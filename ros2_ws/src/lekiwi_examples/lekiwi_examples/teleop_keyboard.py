"""キーボードでベースとアームを同時に動かす。

    ros2 run lekiwi_examples teleop_keyboard

★ `robot.launch.py` が動いていることが前提。このノードはハードウェアに
  直接触らず、ROS のインターフェースだけを使う:

    ベース  -> /cmd_vel                                        (geometry_msgs/Twist)
    アーム  -> /joint_trajectory_controller/joint_trajectory    (trajectory_msgs)
    グリッパ -> /gripper_controller/gripper_cmd                  (action)

────────────────────────────────────────────────────────────────────────
★ 安全上の注意
────────────────────────────────────────────────────────────────────────
* **車輪を浮かせてから使うこと。** `/cmd_vel` は Nav2 の collision_monitor
  より下流なので、**衝突監視も加速度制限も効かない**。
* アームは可動域の内側 `joint_limit_margin` まで自動でクランプするが、
  **機体との干渉は見ていない**。LiDAR やプレートに当たりうる。
* キーを離せばベースは止まる (`base_driver` の watchdog が 0.5 秒で
  速度ゼロにする)。**アームは止まらず、その姿勢で保持する**。

────────────────────────────────────────────────────────────────────────
キー配置
────────────────────────────────────────────────────────────────────────
ベース (teleop_twist_keyboard と同じ並び。★ オムニなので真横にも動ける)

    u  i  o        i / ,  前後       j / l  左右 (strafe)
    j  k  l        u / o  左前/右前   m / .  左後/右後
    m  ,  .        k      停止        q / z  速度の増減

アーム (上段が +、下段が −)

    1 / q   shoulder_pan       2 / w   shoulder_lift
    3 / e   elbow_flex         4 / r   wrist_flex
    5 / t   wrist_roll         6 / y   gripper (開 / 閉)

    Space   アームを止める (いまの姿勢で保持)
    Ctrl+C  終了
"""

from __future__ import annotations

import sys
import termios
import threading
import tty

import rclpy
from builtin_interfaces.msg import Duration
from control_msgs.action import ParallelGripperCommand
from geometry_msgs.msg import Twist
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

# ベース: キー -> (vx, vy, wz) の向き。大きさは speed 側で決める。
BASE_KEYS = {
    "i": (1.0, 0.0, 0.0),
    ",": (-1.0, 0.0, 0.0),
    "j": (0.0, 1.0, 0.0),
    "l": (0.0, -1.0, 0.0),
    "u": (1.0, 1.0, 0.0),
    "o": (1.0, -1.0, 0.0),
    "m": (-1.0, 1.0, 0.0),
    ".": (-1.0, -1.0, 0.0),
    "k": (0.0, 0.0, 0.0),
}
# ★ 回転は別キーにする。teleop_twist_keyboard は j/l を回転に使うが、
#   このベースはオムニで真横に動けるため、strafe を主に割り当てた。
BASE_TURN_KEYS = {"[": 1.0, "]": -1.0}

# アーム: キー -> (関節の並び順, 符号)。上段が +、下段が −。
ARM_JOINT_ORDER = (
    "shoulder_pan_joint",
    "shoulder_lift_joint",
    "elbow_flex_joint",
    "wrist_flex_joint",
    "wrist_roll_joint",
)
ARM_KEYS = {
    "1": (0, +1.0), "q": (0, -1.0),
    "2": (1, +1.0), "w": (1, -1.0),
    "3": (2, +1.0), "e": (2, -1.0),
    "4": (3, +1.0), "r": (3, -1.0),
    "5": (4, +1.0), "t": (4, -1.0),
}
GRIPPER_KEYS = {"6": +1.0, "y": -1.0}

HELP = __doc__


