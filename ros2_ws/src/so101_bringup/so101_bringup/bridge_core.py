"""ROS/LeRobot unit conversion and validation without ROS dependencies."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from xml.etree import ElementTree

ROS_TO_LEROBOT = {
    "shoulder_pan_joint": "shoulder_pan",
    "shoulder_lift_joint": "shoulder_lift",
    "elbow_flex_joint": "elbow_flex",
    "wrist_flex_joint": "wrist_flex",
    "wrist_roll_joint": "wrist_roll",
    "gripper_joint": "gripper",
}
ROS_JOINTS = tuple(ROS_TO_LEROBOT)
LEROBOT_JOINTS = tuple(ROS_TO_LEROBOT.values())
BODY_ROS_JOINTS = ROS_JOINTS[:-1]


class InvalidJointCommand(ValueError):
    """Raised when an internal hardware command is incomplete or unsafe."""


@dataclass(frozen=True)
class JointLimit:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.lower) or not math.isfinite(self.upper):
            raise ValueError("joint limits must be finite")
        if self.lower >= self.upper:
            raise ValueError("joint lower limit must be smaller than upper limit")

    def clamp(self, value: float) -> float:
        return min(self.upper, max(self.lower, value))


def gripper_limit_from_urdf(robot_description: str, prefix: str = "") -> JointLimit:
    """Read the gripper operating range from the runtime robot description.

    `prefix` matches the xacro `prefix` argument, which the upstream macro
    applies to joint names as well as link names. Everything else in this
    module works in unprefixed canonical names; the prefix is stripped and
    reapplied at the ROS boundary in lerobot_bridge.
    """
    try:
        root = ElementTree.fromstring(robot_description)
    except ElementTree.ParseError as exc:
        raise ValueError("robot_description is not valid XML") from exc

    wanted = f"{prefix}gripper_joint"
    joint = next(
        (item for item in root.findall("joint") if item.get("name") == wanted),
        None,
    )
    if joint is None:
        raise ValueError(f"robot_description has no {wanted}")
    limit = joint.find("limit")
    if limit is None or limit.get("lower") is None or limit.get("upper") is None:
        raise ValueError("gripper_joint must have lower and upper limits")
    return JointLimit(float(limit.get("lower")), float(limit.get("upper")))


def ordered_ros_positions(names: Sequence[str], positions: Sequence[float]) -> dict[str, float]:
    """Validate a complete six-joint command and put it in canonical order."""
    if len(names) != len(positions):
        raise InvalidJointCommand("joint name and position lengths differ")
    if len(names) != len(ROS_JOINTS):
        raise InvalidJointCommand(f"expected {len(ROS_JOINTS)} joints, got {len(names)}")
    if len(set(names)) != len(names):
        raise InvalidJointCommand("joint names contain duplicates")
    unknown = set(names) - set(ROS_JOINTS)
    missing = set(ROS_JOINTS) - set(names)
    if unknown or missing:
        raise InvalidJointCommand(
            f"joint set mismatch: missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    values = dict(zip(names, positions, strict=True))
    if not all(math.isfinite(float(value)) for value in values.values()):
        raise InvalidJointCommand("joint positions must all be finite")
    return {name: float(values[name]) for name in ROS_JOINTS}


def ros_to_lerobot(
    positions: Mapping[str, float], gripper_limit: JointLimit
) -> dict[str, float]:
    """Convert ROS radians to LeRobot degrees and normalized gripper percent."""
    if set(positions) != set(ROS_JOINTS):
        raise InvalidJointCommand("a complete canonical ROS joint mapping is required")
    result = {
        ROS_TO_LEROBOT[name]: math.degrees(float(positions[name]))
        for name in BODY_ROS_JOINTS
    }
    gripper = gripper_limit.clamp(float(positions["gripper_joint"]))
    result["gripper"] = 100.0 * (gripper - gripper_limit.lower) / (
        gripper_limit.upper - gripper_limit.lower
    )
    return result


def lerobot_to_ros(
    positions: Mapping[str, float], gripper_limit: JointLimit
) -> dict[str, float]:
    """Convert a complete LeRobot observation to ROS joint positions."""
    if set(positions) != set(LEROBOT_JOINTS):
        missing = set(LEROBOT_JOINTS) - set(positions)
        unknown = set(positions) - set(LEROBOT_JOINTS)
        raise ValueError(
            f"LeRobot joint set mismatch: missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    if not all(math.isfinite(float(value)) for value in positions.values()):
        raise ValueError("LeRobot positions must all be finite")
    inverse = {lerobot: ros for ros, lerobot in ROS_TO_LEROBOT.items()}
    result = {
        inverse[name]: math.radians(float(positions[name]))
        for name in LEROBOT_JOINTS[:-1]
    }
    percent = min(100.0, max(0.0, float(positions["gripper"])))
    result["gripper_joint"] = gripper_limit.lower + percent / 100.0 * (
        gripper_limit.upper - gripper_limit.lower
    )
    return {name: result[name] for name in ROS_JOINTS}


class VelocityEstimator:
    """Finite-difference velocity estimator for position-only LeRobot observations."""

    def __init__(self) -> None:
        self._positions: dict[str, float] | None = None
        self._stamp: float | None = None

    def update(self, positions: Mapping[str, float], stamp: float) -> dict[str, float]:
        current = {name: float(positions[name]) for name in ROS_JOINTS}
        if self._positions is None or self._stamp is None or stamp <= self._stamp:
            velocity = dict.fromkeys(ROS_JOINTS, 0.0)
        else:
            dt = stamp - self._stamp
            velocity = {
                name: (current[name] - self._positions[name]) / dt for name in ROS_JOINTS
            }
        self._positions = current
        self._stamp = stamp
        return velocity


class CommandWatchdog:
    """A watchdog that is armed only after the first valid command."""

    def __init__(self, timeout: float, clock=time.monotonic) -> None:
        if timeout <= 0:
            raise ValueError("watchdog timeout must be positive")
        self.timeout = timeout
        self._clock = clock
        self._last_command: float | None = None

    def mark(self) -> None:
        self._last_command = self._clock()

    def expired(self) -> bool:
        return self._last_command is not None and self._clock() - self._last_command > self.timeout

