"""Pure kinematics and Cartesian-jog helpers for the SO-101 arm."""

from __future__ import annotations

from dataclasses import dataclass
import math
import xml.etree.ElementTree as ET

import numpy as np


KEY_DIRECTIONS = {
    "w": np.array([1.0, 0.0, 0.0]),
    "s": np.array([-1.0, 0.0, 0.0]),
    "a": np.array([0.0, 1.0, 0.0]),
    "d": np.array([0.0, -1.0, 0.0]),
    "r": np.array([0.0, 0.0, 1.0]),
    "f": np.array([0.0, 0.0, -1.0]),
}


def velocity_from_keys(pressed: set[str], speed: float) -> np.ndarray:
    """Return a constant-magnitude XYZ velocity for the currently pressed keys."""
    direction = sum(
        (KEY_DIRECTIONS[key] for key in pressed if key in KEY_DIRECTIONS),
        start=np.zeros(3),
    )
    norm = float(np.linalg.norm(direction))
    return direction * (speed / norm) if norm > 0.0 else direction


def _numbers(text: str | None, default: tuple[float, ...]) -> np.ndarray:
    if text is None:
        return np.array(default, dtype=float)
    return np.array([float(value) for value in text.split()], dtype=float)


def rotation_from_rpy(rpy: np.ndarray) -> np.ndarray:
    """Return the URDF fixed-axis roll/pitch/yaw rotation matrix."""
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ]
    )


def rotation_about_axis(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    skew = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    return np.eye(3) + math.sin(angle) * skew + (1.0 - math.cos(angle)) * (skew @ skew)


def transform(rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
    result = np.eye(4)
    result[:3, :3] = rotation
    result[:3, 3] = translation
    return result


@dataclass(frozen=True)
class Joint:
    name: str
    parent: str
    child: str
    joint_type: str
    xyz: np.ndarray
    rpy: np.ndarray
    axis: np.ndarray
    lower: float
    upper: float


class SerialChain:
    """Minimal URDF serial-chain model supporting fixed and revolute joints."""

    def __init__(self, joints: list[Joint]) -> None:
        self.joints = joints
        self.by_name = {joint.name: joint for joint in joints}

    @classmethod
    def from_urdf(cls, xml: str, base_link: str, tip_link: str) -> "SerialChain":
        root = ET.fromstring(xml)
        by_child: dict[str, Joint] = {}
        for element in root.findall("joint"):
            joint_type = element.attrib["type"]
            if joint_type not in {"fixed", "revolute", "continuous"}:
                continue
            origin = element.find("origin")
            axis = element.find("axis")
            limit = element.find("limit")
            lower = -math.inf
            upper = math.inf
            if joint_type == "revolute" and limit is not None:
                lower = float(limit.attrib["lower"])
                upper = float(limit.attrib["upper"])
            joint = Joint(
                name=element.attrib["name"],
                parent=element.find("parent").attrib["link"],
                child=element.find("child").attrib["link"],
                joint_type=joint_type,
                xyz=_numbers(origin.attrib.get("xyz") if origin is not None else None, (0, 0, 0)),
                rpy=_numbers(origin.attrib.get("rpy") if origin is not None else None, (0, 0, 0)),
                axis=_numbers(axis.attrib.get("xyz") if axis is not None else None, (1, 0, 0)),
                lower=lower,
                upper=upper,
            )
            by_child[joint.child] = joint

        chain: list[Joint] = []
        link = tip_link
        visited = set()
        while link != base_link:
            if link in visited or link not in by_child:
                raise ValueError(f"URDF に {base_link} から {tip_link} への直列チェーンがない")
            visited.add(link)
            joint = by_child[link]
            chain.append(joint)
            link = joint.parent
        chain.reverse()
        return cls(chain)

    def position_and_jacobian(
        self, positions: dict[str, float], controlled_joints: list[str]
    ) -> tuple[np.ndarray, np.ndarray]:
        current = np.eye(4)
        origins: dict[str, np.ndarray] = {}
        axes: dict[str, np.ndarray] = {}
        controlled = set(controlled_joints)

        for joint in self.joints:
            current = current @ transform(rotation_from_rpy(joint.rpy), joint.xyz)
            if joint.joint_type != "fixed":
                if joint.name not in positions:
                    raise KeyError(f"関節状態がない: {joint.name}")
                if joint.name in controlled:
                    origins[joint.name] = current[:3, 3].copy()
                    axes[joint.name] = current[:3, :3] @ joint.axis
                current = current @ transform(
                    rotation_about_axis(joint.axis, positions[joint.name]), np.zeros(3)
                )

        tip = current[:3, 3].copy()
        missing = [name for name in controlled_joints if name not in origins]
        if missing:
            raise ValueError(f"制御関節がチェーンにない: {missing}")
        jacobian = np.column_stack(
            [np.cross(axes[name], tip - origins[name]) for name in controlled_joints]
        )
        return tip, jacobian

    def limits(self, joint_names: list[str]) -> list[tuple[float, float]]:
        return [(self.by_name[name].lower, self.by_name[name].upper) for name in joint_names]


def damped_least_squares(
    jacobian: np.ndarray,
    cartesian_velocity: np.ndarray,
    damping: float,
    max_joint_velocity: float,
) -> np.ndarray:
    """Map XYZ velocity to bounded joint velocity using damped least squares."""
    lhs = jacobian @ jacobian.T + (damping * damping) * np.eye(3)
    joint_velocity = jacobian.T @ np.linalg.solve(lhs, cartesian_velocity)
    peak = float(np.max(np.abs(joint_velocity), initial=0.0))
    if peak > max_joint_velocity:
        joint_velocity *= max_joint_velocity / peak
    return joint_velocity


def bounded_target(
    current: np.ndarray,
    joint_velocity: np.ndarray,
    horizon: float,
    limits: list[tuple[float, float]],
    margin: float,
) -> np.ndarray:
    target = current + joint_velocity * horizon
    for index, (lower, upper) in enumerate(limits):
        target[index] = np.clip(target[index], lower + margin, upper - margin)
    return target


def arm_target(
    current: np.ndarray,
    controlled_velocity: np.ndarray,
    horizon: float,
    controlled_limits: list[tuple[float, float]],
    margin: float,
) -> np.ndarray:
    """Build a five-joint target while preserving the wrist-roll position."""
    if current.shape != (5,) or controlled_velocity.shape != (4,):
        raise ValueError("current は5要素、controlled_velocity は4要素であること")
    target = current.copy()
    target[:4] = bounded_target(
        current[:4], controlled_velocity, horizon, controlled_limits, margin
    )
    target[4] = current[4]
    return target


def validate_xyz_command(
    frame_id: str,
    expected_frame: str,
    linear: np.ndarray,
    angular: np.ndarray,
    age: float | None,
    timeout: float,
) -> str | None:
    """Return an error description, or None when a Cartesian command is valid."""
    if frame_id != expected_frame:
        return f"frame_id={frame_id!r}, 期待値={expected_frame!r}"
    if not np.allclose(angular, 0.0, atol=1e-12):
        return "angular 成分は未対応"
    if age is None or age > timeout:
        return "timestamp が無いか古い"
    if not np.isfinite(linear).all():
        return "非有限値を含む"
    return None


def missing_joints(positions: dict[str, float], required: list[str]) -> list[str]:
    """List required joints absent from a JointState-derived position map."""
    return [name for name in required if name not in positions]
