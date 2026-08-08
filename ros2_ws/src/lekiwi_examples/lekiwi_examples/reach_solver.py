"""Offline position IK for the SO-101, built entirely from cartesian_math.

Kept free of ROS imports so it can be unit tested without a ROS runtime.

The underlying solver (`damped_least_squares`) is velocity level, so reaching a
Cartesian point means iterating it to convergence *before* anything is
commanded. That is what makes "warn and do nothing" possible: unreachability is
decided offline, and the arm never moves for a target it cannot reach.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .cartesian_math import (
    ARM_JOINTS,
    CONTROLLED_JOINTS,
    SerialChain,
    arm_target,
    damped_least_squares,
    prefixed,
)

SOLVED = "SOLVED"
STALLED = "STALLED"
ITERATION_LIMIT = "ITERATION_LIMIT"


@dataclass(frozen=True)
class SolverConfig:
    """Tuning for `solve`. Distances are metres, angles radians."""

    tolerance: float = 0.005
    max_iterations: int = 200
    #: Largest Cartesian step taken per iteration; caps how far the linearised
    #: Jacobian is trusted.
    step: float = 0.02
    #: Largest joint step per iteration. This is `damped_least_squares`'s
    #: `max_joint_velocity` argument, which becomes a step because `solve`
    #: calls `arm_target` with horizon=1.0.
    max_joint_step: float = 0.10
    damping: float = 0.03
    joint_limit_margin: float = 0.10
    #: Residual improvement below this counts as "no progress".
    stall_tolerance: float = 1e-4
    #: Consecutive no-progress iterations before declaring unreachable.
    stall_patience: int = 10


@dataclass
class SolverResult:
    status: str
    positions: np.ndarray
    residual: float
    iterations: int
    #: Joints sitting on a limit at the final pose. The difference between
    #: "too far away" and "you need to rotate the base".
    pinned: list[str] = field(default_factory=list)

    @property
    def solved(self) -> bool:
        return self.status == SOLVED


def pinned_joints(
    positions: np.ndarray,
    joint_names: list[str],
    limits: list[tuple[float, float]],
    margin: float,
    epsilon: float = 1e-6,
) -> list[str]:
    """Names of joints resting on their clamped bound."""
    result = []
    for value, name, (lower, upper) in zip(positions, joint_names, limits):
        if value <= lower + margin + epsilon or value >= upper - margin - epsilon:
            result.append(name)
    return result


def solve(
    chain: SerialChain,
    start: np.ndarray,
    target: np.ndarray,
    limits: list[tuple[float, float]],
    config: SolverConfig = SolverConfig(),
    prefix: str = "",
) -> SolverResult:
    """Iterate the DLS solver toward `target`, expressed in the chain base frame.

    `start` is the five current arm joint positions in ARM_JOINTS order.
    `limits` are the four controlled joints' limits, from `chain.limits`.

    wrist_roll is deliberately frozen: `arm_target` preserves it. Its axis
    passes 8 mm from the tip, so freezing it costs a little reach but the
    remaining four joints still span three dimensions.
    """
    arm_names = prefixed(ARM_JOINTS, prefix)
    controlled_names = prefixed(CONTROLLED_JOINTS, prefix)

    positions = np.array(start, dtype=float)
    target = np.asarray(target, dtype=float)
    best = np.inf
    stall = 0
    residual = np.inf
    status = ITERATION_LIMIT
    iteration = 0

    for iteration in range(1, config.max_iterations + 1):
        tip, jacobian = chain.position_and_jacobian(
            dict(zip(arm_names, positions)), controlled_names
        )
        error = target - tip
        residual = float(np.linalg.norm(error))
        if residual < config.tolerance:
            status = SOLVED
            break

        if best - residual < config.stall_tolerance:
            stall += 1
            if stall >= config.stall_patience:
                status = STALLED
                break
        else:
            stall = 0
            best = residual

        # Cap the Cartesian step so the linearisation stays valid far from
        # the target; near it, take the whole remaining error.
        step = error * min(1.0, config.step / residual)
        joint_step = damped_least_squares(
            jacobian, step, config.damping, config.max_joint_step
        )
        positions = arm_target(
            positions, joint_step, 1.0, limits, config.joint_limit_margin
        )

    return SolverResult(
        status=status,
        positions=positions,
        residual=residual,
        iterations=iteration,
        pinned=(
            []
            if status == SOLVED
            else pinned_joints(
                positions[:4], controlled_names, limits, config.joint_limit_margin
            )
        ),
    )
