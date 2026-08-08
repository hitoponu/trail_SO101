"""キーボード操作の振り分けと目標の持ち方を、ROS 抜きで検証する。

★ ここが試験されていなかったせいで、実機で「どのキーを押しても
  shoulder_lift が下がる」というバグを出した。再発防止のため
  **キー -> 送られる目標** を端から端まで確かめる。
"""

import sys
import types

import pytest

# teleop_keyboard は rclpy を import する。テストは実機もコンテナも無しで
# 回したいので、ダミーの型だけ置いて import を通す。
# ★ ノード本体は使わない。検証するのは handle_key の振り分けと
#   nudge_joint / hold_arm が「何を目標にするか」だけ。
for name in (
    "rclpy",
    "rclpy.action",
    "rclpy.executors",
    "rclpy.node",
    "rclpy.qos",
    "builtin_interfaces.msg",
    "control_msgs.action",
    "geometry_msgs.msg",
    "sensor_msgs.msg",
    "std_msgs.msg",
    "trajectory_msgs.msg",
):
    sys.modules.setdefault(name, types.ModuleType(name))

sys.modules["rclpy"].executors = sys.modules["rclpy.executors"]
sys.modules["rclpy.node"].Node = object
sys.modules["rclpy.action"].ActionClient = object
sys.modules["rclpy.executors"].ExternalShutdownException = type(
    "ExternalShutdownException", (Exception,), {}
)
for module, attributes in {
    "rclpy.qos": ("DurabilityPolicy", "QoSProfile", "ReliabilityPolicy"),
    "builtin_interfaces.msg": ("Duration",),
    "control_msgs.action": ("ParallelGripperCommand",),
    "geometry_msgs.msg": ("Twist",),
    "sensor_msgs.msg": ("JointState",),
    "std_msgs.msg": ("String",),
    "trajectory_msgs.msg": ("JointTrajectory", "JointTrajectoryPoint"),
}.items():
    for attribute in attributes:
        setattr(sys.modules[module], attribute, object)

from lekiwi_examples.cartesian_math import joint_limits_from_urdf  # noqa: E402
from lekiwi_examples.teleop_keyboard import (  # noqa: E402
    ARM_JOINT_ORDER,
    ARM_KEYS,
    BASE_KEYS,
    BASE_TURN_KEYS,
    GRIPPER_KEYS,
    TeleopKeyboard,
    handle_key,
)


class FakeNode:
    """TeleopKeyboard の実装を借りつつ、ROS の入出力だけ差し替える。"""

    _joints = [f"arm_{name}" for name in ARM_JOINT_ORDER]

    # 検証対象の実装をそのまま使う（コピーではなく本物であることが重要）
    nudge_joint = TeleopKeyboard.nudge_joint
    hold_arm = TeleopKeyboard.hold_arm
    _send_target = TeleopKeyboard._send_target
    _sync_target = TeleopKeyboard._sync_target
    _clamp = TeleopKeyboard._clamp

    def __init__(self, positions=None, limits=None, margin=0.0):
        import threading

        self._lock = threading.Lock()
        # ★ `positions or {...}` と書くと空辞書が falsy で既定に落ちる。
        #   「関節状態がまだ来ていない」を表現できなくなる。
        if positions is None:
            positions = {name: 0.0 for name in self._joints}
        self._positions = dict(positions)
        self._target = None
        self._limits = limits
        self._margin = margin
        self._arm_step = 0.05
        self._arm_duration = 0.2
        self.sent: list[list[float]] = []
        self.twists: list[tuple[float, float, float]] = []
        self.gripper_calls: list[float] = []

    # --- ROS の代わり ---
    def _publish(self, target):
        self.sent.append(list(target))

    def set_base(self, vx, vy, wz):
        self.twists.append((vx, vy, wz))

    def nudge_gripper(self, direction):
        self.gripper_calls.append(direction)
        return f"gripper {direction:+.1f}"


# TeleopKeyboard._send_target は JointTrajectory を組んで publish する。
# ROS 型が無いテストでは組み立て部分だけ差し替え、「何を目標にしたか」を見る。
def _send_target(self, index):
    self._publish(self._target)
    if index is None:
        return "hold"
    return f"{self._joints[index]} {self._target[index]:+.3f}"


FakeNode._send_target = _send_target


