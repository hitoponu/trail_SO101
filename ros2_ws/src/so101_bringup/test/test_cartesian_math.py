import numpy as np

from so101_bringup.cartesian_math import (
    SerialChain,
    arm_target,
    bounded_target,
    damped_least_squares,
    missing_joints,
    validate_xyz_command,
    velocity_from_keys,
)


URDF = """
<robot name="test">
  <link name="base_link"/><link name="link1"/><link name="link2"/><link name="tip"/>
  <joint name="joint1" type="revolute">
    <parent link="base_link"/><child link="link1"/>
    <origin xyz="0 0 0" rpy="0 0 0"/><axis xyz="0 0 1"/>
    <limit lower="-2" upper="2" effort="1" velocity="1"/>
  </joint>
  <joint name="joint2" type="revolute">
    <parent link="link1"/><child link="link2"/>
    <origin xyz="1 0 0" rpy="0 0 0"/><axis xyz="0 0 1"/>
    <limit lower="-2" upper="2" effort="1" velocity="1"/>
  </joint>
  <joint name="tip_fixed" type="fixed">
    <parent link="link2"/><child link="tip"/><origin xyz="1 0 0" rpy="0 0 0"/>
  </joint>
</robot>
"""


def test_key_mapping_and_opposites():
    assert np.allclose(velocity_from_keys({"w"}, 0.02), [0.02, 0, 0])
    assert np.allclose(velocity_from_keys({"s"}, 0.02), [-0.02, 0, 0])
    assert np.allclose(velocity_from_keys({"a"}, 0.02), [0, 0.02, 0])
    assert np.allclose(velocity_from_keys({"d"}, 0.02), [0, -0.02, 0])
    assert np.allclose(velocity_from_keys({"r"}, 0.02), [0, 0, 0.02])
    assert np.allclose(velocity_from_keys({"f"}, 0.02), [0, 0, -0.02])
    assert np.allclose(velocity_from_keys({"w", "s"}, 0.02), np.zeros(3))


def test_diagonal_is_normalized():
    velocity = velocity_from_keys({"w", "a", "r"}, 0.02)
    assert np.isclose(np.linalg.norm(velocity), 0.02)
    assert np.allclose(velocity_from_keys(set(), 0.02), np.zeros(3))


def test_urdf_chain_fk_and_jacobian_match_finite_difference():
    chain = SerialChain.from_urdf(URDF, "base_link", "tip")
    positions = {"joint1": 0.3, "joint2": -0.4}
    point, jacobian = chain.position_and_jacobian(positions, ["joint1", "joint2"])
    epsilon = 1e-7
    for column, name in enumerate(["joint1", "joint2"]):
        shifted = positions.copy()
        shifted[name] += epsilon
        shifted_point, _ = chain.position_and_jacobian(shifted, ["joint1", "joint2"])
        assert np.allclose(jacobian[:, column], (shifted_point - point) / epsilon, atol=1e-6)
    assert chain.limits(["joint1", "joint2"]) == [(-2.0, 2.0), (-2.0, 2.0)]


def test_damped_least_squares_and_velocity_limit():
    jacobian = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]])
    velocity = damped_least_squares(jacobian, np.array([1.0, 2.0, 0.0]), 0.01, 0.5)
    assert np.max(np.abs(velocity)) <= 0.5
    assert velocity[1] > velocity[0] > 0.0


def test_bounded_target_respects_margin():
    target = bounded_target(
        np.array([0.95, -0.95]), np.array([1.0, -1.0]), 1.0,
        [(-1.0, 1.0), (-1.0, 1.0)], 0.1,
    )
    assert np.allclose(target, [0.9, -0.9])


def test_arm_target_preserves_wrist_roll():
    current = np.array([0.0, 0.0, 0.0, 0.0, 0.37])
    target = arm_target(current, np.ones(4), 0.1, [(-1.0, 1.0)] * 4, 0.1)
    assert np.allclose(target[:4], np.full(4, 0.1))
    assert target[4] == current[4]


def test_command_validation_rejects_invalid_inputs():
    zeros = np.zeros(3)
    assert validate_xyz_command("base_link", "base_link", zeros, zeros, 0.1, 0.2) is None
    assert "frame_id" in validate_xyz_command("tip", "base_link", zeros, zeros, 0.1, 0.2)
    assert "angular" in validate_xyz_command("base_link", "base_link", zeros, np.ones(3), 0.1, 0.2)
    assert "古い" in validate_xyz_command("base_link", "base_link", zeros, zeros, 0.3, 0.2)
    assert "非有限" in validate_xyz_command(
        "base_link", "base_link", np.array([np.nan, 0.0, 0.0]), zeros, 0.1, 0.2
    )


def test_missing_joint_detection():
    assert missing_joints({"joint1": 0.0}, ["joint1", "joint2"]) == ["joint2"]
