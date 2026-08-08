"""Reach the SO-101 gripper to a point that is fixed in the `map` frame.

Scope, deliberately: **the arm only**. If the target is out of reach this node
warns and does nothing. It never drives the base — it creates no /cmd_vel
publisher at all, so that guarantee is structural rather than a matter of
discipline (see test_reach_node_contract.py).

Accuracy: the target is resolved through map -> odom -> base_footprint -> ... ->
arm_base_link, so every centimetre of SLAM error lands on the gripper. Realistic
end-to-end accuracy is a few centimetres, not the solver's 5 mm tolerance. The
residual reported in the status line is the SOLVER residual; do not read it as
physical accuracy.
"""

from __future__ import annotations

import math

import numpy as np
import rclpy
import tf2_ros
from action_msgs.msg import GoalStatus
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory, ParallelGripperCommand
from geometry_msgs.msg import PointStamped, PoseStamped
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.duration import Duration as RclDuration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from std_srvs.srv import Trigger
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from visualization_msgs.msg import Marker

from .cartesian_math import (
    ARM_JOINTS,
    BASE_LINK,
    CONTROLLED_JOINTS,
    SerialChain,
    TIP_LINK,
    missing_joints,
    prefixed,
)
from .reach_solver import SolverConfig, solve


class ReachToPoint(Node):
    def __init__(self) -> None:
        super().__init__("so101_reach_to_point")

        defaults = {
            "joint_prefix": "arm_",
            # Given UNPREFIXED; joint_prefix is applied to both.
            "base_link": BASE_LINK,
            "tip_link": TIP_LINK,
            "target_topic": "/so101/reach_target",
            "point_target_topic": "/clicked_point",
            "subscribe_clicked_point": True,
            "trajectory_action": "/joint_trajectory_controller/follow_joint_trajectory",
            "gripper_action": "/gripper_controller/gripper_cmd",
            "expected_frame": "map",
            "tf_timeout": 0.5,
            "tf_max_age": 1.0,
            # Cheap sanity guard only: skip 200 solver iterations to say
            # "obviously no" for a target metres away. Measured envelope from
            # arm_base_link is 0.007-0.543 m (grid over the joint limits with
            # the 0.10 rad margin), and the zero pose alone sits at 0.452 m,
            # so anything under ~0.55 would reject genuinely reachable points.
            # This is NOT a tipping guard - a radius cannot tell a safe pose
            # from a tippy one. Use joint_limit_overrides for that.
            "max_reach_radius": 0.55,
            # Floor guard only; it cannot protect the robot body (the plate spans
            # z 0.033-0.040 and plate2 tops out at 0.092 in base_footprint).
            # Use joint_limit_overrides for the body.
            "z_floor": 0.035,
            "floor_frame": "base_footprint",
            "min_command_interval": 1.0,
            "max_joint_speed": 0.6,
            "min_reach_duration": 1.0,
            "max_reach_duration": 12.0,
            "require_stationary_base": True,
            "odom_topic": "/odom",
            "base_linear_tolerance": 0.01,
            "base_angular_tolerance": 0.05,
            "base_motion_tolerance": 0.02,
            "base_watch_rate": 10.0,
            "goal_time_slack": 5.0,
            # "joint:lower:upper" entries, intersected with the URDF limits.
            # Determined by hand on the real robot (hardware step 5) so the arm
            # cannot sweep into the LiDAR or the camera mount. laser_link and
            # arm_mount_link are only 44 mm apart in xy.
            "joint_limit_overrides": [""],
            # Measured stow target.  The stow callback still intersects it with
            # the runtime URDF limits and the configured safety margin.
            # Order: shoulder_pan, shoulder_lift, elbow_flex, wrist_flex,
            # wrist_roll.  The gripper target is configured separately below.
            "stow_positions": [
                0.03222146311374147,
                -1.7951958020513104,
                1.7422605412215924,
                -1.7721804712557807,
                1.370946537720381,
            ],
            "stow_gripper_position": 0.0363150867823765,
            "solver_tolerance": 0.005,
            "solver_max_iterations": 200,
            "solver_step": 0.02,
            "solver_max_joint_step": 0.10,
            "solver_damping": 0.03,
            "joint_limit_margin": 0.10,
            "solver_stall_tolerance": 1e-4,
            "solver_stall_patience": 10,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

        def param(name):
            return self.get_parameter(name).value

        prefix = str(param("joint_prefix"))
        self._prefix = prefix
        self._arm_joints = prefixed(ARM_JOINTS, prefix)
        self._controlled_joints = prefixed(CONTROLLED_JOINTS, prefix)
        self._base = prefix + str(param("base_link"))
        self._tip = prefix + str(param("tip_link"))

        self._expected_frame = str(param("expected_frame"))
        self._tf_timeout = float(param("tf_timeout"))
        self._tf_max_age = float(param("tf_max_age"))
        self._max_reach_radius = float(param("max_reach_radius"))
        self._z_floor = float(param("z_floor"))
        self._floor_frame = str(param("floor_frame"))
        self._min_interval = float(param("min_command_interval"))
        self._max_joint_speed = float(param("max_joint_speed"))
        self._min_duration = float(param("min_reach_duration"))
        self._max_duration = float(param("max_reach_duration"))
        self._require_stationary = bool(param("require_stationary_base"))
        self._linear_tolerance = float(param("base_linear_tolerance"))
        self._angular_tolerance = float(param("base_angular_tolerance"))
        self._drift_tolerance = float(param("base_motion_tolerance"))
        self._goal_time_slack = float(param("goal_time_slack"))
        self._stow = [float(value) for value in param("stow_positions")]
        if len(self._stow) != len(ARM_JOINTS):
            raise ValueError(
                f"stow_positions must have {len(ARM_JOINTS)} entries, "
                f"got {len(self._stow)}"
            )
        self._stow_gripper = float(param("stow_gripper_position"))
        if not math.isfinite(self._stow_gripper):
            raise ValueError("stow_gripper_position must be finite")

        self._config = SolverConfig(
            tolerance=float(param("solver_tolerance")),
            max_iterations=int(param("solver_max_iterations")),
            step=float(param("solver_step")),
            max_joint_step=float(param("solver_max_joint_step")),
            damping=float(param("solver_damping")),
            joint_limit_margin=float(param("joint_limit_margin")),
            stall_tolerance=float(param("solver_stall_tolerance")),
            stall_patience=int(param("solver_stall_patience")),
        )
        self._overrides = self._parse_overrides(param("joint_limit_overrides"))

        self._chain: SerialChain | None = None
        self._limits: list[tuple[float, float]] = []
        self._positions: dict[str, float] = {}
        self._busy = False
        self._last_accept: Time | None = None
        self._goal_handle = None
        self._plan_translation: np.ndarray | None = None
        #: アクションが結果を返さないまま消えたときに _busy を解除する期限。
        self._deadline = None
        #: Target in the planning frame, kept so the achieved pose can be
        #: scored by our own FK when the action reports back.
        self._target: np.ndarray | None = None

        # The target subscription and the action client must not share a group,
        # or the action's done-callbacks deadlock behind a running target
        # callback (both are served by the same MultiThreadedExecutor).
        self._inbox = MutuallyExclusiveCallbackGroup()
        self._actions = MutuallyExclusiveCallbackGroup()

        self._buffer = tf2_ros.Buffer(cache_time=RclDuration(seconds=10.0))
        # ★ spin_thread=False であること。
        #   spin_thread=True は「渡したノード」を自前の SingleThreadedExecutor に
        #   add_node する (tf2_ros/transform_listener.py の run_func)。ノードは
        #   1 つの executor にしか属せず、Node.executor の setter は前の executor から
        #   自分を remove するので、main() の MultiThreadedExecutor.add_node と
        #   競合して後勝ちになる。listener 側が勝つと全コールバックが
        #   SingleThreadedExecutor に載り、lookup_transform(timeout) が
        #   TF 受信スレッド自身を塞いで毎回タイムアウトし、
        #   REJECTED_NO_TF を出し続ける。
        #   False なら MTE が TF 購読も捌くので決定的になる。TF の購読は
        #   TransformListener 側で ReentrantCallbackGroup に入るため、
        #   目標処理中でも並行して受信できる。
        self._listener = tf2_ros.TransformListener(
            self._buffer, self, spin_thread=False
        )

        latched = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.create_subscription(
            String, "/robot_description", self._description_cb, latched
        )
        self.create_subscription(
            JointState, "/joint_states", self._joint_state_cb, 10
        )
        self.create_subscription(
            PoseStamped,
            str(param("target_topic")),
            self._pose_target_cb,
            10,
            callback_group=self._inbox,
        )
        if bool(param("subscribe_clicked_point")):
            # RViz's "Publish Point" tool emits PointStamped, NOT PoseStamped
            # (that is "2D Goal Pose", on /goal_pose, which nav2 owns). A plain
            # remap would silently never fire, so subscribe to both types.
            self.create_subscription(
                PointStamped,
                str(param("point_target_topic")),
                self._point_target_cb,
                10,
                callback_group=self._inbox,
            )
        self._odom_twist: tuple[float, float] | None = None
        self._odom_stamp: Time | None = None
        self._odom_topic = str(param("odom_topic"))
        if self._require_stationary:
            self.create_subscription(
                Odometry, self._odom_topic, self._odom_cb, 10
            )

        self._status_pub = self.create_publisher(String, "/so101/reach_status", 10)
        self._marker_pub = self.create_publisher(Marker, "/so101/reach_markers", 10)
        self._client = ActionClient(
            self,
            FollowJointTrajectory,
            str(param("trajectory_action")),
            callback_group=self._actions,
        )
        self._gripper_client = ActionClient(
            self,
            ParallelGripperCommand,
            str(param("gripper_action")),
            callback_group=self._actions,
        )
        self.create_service(
            Trigger, "/so101/stow", self._stow_cb, callback_group=self._inbox
        )

        self._watch = self.create_timer(
            1.0 / float(param("base_watch_rate")),
            self._watch_base,
            callback_group=self._actions,
        )

        self.get_logger().info(
            f"reach: planning frame={self._base}, tip={self._tip}, "
            f"targets in {self._expected_frame!r}"
        )

    # ---------------------------------------------------------------- inputs

    def _parse_overrides(self, entries) -> dict[str, tuple[float, float]]:
        result: dict[str, tuple[float, float]] = {}
        for entry in entries or []:
            text = str(entry).strip()
            if not text:
                continue
            parts = text.split(":")
            if len(parts) != 3:
                raise ValueError(
                    f"joint_limit_overrides entry must be 'joint:lower:upper', got {text!r}"
                )
            name, lower, upper = parts[0], float(parts[1]), float(parts[2])
            if lower >= upper:
                raise ValueError(f"joint_limit_overrides {name}: lower must be < upper")
            result[name] = (lower, upper)
        return result

    def _description_cb(self, message: String) -> None:
        if self._chain is not None:
            return
        try:
            chain = SerialChain.from_urdf(message.data, self._base, self._tip)
            limits = chain.limits(self._controlled_joints)
        except (ValueError, KeyError) as exc:
            self.get_logger().error(f"robot_description を使用できません: {exc}")
            return

        merged = []
        for name, (lower, upper) in zip(self._controlled_joints, limits):
            if name in self._overrides:
                over_lower, over_upper = self._overrides[name]
                lower, upper = max(lower, over_lower), min(upper, over_upper)
                if lower >= upper:
                    self.get_logger().error(
                        f"{name}: joint_limit_overrides が URDF の可動範囲と交わらない"
                    )
                    return
            merged.append((lower, upper))

        unknown = set(self._overrides) - set(self._controlled_joints)
        if unknown:
            self.get_logger().warn(
                f"joint_limit_overrides に未知の関節: {sorted(unknown)}"
            )

        # ★ 順序が重要。読み手は別スレッド (_inbox グループ) で、
        #   _handle_target は _chain の非 None だけを準備完了の判定に使う。
        #   逆順にすると _chain が入って _limits が [] の一瞬に目標が届いたとき、
        #   bounded_target が何もクランプせず**関節制限なしで解いてしまう**。
        self._limits = merged
        self._chain = chain
        self.get_logger().info(f"URDF チェーンを読み込みました: {self._base} -> {self._tip}")

    def _joint_state_cb(self, message: JointState) -> None:
        # Two publishers (base wheels and the arm broadcaster) each send only
        # their own joints, so a single message is never a full snapshot.
        self._positions.update(dict(zip(message.name, message.position)))

    def _odom_cb(self, message: Odometry) -> None:
        linear = message.twist.twist.linear
        angular = message.twist.twist.angular
        self._odom_twist = (
            math.hypot(linear.x, linear.y),
            abs(angular.z),
        )
        self._odom_stamp = self.get_clock().now()

    def _point_target_cb(self, message: PointStamped) -> None:
        pose = PoseStamped()
        pose.header = message.header
        pose.pose.position = message.point
        pose.pose.orientation.w = 1.0
        self._handle_target(pose)

    def _pose_target_cb(self, message: PoseStamped) -> None:
        self._handle_target(message)

    # --------------------------------------------------------------- reporting

    def _report(self, code: str, detail: str = "") -> None:
        line = f"{code} {detail}".strip()
        message = String()
        message.data = line
        self._status_pub.publish(message)
        if code.startswith(("REJECTED", "ABORTED", "FAILED")):
            self.get_logger().warn(line)
        else:
            self.get_logger().info(line)

    def _marker(self, frame: str, point, accepted: bool) -> None:
        marker = Marker()
        marker.header.frame_id = frame
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.ns = "so101_reach"
        marker.id = 0
        marker.type = Marker.SPHERE
        marker.action = Marker.ADD
        marker.pose.position = point
        marker.pose.orientation.w = 1.0
        marker.scale.x = marker.scale.y = marker.scale.z = 0.04
        marker.color.a = 0.8
        marker.color.g = 1.0 if accepted else 0.0
        marker.color.r = 0.0 if accepted else 1.0
        self._marker_pub.publish(marker)

    # ---------------------------------------------------------------- planning

    def _lookup(self, target_frame: str, source_frame: str, stamp: Time):
        """Transform at `stamp`, falling back to latest with a warning."""
        try:
            return self._buffer.lookup_transform(
                target_frame,
                source_frame,
                stamp,
                timeout=RclDuration(seconds=self._tf_timeout),
            )
        except tf2_ros.ExtrapolationException:
            transform = self._buffer.lookup_transform(
                target_frame, source_frame, Time()
            )
            self.get_logger().warn(
                f"{source_frame} -> {target_frame} をメッセージ時刻で引けず、"
                "最新の TF で解決した"
            )
            return transform

    def _tf_reason(self, frame: str) -> str:
        """tf2's explanation of why a transform is unavailable, if it offers one."""
        try:
            available, reason = self._buffer.can_transform(
                self._base, frame, Time(), return_debug_tuple=True
            )
        except (TypeError, tf2_ros.TransformException):
            return ""
        return "" if available else str(reason)

    def _tf_age(self, source_frame: str) -> float:
        """Seconds since the newest transform on the chain from source_frame.

        lookup_transform with Time() succeeds on a stale-but-present transform,
        so a dead slam_toolbox would leave a frozen map->odom and every reach
        would silently plan in a past world. This is the guard for that.
        """
        transform = self._buffer.lookup_transform(self._base, source_frame, Time())
        stamp = Time.from_msg(transform.header.stamp)
        if stamp.nanoseconds == 0:
            return 0.0  # static transform: never stale
        return (self.get_clock().now() - stamp).nanoseconds / 1e9

    def _handle_target(self, message: PoseStamped) -> None:
        if self._chain is None:
            self._report("REJECTED_NOT_READY", "robot_description を待っている")
            return
        missing = missing_joints(self._positions, self._arm_joints)
        if missing:
            self._report("REJECTED_NOT_READY", f"関節状態が不足: {missing}")
            return
        if self._busy:
            self._report("REJECTED_BUSY", "実行中のリーチがある")
            return

        now = self.get_clock().now()
        if (
            self._last_accept is not None
            and (now - self._last_accept).nanoseconds / 1e9 < self._min_interval
        ):
            self._report("REJECTED_TOO_SOON", f"< {self._min_interval}s")
            return

        frame = message.header.frame_id
        if not frame:
            self._report("REJECTED_NO_FRAME", "header.frame_id が空")
            return
        if self._expected_frame and frame != self._expected_frame:
            self._report(
                "REJECTED_WRONG_FRAME",
                f"frame_id={frame!r}, 期待値={self._expected_frame!r} "
                "(RViz の Fixed Frame を確認)",
            )
            return

        if self._require_stationary:
            # ★ fail-closed。odom が一度も来ていなければガードは検証できないので
            #   拒否する。ベースは別コンテナなので「まだ上がっていない」
            #   「トピック名が違う」は現実に起きる。ここを fail-open にすると
            #   「静止確認を要求しているのに一度も確認していない」状態で
            #   アームが動く (tf_max_age を fail-closed にしたのと同じ理由)。
            if self._odom_twist is None or self._odom_stamp is None:
                self._report(
                    "REJECTED_NOT_READY",
                    f"{self._odom_topic} が未受信で静止確認ができない "
                    "(ベース側が未起動か、require_stationary_base:=false)",
                )
                return
            # 鮮度も見る。ベースのコンテナが落ちると odom は止まるが
            # 最後の値は残るので、「止まっていた」ことになって素通りする。
            # tf_max_age と同じ理由でこちらも fail-closed にする。
            odom_age = (now - self._odom_stamp).nanoseconds / 1e9
            if odom_age > self._tf_max_age:
                self._report(
                    "REJECTED_STALE_ODOM",
                    f"{self._odom_topic} age={odom_age:.1f}s > {self._tf_max_age}s "
                    "(ベース側が停止している可能性)",
                )
                return
            linear, angular = self._odom_twist
            if linear > self._linear_tolerance or angular > self._angular_tolerance:
                self._report(
                    "REJECTED_BASE_MOVING",
                    f"linear={linear:.3f} angular={angular:.3f}",
                )
                return

        stamp = Time.from_msg(message.header.stamp)
        try:
            transform = self._lookup(self._base, frame, stamp)
            age = self._tf_age(frame)
        except tf2_ros.TransformException as exc:
            # tf2's own message names the missing link, which distinguishes
            # "slam not started" from "slam not yet localized". Keep it verbatim.
            self._report("REJECTED_NO_TF", self._tf_reason(frame) or str(exc))
            self._marker(frame, message.pose.position, accepted=False)
            return

        if age > self._tf_max_age:
            self._report(
                "REJECTED_STALE_TF",
                f"age={age:.1f}s > {self._tf_max_age}s "
                "(slam_toolbox が停止している可能性)",
            )
            self._marker(frame, message.pose.position, accepted=False)
            return

        target = self._apply(transform, message.pose.position)

        distance = float(np.linalg.norm(target))
        if distance > self._max_reach_radius:
            self._report(
                "REJECTED_OUT_OF_RANGE",
                f"range={distance:.3f}m > max_reach_radius={self._max_reach_radius}m",
            )
            self._marker(frame, message.pose.position, accepted=False)
            return

        try:
            floor = self._apply(
                self._lookup(self._floor_frame, frame, stamp), message.pose.position
            )
            if floor[2] < self._z_floor:
                self._report(
                    "REJECTED_BELOW_FLOOR",
                    f"z={floor[2]:.3f}m < z_floor={self._z_floor}m",
                )
                self._marker(frame, message.pose.position, accepted=False)
                return
        except tf2_ros.TransformException:
            self.get_logger().warn(
                f"{self._floor_frame} が引けないので床面チェックを省略した"
            )

        start = np.array([self._positions[name] for name in self._arm_joints])
        try:
            result = solve(
                self._chain, start, target, self._limits, self._config, self._prefix
            )
        except (KeyError, ValueError, np.linalg.LinAlgError) as exc:
            self._report("REJECTED_SOLVER_ERROR", str(exc))
            self._marker(frame, message.pose.position, accepted=False)
            return

        if not result.solved:
            self._report(
                "REJECTED_UNREACHABLE",
                f"residual={result.residual:.4f} status={result.status} "
                f"pinned={result.pinned}",
            )
            self._marker(frame, message.pose.position, accepted=False)
            return

        travel = float(np.max(np.abs(result.positions - start)))
        duration = min(
            self._max_duration,
            max(self._min_duration, travel / self._max_joint_speed),
        )
        position = message.pose.position
        self._report(
            "ACCEPTED",
            f"target={frame}({position.x:.3f},{position.y:.3f},{position.z:.3f}) "
            f"{self._base}({target[0]:.3f},{target[1]:.3f},{target[2]:.3f}) "
            f"iters={result.iterations} residual={result.residual:.4f} "
            f"dur={duration:.1f}",
        )
        self._marker(frame, position, accepted=True)
        self._last_accept = now
        self._plan_translation = self._translation(transform)
        self._send(result.positions, duration, target)

    @staticmethod
    def _translation(transform) -> np.ndarray:
        t = transform.transform.translation
        return np.array([t.x, t.y, t.z])

    @staticmethod
    def _apply(transform, point) -> np.ndarray:
        """Rotate and translate a point by a TransformStamped."""
        q = transform.transform.rotation
        t = transform.transform.translation
        vector = np.array([point.x, point.y, point.z])
        quaternion = np.array([q.x, q.y, q.z, q.w])
        x, y, z, w = quaternion
        rotation = np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )
        return rotation @ vector + np.array([t.x, t.y, t.z])

    # ----------------------------------------------------------------- output

    def _send_gripper(self, position: float) -> None:
        goal = ParallelGripperCommand.Goal()
        goal.command.position = [float(position)]
        future = self._gripper_client.send_goal_async(goal)
        future.add_done_callback(self._gripper_goal_response)

    def _gripper_goal_response(self, future) -> None:
        try:
            handle = future.result()
        except Exception as exc:  # pragma: no cover - middleware failure
            self.get_logger().error(f"グリッパのstow送信に失敗: {exc}")
            return
        if handle is None or not handle.accepted:
            self.get_logger().error("グリッパのstowゴールが拒否された")
            return
        result_future = handle.get_result_async()
        result_future.add_done_callback(self._gripper_result)

    def _gripper_result(self, future) -> None:
        try:
            outcome = future.result()
        except Exception as exc:  # pragma: no cover - middleware failure
            self.get_logger().error(f"グリッパのstow結果を取得できない: {exc}")
            return
        if outcome is None or outcome.status != GoalStatus.STATUS_SUCCEEDED:
            status = "unknown" if outcome is None else str(outcome.status)
            self.get_logger().error(f"グリッパのstowに失敗: status={status}")

    def _send(self, positions: np.ndarray, duration: float, target=None) -> None:
        if not self._client.wait_for_server(timeout_sec=2.0):
            self._report("FAILED_ACTION", "コントローラのアクションサーバが無い")
            self._release()
            return

        trajectory = JointTrajectory()
        trajectory.joint_names = list(self._arm_joints)
        point = JointTrajectoryPoint()
        point.positions = [float(value) for value in positions]
        # Zero terminal velocity so the controller does not extrapolate past
        # the final point.
        point.velocities = [0.0] * len(self._arm_joints)
        seconds = int(duration)
        point.time_from_start = Duration(
            sec=seconds, nanosec=int((duration - seconds) * 1e9)
        )
        trajectory.points = [point]

        goal = FollowJointTrajectory.Goal()
        goal.trajectory = trajectory
        # 宣言だけして使っていないと「効いているつもりのつまみ」になり、
        # 実機で挙動を追うときに紛らわしい。ここで実際にゴールへ載せる。
        # 未設定 (0) だと ros2_controllers.yaml の constraints.goal_time だけが効く。
        slack = int(self._goal_time_slack)
        goal.goal_time_tolerance = Duration(
            sec=slack, nanosec=int((self._goal_time_slack - slack) * 1e9)
        )

        self._busy = True
        self._deadline = (
            self.get_clock().now()
            + RclDuration(seconds=duration + self._goal_time_slack + 10.0)
        )
        self._target = None if target is None else np.asarray(target)
        future = self._client.send_goal_async(goal)
        future.add_done_callback(self._goal_response)

    def _release(self) -> None:
        """Return to accepting targets. Every exit path must go through here."""
        self._busy = False
        self._goal_handle = None
        self._plan_translation = None
        self._deadline = None

    def _goal_response(self, future) -> None:
        handle = future.result()
        if handle is None or not handle.accepted:
            self._release()
            self._report("FAILED_ACTION", "コントローラがゴールを拒否した")
            return
        self._goal_handle = handle
        handle.get_result_async().add_done_callback(self._goal_result)

    def _goal_result(self, future) -> None:
        self._release()
        outcome = future.result()
        if outcome is None:
            self._report("FAILED_ACTION", "結果を取得できなかった")
            return
        if outcome.status == GoalStatus.STATUS_CANCELED:
            return  # already reported by whoever cancelled

        # Judge success by our own FK on the achieved joint state, not by the
        # controller's verdict: with a finite-difference velocity estimate over
        # a 4096 count/rev encoder, its tolerance checks are unreliable.
        detail = ""
        if self._chain is not None and self._target is not None:
            try:
                tip, _ = self._chain.position_and_jacobian(
                    {name: self._positions[name] for name in self._arm_joints},
                    self._controlled_joints,
                )
                detail = f"residual_fk={float(np.linalg.norm(self._target - tip)):.4f}"
            except (KeyError, ValueError):
                detail = "residual_fk=unavailable"

        result = outcome.result
        if outcome.status == GoalStatus.STATUS_SUCCEEDED and result.error_code == 0:
            self._report("SUCCEEDED", detail)
        else:
            self._report(
                "FAILED_ACTION",
                f"status={outcome.status} error_code={result.error_code} "
                f"{result.error_string} {detail}".strip(),
            )

    # ----------------------------------------------------------------- safety

    def _watch_base(self) -> None:
        """Abort the reach if the base moves out from under the plan."""
        if not self._busy:
            return
        # ★ _busy の抜け道。アクションサーバが結果を返さないまま消えると
        #   (コントローラのクラッシュ、spawner のやり直し等) done-callback が
        #   永遠に来ず、以降すべての目標が REJECTED_BUSY になって復帰できない。
        if self._deadline is not None and self.get_clock().now() > self._deadline:
            self._report(
                "FAILED_ACTION",
                "アクションが期限内に結果を返さなかった。受付を再開する",
            )
            self._release()
            return
        if self._plan_translation is None or self._goal_handle is None:
            return
        try:
            current = self._translation(
                self._buffer.lookup_transform(
                    self._base, self._expected_frame or "map", Time()
                )
            )
        except tf2_ros.TransformException:
            return
        drift = float(np.linalg.norm(current - self._plan_translation))
        if drift > self._drift_tolerance:
            self._report("ABORTED_BASE_MOVED", f"drift={drift:.3f}m")
            self._goal_handle.cancel_goal_async()
            self._plan_translation = None

    def _stow_cb(self, _request, response):
        """Move to a low folded pose. Call this BEFORE stopping the container:
        a graceful shutdown cuts torque and the arm falls."""
        if self._busy:
            response.success = False
            response.message = "リーチ実行中"
            return response
        missing = missing_joints(self._positions, self._arm_joints)
        if missing:
            response.success = False
            response.message = f"関節状態が不足: {missing}"
            return response
        # ★ stow も関節制限と joint_limit_overrides でクランプする。
        #   overrides の存在理由は「アームを LiDAR / カメラマウントに突っ込ませない」
        #   (laser_link と arm_mount_link は xy で 44.7mm しか離れていない) なのに、
        #   停止のたびに必ず実行される stow だけがその防御を迂回していた。
        #   チェーン未受信ならクランプできないので拒否する (fail-closed)。
        if self._chain is None:
            response.success = False
            response.message = "robot_description 未受信で関節制限を確認できない"
            return response
        if not self._client.wait_for_server(timeout_sec=2.0):
            response.success = False
            response.message = "アームのアクションサーバが無い"
            return response
        if not self._gripper_client.wait_for_server(timeout_sec=2.0):
            response.success = False
            response.message = "グリッパのアクションサーバが無い"
            return response
        start = np.array([self._positions[name] for name in self._arm_joints])
        positions = np.array(self._stow)
        margin = self._config.joint_limit_margin
        clamped = positions.copy()
        for index, (lower, upper) in enumerate(self._limits):
            clamped[index] = float(
                np.clip(positions[index], lower + margin, upper - margin)
            )
        if not np.allclose(clamped, positions):
            adjusted = [
                f"{name}: {before:.3f}->{after:.3f}"
                for name, before, after in zip(self._arm_joints, positions, clamped)
                if abs(before - after) > 1e-9
            ]
            self.get_logger().warn(f"stow_positions を制限内へ丸めた: {adjusted}")
        positions = clamped
        travel = float(np.max(np.abs(positions - start)))
        duration = min(
            self._max_duration, max(self._min_duration, travel / self._max_joint_speed)
        )
        self._report("STOW", f"dur={duration:.1f}")
        self._send_gripper(self._stow_gripper)
        self._send(positions, duration)
        response.success = True
        response.message = "stowing"
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ReachToPoint()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