def test_全キーが意図した関節を動かす():
    """★ 実機バグの直接の再現。1/q/2/w/... が別々の関節に効くこと。"""
    moved = {}
    for key, (index, direction) in ARM_KEYS.items():
        node = FakeNode()
        handle_key(node, key)
        assert len(node.sent) == 1, key
        changed = [i for i, v in enumerate(node.sent[0]) if v != 0.0]
        assert changed == [index], f"{key} が動かした関節 {changed} != [{index}]"
        moved[key] = (index, node.sent[0][index])
        assert node.sent[0][index] == pytest.approx(direction * 0.05)

    # 上段 5 キーが 5 関節すべてを、重複なくカバーしていること
    assert sorted(i for i, _ in moved.values())[::2] == [0, 1, 2, 3, 4]


def test_目標は実測値ではなく前回の目標に積む():
    """★ バグの本体。保持力が弱く関節が垂れても、目標は垂れに追従しない。"""
    node = FakeNode()
    node.nudge_joint(1, +1.0)
    assert node.sent[-1][1] == pytest.approx(+0.05)

    # 実測が重力で下がった（P=16 の保持力問題）。次の指令は影響を受けないこと。
    node._positions["arm_shoulder_lift_joint"] = -0.30

    node.nudge_joint(0, +1.0)  # 別の関節を動かす
    assert node.sent[-1][1] == pytest.approx(+0.05), "垂れた実測値が目標に混入した"
    assert node.sent[-1][0] == pytest.approx(+0.05)

    node.nudge_joint(1, +1.0)
    assert node.sent[-1][1] == pytest.approx(+0.10), "目標が累積していない"


def test_Space_は実測値へ同期し直す():
    node = FakeNode()
    node.nudge_joint(1, +1.0)
    node._positions["arm_shoulder_lift_joint"] = -0.30

    handle_key(node, " ")
    assert node.sent[-1][1] == pytest.approx(-0.30), "Space が現在姿勢を取り込んでいない"

    # 同期後は、その位置からの相対で積む
    node.nudge_joint(1, +1.0)
    assert node.sent[-1][1] == pytest.approx(-0.25)


def test_関節状態が来る前は何も送らない():
    node = FakeNode(positions={})
    status = node.nudge_joint(0, +1.0)
    assert node.sent == []
    assert "待っています" in status


def test_可動域でクランプする():
    limits = [(-1.0, 1.0)] * 5
    node = FakeNode(limits=limits, margin=0.10)
    for _ in range(100):
        node.nudge_joint(0, +1.0)
    assert node.sent[-1][0] == pytest.approx(0.90), "上限 - margin を超えた"
    for _ in range(100):
        node.nudge_joint(0, -1.0)
    assert node.sent[-1][0] == pytest.approx(-0.90)


def test_余白が可動域より広ければクランプしない():
    """margin が過大でも「動かせない」にはせず、素通しにする。"""
    node = FakeNode(limits=[(-0.05, 0.05)] * 5, margin=0.10)
    node.nudge_joint(0, +1.0)
    assert node.sent[-1][0] == pytest.approx(0.05)


def test_ベースの左右移動が割り当てられている():
    """j / l が linear.y に出ること（回転ではない）。"""
    assert BASE_KEYS["j"] == (0.0, +1.0, 0.0)
    assert BASE_KEYS["l"] == (0.0, -1.0, 0.0)
    node = FakeNode()
    handle_key(node, "j")
    handle_key(node, "l")
    assert node.twists == [(0.0, 1.0, 0.0), (0.0, -1.0, 0.0)]


def test_旋回は別キーに分けてある():
    node = FakeNode()
    handle_key(node, "[")
    handle_key(node, "]")
    assert node.twists == [(0.0, 0.0, +1.0), (0.0, 0.0, -1.0)]
    assert not set(BASE_TURN_KEYS) & set(BASE_KEYS)


def test_キーが重複していない():
    """同じキーが 2 つの役割を持つと、先に評価された側だけが効く。"""
    groups = [set(BASE_KEYS), set(BASE_TURN_KEYS), set(ARM_KEYS), set(GRIPPER_KEYS), {" ", "?"}]
    for i, left in enumerate(groups):
        for right in groups[i + 1:]:
            assert not left & right, f"キーが重複: {left & right}"


def test_知らないキーはベースを止める():
    node = FakeNode()
    handle_key(node, "Z")
    assert node.twists == [(0.0, 0.0, 0.0)]
    assert node.sent == []


def test_URDF_から可動域を読む():
    urdf = """<robot name="t">
      <joint name="arm_shoulder_pan_joint" type="revolute">
        <parent link="a"/><child link="b"/>
        <limit lower="-1.9" upper="1.9" effort="1" velocity="1"/>
      </joint>
      <joint name="fixed_one" type="fixed">
        <parent link="b"/><child link="c"/>
      </joint>
    </robot>"""
    limits = joint_limits_from_urdf(urdf)
    assert limits == {"arm_shoulder_pan_joint": (-1.9, 1.9)}
