"""Translate base-frame XYZ velocity commands into SO-101 joint trajectories."""

from __future__ import annotations

import time

import numpy as np
import rclpy
from builtin_interfaces.msg import Duration
from geometry_msgs.msg import TwistStamped
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from so101_bringup.cartesian_math import (
    SerialChain,
    arm_target,
    damped_least_squares,
    missing_joints,
    validate_xyz_command,
)


ARM_JOINTS = [
    "shoulder_pan_joint",
    "shoulder_lift_joint",
    "elbow_flex_joint",
    "wrist_flex_joint",
    "wrist_roll_joint",
]
CONTROLLED_JOINTS = ARM_JOINTS[:-1]


class CartesianJog(Node):
    def __init__(self) -> None:
        super().__init__("so101_cartesian_jog")
        defaults = {
            "base_link": "base_link",
            "tip_link": "gripper_frame_link",
            "command_frame": "base_link",
            "command_topic": "/so101/cartesian_twist",
            "trajectory_topic": "/joint_trajectory_controller/joint_trajectory",
            "control_rate": 20.0,
            "trajectory_horizon": 0.10,
            "max_joint_velocity": 0.5,
            "joint_limit_margin": 0.10,
            "command_timeout": 0.20,
            "damping": 0.03,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

        self._base = str(self.get_parameter("base_link").value)
        self._tip = str(self.get_parameter("tip_link").value)
        self._frame = str(self.get_parameter("command_frame").value)
        self._horizon = float(self.get_parameter("trajectory_horizon").value)
        self._max_joint_velocity = float(self.get_parameter("max_joint_velocity").value)
        self._margin = float(self.get_parameter("joint_limit_margin").value)
        self._timeout = float(self.get_parameter("command_timeout").value)
        self._damping = float(self.get_parameter("damping").value)

        self._chain: SerialChain | None = None
        self._limits: list[tuple[float, float]] = []
        self._positions: dict[str, float] = {}
        self._velocity = np.zeros(3)
        self._last_command_monotonic: float | None = None
        self._holding = True
        self._warned_missing_state = False

        description_qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.create_subscription(String, "/robot_description", self._description_cb, description_qos)
        self.create_subscription(JointState, "/joint_states", self._joint_state_cb, 10)
        self.create_subscription(
            TwistStamped,
            str(self.get_parameter("command_topic").value),
            self._twist_cb,
            10,
        )
        self._trajectory_pub = self.create_publisher(
            JointTrajectory, str(self.get_parameter("trajectory_topic").value), 10
        )
        rate = float(self.get_parameter("control_rate").value)
        self._timer = self.create_timer(1.0 / rate, self._update)
        self.get_logger().info("Cartesian Jog は robot_description と joint_states を待っています")

    def _description_cb(self, message: String) -> None:
        if self._chain is not None:
            return
        try:
            chain = SerialChain.from_urdf(message.data, self._base, self._tip)
            limits = chain.limits(CONTROLLED_JOINTS)
            for name, (lower, upper) in zip(CONTROLLED_JOINTS, limits):
                if not np.isfinite([lower, upper]).all() or lower + self._margin >= upper - self._margin:
                    raise ValueError(f"{name} の可動範囲または余白が不正")
            self._chain = chain
            self._limits = limits
            self.get_logger().info(
                f"URDF チェーンを読み込みました: {self._base} -> {self._tip}"
            )
        except (ValueError, KeyError) as exc:
            self.get_logger().error(f"robot_description を使用できません: {exc}")

    def _joint_state_cb(self, message: JointState) -> None:
        self._positions.update(dict(zip(message.name, message.position)))

    def _twist_cb(self, message: TwistStamped) -> None:
        linear = np.array(
            [message.twist.linear.x, message.twist.linear.y, message.twist.linear.z],
            dtype=float,
        )
        angular = np.array(
            [message.twist.angular.x, message.twist.angular.y, message.twist.angular.z]
        )
        stamp = Time.from_msg(message.header.stamp)
        age = None
        if stamp.nanoseconds != 0:
            age = (self.get_clock().now() - stamp).nanoseconds / 1_000_000_000
        error = validate_xyz_command(
            message.header.frame_id,
            self._frame,
            linear,
            angular,
            age,
            self._timeout,
        )
        if error is not None:
            self.get_logger().warn(f"Twist を破棄: {error}", throttle_duration_sec=2.0)
            return
        self._velocity = linear
        self._last_command_monotonic = time.monotonic()

    def _ready_positions(self) -> np.ndarray | None:
        missing = missing_joints(self._positions, ARM_JOINTS)
        if self._chain is None or missing:
            if missing and not self._warned_missing_state:
                self.get_logger().warn(f"関節状態を待っています: {missing}")
                self._warned_missing_state = True
            return None
        self._warned_missing_state = False
        return np.array([self._positions[name] for name in ARM_JOINTS], dtype=float)

    def _publish_positions(self, positions: np.ndarray) -> None:
        message = JointTrajectory()
        message.header.stamp = self.get_clock().now().to_msg()
        message.joint_names = ARM_JOINTS
        point = JointTrajectoryPoint()
        point.positions = [float(value) for value in positions]
        seconds = int(self._horizon)
        point.time_from_start = Duration(
            sec=seconds, nanosec=int((self._horizon - seconds) * 1_000_000_000)
        )
        message.points = [point]
        self._trajectory_pub.publish(message)

    def _hold(self, positions: np.ndarray) -> None:
        if not self._holding:
            self._publish_positions(positions)
            self._holding = True

    def _update(self) -> None:
        positions = self._ready_positions()
        if positions is None:
            return
        stale = (
            self._last_command_monotonic is None
            or time.monotonic() - self._last_command_monotonic > self._timeout
        )
        if stale or np.allclose(self._velocity, 0.0, atol=1e-12):
            self._hold(positions)
            return

        assert self._chain is not None
        position_map = dict(zip(ARM_JOINTS, positions))
        try:
            _, jacobian = self._chain.position_and_jacobian(position_map, CONTROLLED_JOINTS)
            joint_velocity = damped_least_squares(
                jacobian, self._velocity, self._damping, self._max_joint_velocity
            )
            target = arm_target(
                positions,
                joint_velocity,
                self._horizon,
                self._limits,
                self._margin,
            )
            self._publish_positions(target)
            self._holding = False
        except (KeyError, ValueError, np.linalg.LinAlgError) as exc:
            self.get_logger().error(f"Cartesian Jog の計算に失敗: {exc}", throttle_duration_sec=2.0)
            self._hold(positions)

    def stop(self) -> None:
        positions = self._ready_positions()
        if positions is not None:
            self._holding = False
            self._hold(positions)


def main() -> None:
    rclpy.init()
    node = CartesianJog()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