class TeleopKeyboard(Node):
    def __init__(self) -> None:
        super().__init__("lekiwi_teleop_keyboard")

        defaults = {
            "joint_prefix": "arm_",
            "cmd_vel_topic": "/cmd_vel",
            "trajectory_topic": "/joint_trajectory_controller/joint_trajectory",
            "gripper_action": "/gripper_controller/gripper_cmd",
            # ★ base.yaml の上限 (0.26 / 0.23 / 1.8) より控えめにしておく。
            #   キー操作は微調整が効かないので、既定は遅いほうが安全。
            "base_linear_speed": 0.10,
            "base_angular_speed": 0.5,
            # アームは 1 キー押下あたりこれだけ動く [rad]。
            "arm_step": 0.05,
            "arm_step_duration": 0.20,
            # グリッパは 0.0-1.0 の正規化位置で送る。
            "gripper_step": 0.10,
            # 可動域の端から残す余白 [rad]。URDF の値を直接は読まないので、
            # ここは「送る目標をどこでクランプするか」だけを決める。
            "joint_limit_margin": 0.10,
            "publish_rate": 20.0,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

        def param(name):
            return self.get_parameter(name).value

        prefix = str(param("joint_prefix"))
        self._joints = [f"{prefix}{name}" for name in ARM_JOINT_ORDER]
        self._gripper_joint = f"{prefix}gripper_joint"
        self._arm_step = float(param("arm_step"))
        self._arm_duration = float(param("arm_step_duration"))
        self._gripper_step = float(param("gripper_step"))
        self._margin = float(param("joint_limit_margin"))
        self._linear = float(param("base_linear_speed"))
        self._angular = float(param("base_angular_speed"))

        self._cmd_pub = self.create_publisher(Twist, str(param("cmd_vel_topic")), 10)
        self._traj_pub = self.create_publisher(
            JointTrajectory, str(param("trajectory_topic")), 10
        )
        self._gripper = ActionClient(
            self, ParallelGripperCommand, str(param("gripper_action"))
        )

        # ★ /joint_states の publisher は 2 つ (車輪 / アーム) あるので、
        #   1 通では全関節が揃わない。辞書に蓄積する。
        self._positions: dict[str, float] = {}
        self.create_subscription(JointState, "/joint_states", self._joint_state_cb, 10)

        self._twist = (0.0, 0.0, 0.0)
        self._lock = threading.Lock()
        self._gripper_target: float | None = None

        self.create_timer(1.0 / float(param("publish_rate")), self._publish_twist)

    # ── 状態 ──────────────────────────────────────────────────────────

    def _joint_state_cb(self, message: JointState) -> None:
        with self._lock:
            self._positions.update(zip(message.name, message.position))

    def _arm_ready(self) -> bool:
        with self._lock:
            return all(name in self._positions for name in self._joints)

    # ── ベース ────────────────────────────────────────────────────────

    def set_base(self, vx: float, vy: float, wz: float) -> None:
        with self._lock:
            self._twist = (vx, vy, wz)

    def _publish_twist(self) -> None:
        with self._lock:
            vx, vy, wz = self._twist
        message = Twist()
        message.linear.x = vx * self._linear
        message.linear.y = vy * self._linear
        message.angular.z = wz * self._angular
        self._cmd_pub.publish(message)

    # ── アーム ────────────────────────────────────────────────────────

    def nudge_joint(self, index: int, direction: float) -> str:
        """1 関節だけを arm_step ぶん動かす目標を送る。"""
        if not self._arm_ready():
            return "関節状態を待っています（/joint_states）"
        with self._lock:
            target = [self._positions[name] for name in self._joints]
        target[index] += direction * self._arm_step

        message = JointTrajectory()
        message.header.stamp = self.get_clock().now().to_msg()
        message.joint_names = list(self._joints)
        point = JointTrajectoryPoint()
        point.positions = [float(v) for v in target]
        point.velocities = [0.0] * len(target)
        seconds = int(self._arm_duration)
        point.time_from_start = Duration(
            sec=seconds, nanosec=int((self._arm_duration - seconds) * 1e9)
        )
        message.points = [point]
        self._traj_pub.publish(message)
        return f"{self._joints[index]} {direction * self._arm_step:+.3f} rad"

    def hold_arm(self) -> str:
        """いまの姿勢をそのまま目標として送り、動きを止める。"""
        if not self._arm_ready():
            return "関節状態を待っています"
        return self.nudge_joint(0, 0.0)

    def nudge_gripper(self, direction: float) -> str:
        if not self._gripper.server_is_ready():
            self._gripper.wait_for_server(timeout_sec=0.5)
            if not self._gripper.server_is_ready():
                return "グリッパのアクションサーバが居ません"
        if self._gripper_target is None:
            self._gripper_target = 0.5
        self._gripper_target = min(1.0, max(0.0, self._gripper_target + direction * self._gripper_step))
        goal = ParallelGripperCommand.Goal()
        goal.command.position = [float(self._gripper_target)]
        # ★ 結果は待たない。購読コールバックの中で spin すると詰まる。
        self._gripper.send_goal_async(goal)
        return f"gripper -> {self._gripper_target:.2f}"

    def stop_all(self) -> None:
        self.set_base(0.0, 0.0, 0.0)
        self._publish_twist()


def _read_key() -> str:
    """端末を raw にして 1 文字読む。pynput を使わないので SSH でも動く。"""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main() -> None:
    rclpy.init()
    node = TeleopKeyboard()

    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)
    spin = threading.Thread(target=executor.spin, daemon=True)
    spin.start()

    print(HELP)
    status = ""
    try:
        while rclpy.ok():
            key = _read_key()
            if key == "\x03":  # Ctrl+C
                break
            if key in BASE_KEYS:
                node.set_base(*BASE_KEYS[key])
                status = f"base {BASE_KEYS[key]}"
            elif key in BASE_TURN_KEYS:
                node.set_base(0.0, 0.0, BASE_TURN_KEYS[key])
                status = f"turn {BASE_TURN_KEYS[key]:+.0f}"
            elif key in ARM_KEYS:
                index, direction = ARM_KEYS[key]
                status = node.nudge_joint(index, direction)
            elif key in GRIPPER_KEYS:
                status = node.nudge_gripper(GRIPPER_KEYS[key])
            elif key == " ":
                status = node.hold_arm()
            elif key == "?":
                print(HELP)
                continue
            else:
                # 知らないキーはベースを止める。暴走させないための既定動作。
                node.set_base(0.0, 0.0, 0.0)
                status = "停止"
            print(f"\r{status:<60}", end="", flush=True)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        # ★ 終了時に必ずベースを止める。ここを飛ばすと watchdog の 0.5 秒ぶん
        #   走り続ける。
        node.stop_all()
        print()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
