import json
import math

import pytest
from so101_bringup.bridge_core import (
    ROS_JOINTS,
    CommandWatchdog,
    InvalidJointCommand,
    JointLimit,
    VelocityEstimator,
    gripper_limit_from_urdf,
    lerobot_to_ros,
    ordered_ros_positions,
    ros_to_lerobot,
)
from so101_bringup.lerobot_backend import LeRobotSO101Backend, MockSO101Backend


def test_gripper_limit_is_read_from_robot_description():
    description = """<robot><joint name="gripper_joint" type="revolute">
      <limit lower="-0.1" upper="1.7" effort="1" velocity="1"/>
    </joint></robot>"""
    assert gripper_limit_from_urdf(description) == JointLimit(-0.1, 1.7)


def test_ros_lerobot_round_trip():
    limit = JointLimit(-0.1, 1.7)
    ros = dict(zip(ROS_JOINTS, [0.1, -0.2, 0.3, -0.4, 0.5, 0.8], strict=True))
    lerobot = ros_to_lerobot(ros, limit)
    assert lerobot["shoulder_pan"] == pytest.approx(math.degrees(0.1))
    assert lerobot["gripper"] == pytest.approx(50.0)
    assert lerobot_to_ros(lerobot, limit) == pytest.approx(ros)


def test_gripper_commands_are_clamped_to_urdf_limit():
    limit = JointLimit(0.0, 1.0)
    ros = dict.fromkeys(ROS_JOINTS, 0.0)
    ros["gripper_joint"] = 5.0
    assert ros_to_lerobot(ros, limit)["gripper"] == 100.0


@pytest.mark.parametrize(
    "names,positions",
    [
        (ROS_JOINTS[:-1], [0.0] * 5),
        (ROS_JOINTS, [0.0] * 5),
        (ROS_JOINTS[:-1] + (ROS_JOINTS[0],), [0.0] * 6),
        (ROS_JOINTS, [0.0] * 5 + [math.nan]),
    ],
)
def test_invalid_joint_commands_are_rejected(names, positions):
    with pytest.raises(InvalidJointCommand):
        ordered_ros_positions(names, positions)


def test_velocity_estimator_uses_position_difference():
    estimator = VelocityEstimator()
    initial = dict.fromkeys(ROS_JOINTS, 0.0)
    assert estimator.update(initial, 10.0) == dict.fromkeys(ROS_JOINTS, 0.0)
    moved = dict(initial)
    moved["shoulder_pan_joint"] = 0.5
    velocity = estimator.update(moved, 10.5)
    assert velocity["shoulder_pan_joint"] == pytest.approx(1.0)


def test_watchdog_arms_on_first_command():
    now = [0.0]
    watchdog = CommandWatchdog(0.5, clock=lambda: now[0])
    now[0] = 10.0
    assert not watchdog.expired()
    watchdog.mark()
    now[0] += 0.49
    assert not watchdog.expired()
    now[0] += 0.02
    assert watchdog.expired()


def test_mock_backend_follows_commands_and_disconnects():
    backend = MockSO101Backend()
    backend.connect()
    command = {
        "shoulder_pan": 1.0,
        "shoulder_lift": 2.0,
        "elbow_flex": 3.0,
        "wrist_flex": 4.0,
        "wrist_roll": 5.0,
        "gripper": 6.0,
    }
    backend.write_positions(command)
    assert backend.read_positions() == command
    backend.disconnect()
    with pytest.raises(RuntimeError):
        backend.read_positions()


def test_mock_backend_transitions_to_io_fault():
    backend = MockSO101Backend()
    backend.connect()
    backend.inject_fault(OSError("simulated serial disconnect"))
    with pytest.raises(OSError, match="simulated serial disconnect"):
        backend.read_positions()


def test_lerobot_backend_validates_calibration_before_importing_lerobot(tmp_path):
    calibration = {
        name: {
            "id": index,
            "drive_mode": 0,
            "homing_offset": 0,
            "range_min": 0,
            "range_max": 4095,
        }
        for index, name in enumerate(
            [
                "shoulder_pan",
                "shoulder_lift",
                "elbow_flex",
                "wrist_flex",
                "wrist_roll",
                "gripper",
            ],
            start=1,
        )
    }
    (tmp_path / "arm.json").write_text(json.dumps(calibration))
    backend = LeRobotSO101Backend("/dev/null", "arm", str(tmp_path))
    assert backend.calibration_file == tmp_path / "arm.json"


def test_lerobot_backend_rejects_missing_calibration(tmp_path):
    with pytest.raises(FileNotFoundError):
        LeRobotSO101Backend("/dev/null", "missing", str(tmp_path))


def test_pinned_lerobot_exports_so101_runtime_classes():
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    assert SO101Follower is not None
    assert SO101FollowerConfig is not None
