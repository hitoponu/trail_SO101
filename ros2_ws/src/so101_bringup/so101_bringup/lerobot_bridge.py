"""Thin ROS 2 bridge between ros2_control JointState topics and LeRobot."""

from __future__ import annotations

import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger

from .bridge_core import (
    ROS_JOINTS,
    CommandWatchdog,
    InvalidJointCommand,
    VelocityEstimator,
    gripper_limit_from_urdf,
    lerobot_to_ros,
    ordered_ros_positions,
    ros_to_lerobot,
)
from .lerobot_backend import LeRobotSO101Backend, MockSO101Backend


class SO101LeRobotBridge(Node):
    def __init__(self) -> None:
        super().__init__("lerobot_bridge")
        self.declare_parameter("backend", "mock")
        self.declare_parameter("usb_port", "/dev/so101_follower")
        self.declare_parameter("robot_id", "")
        self.declare_parameter(
            "calibration_dir",
            "/root/.cache/huggingface/lerobot/calibration/robots/so_follower",
        )
        self.declare_parameter("update_rate", 50.0)
        self.declare_parameter("command_timeout", 0.5)
        self.declare_parameter("robot_description", "")

        update_rate = float(self.get_parameter("update_rate").value)
        if update_rate <= 0:
            raise ValueError("update_rate must be positive")
        robot_description = str(self.get_parameter("robot_description").value)
        self._gripper_limit = gripper_limit_from_urdf(robot_description)
        self._watchdog = CommandWatchdog(
            float(self.get_parameter("command_timeout").value)
        )
        self._velocity = VelocityEstimator()
        self._command: dict[str, float] | None = None
        self._fault: Exception | None = None
        self._closed = False

        backend_name = str(self.get_parameter("backend").value)
        if backend_name == "mock":
            self._backend = MockSO101Backend()
        elif backend_name == "lerobot":
            self._backend = LeRobotSO101Backend(
                port=str(self.get_parameter("usb_port").value),
                robot_id=str(self.get_parameter("robot_id").value),
                calibration_dir=str(self.get_parameter("calibration_dir").value),
            )
        else:
            raise ValueError("backend must be either 'mock' or 'lerobot'")

        self._backend.connect()
        self._state_publisher = self.create_publisher(
            JointState, "/so101/hardware_states", qos_profile_sensor_data
        )
        self.create_subscription(
            JointState, "/so101/hardware_commands", self._command_callback, 1
        )
        self.create_service(Trigger, "/so101/lerobot_bridge/ready", self._ready)
        self.create_timer(1.0 / update_rate, self._control_cycle)
        self.get_logger().info(f"SO-101 bridge ready with backend={backend_name}")

    @property
    def faulted(self) -> bool:
        return self._fault is not None

    def _ready(self, _request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        response.success = not self.faulted
        response.message = "ready" if response.success else str(self._fault)
        return response

    def _command_callback(self, message: JointState) -> None:
        try:
            ordered = ordered_ros_positions(message.name, message.position)
            self._command = ros_to_lerobot(ordered, self._gripper_limit)
            self._watchdog.mark()
        except InvalidJointCommand as exc:
            self.get_logger().error(f"Rejected hardware command: {exc}")

    def _control_cycle(self) -> None:
        try:
            if self._watchdog.expired():
                raise TimeoutError("hardware command watchdog expired")
            if self._command is not None:
                self._backend.write_positions(self._command)
            ros_positions = lerobot_to_ros(
                self._backend.read_positions(), self._gripper_limit
            )
            velocities = self._velocity.update(ros_positions, time.monotonic())
            message = JointState()
            message.header.stamp = self.get_clock().now().to_msg()
            message.name = list(ROS_JOINTS)
            message.position = [ros_positions[name] for name in ROS_JOINTS]
            message.velocity = [velocities[name] for name in ROS_JOINTS]
            self._state_publisher.publish(message)
        except Exception as exc:  # noqa: BLE001 - any I/O error must safe-stop
            self._fault = exc
            self.get_logger().fatal(f"SO-101 bridge fault: {exc}")
            self.close()
            if rclpy.ok():
                rclpy.shutdown()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._backend.disconnect()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    exit_code = 0
    try:
        node = SO101LeRobotBridge()
        rclpy.spin(node)
        if node.faulted:
            exit_code = 1
    except Exception as exc:  # noqa: BLE001 - process boundary reports startup faults
        print(f"Failed to start SO-101 LeRobot bridge: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
