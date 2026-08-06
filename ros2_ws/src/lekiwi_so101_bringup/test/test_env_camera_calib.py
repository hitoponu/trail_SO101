"""環境固定カメラ較正の数学部分のテスト。ROS ランタイム不要。

較正は実機の往復が高コストなので、数学が正しいことを Mac 側で固めておく。
"""

import math

import numpy as np
import pytest

from lekiwi_so101_bringup import icp2d
from lekiwi_so101_bringup.gravity import (
    G,
    gravity_health,
    level_points,
    roll_pitch_from_samples,
    roll_pitch_from_up,
    rotation_rpy,
)


# --------------------------------------------------------------- gravity

def test_level_camera_gives_zero_roll_pitch():
    roll, pitch = roll_pitch_from_up([0.0, 0.0, 1.0])
    assert roll == pytest.approx(0.0)
    assert pitch == pytest.approx(0.0)


@pytest.mark.parametrize("roll,pitch", [
    (0.0, 0.3), (0.2, 0.0), (-0.4, 0.25), (0.1, -0.5), (0.0, 0.0),
])
def test_roll_pitch_round_trip(roll, pitch):
    """既知の姿勢から重力を合成し、復元できるか。"""
    # world の上向き (0,0,1) をセンサ座標へ持ってくる = R^T @ up
    up_in_sensor = rotation_rpy(roll, pitch, 0.0).T @ np.array([0.0, 0.0, 1.0])
    got_roll, got_pitch = roll_pitch_from_up(up_in_sensor)
    assert got_roll == pytest.approx(roll, abs=1e-9)
    assert got_pitch == pytest.approx(pitch, abs=1e-9)


def test_yaw_does_not_affect_roll_pitch():
    """★ 重力は鉛直軸まわりの回転に不変。yaw を変えても roll/pitch は動かない。"""
    roll, pitch = 0.15, -0.35
    first = None
    for yaw in (0.0, 1.0, -2.5, math.pi):
        up = rotation_rpy(roll, pitch, yaw).T @ np.array([0.0, 0.0, 1.0])
        got = roll_pitch_from_up(up)
        if first is None:
            first = got
        assert got[0] == pytest.approx(first[0], abs=1e-9)
        assert got[1] == pytest.approx(first[1], abs=1e-9)


def test_samples_average_out_noise():
    rng = np.random.default_rng(0)
    roll, pitch = 0.05, 0.42
    up = rotation_rpy(roll, pitch, 0.0).T @ np.array([0.0, 0.0, 1.0])
    samples = G * up + rng.normal(0.0, 0.05, size=(400, 3))
    got_roll, got_pitch = roll_pitch_from_samples(samples)
    assert got_roll == pytest.approx(roll, abs=0.01)
    assert got_pitch == pytest.approx(pitch, abs=0.01)


def test_gravity_health_accepts_static_samples():
    up = rotation_rpy(0.1, 0.2, 0.0).T @ np.array([0.0, 0.0, 1.0])
    ok, message = gravity_health(G * up + np.zeros((50, 3)))
    assert ok, message


def test_gravity_health_rejects_wrong_magnitude():
    """★ 加速度計が無効 / 単位違い / 動いている、を較正前に捕まえる。"""
    ok, message = gravity_health(np.tile([0.0, 0.0, 1.0], (50, 1)))
    assert not ok
    assert "重力" in message


def test_gravity_health_rejects_moving_camera():
    rng = np.random.default_rng(1)
    samples = np.array([0.0, 0.0, G]) + rng.normal(0.0, 3.0, size=(200, 3))
    ok, _ = gravity_health(samples)
    assert not ok


def test_level_points_makes_vertical_wall_vertical():
    """傾いたカメラで見た鉛直な壁が、水平化後に鉛直になる。"""
    roll, pitch = 0.2, -0.35
    wall = np.column_stack([
        np.full(50, 2.0), np.linspace(-1, 1, 50), np.linspace(0, 1.5, 50),
    ])
    tilted = wall @ rotation_rpy(roll, pitch, 0.0)          # センサ座標へ
    levelled = level_points(tilted, roll, pitch)
    assert np.allclose(levelled, wall, atol=1e-9)


# ----------------------------------------------------------------- icp2d

def _room(n=400):
    """4m x 3m の部屋の壁を点で表したもの。"""
    rng = np.random.default_rng(7)
    xs = rng.uniform(-2, 2, n)
    ys = rng.uniform(-1.5, 1.5, n)
    return np.vstack([
        np.column_stack([xs, np.full(n, -1.5)]),
        np.column_stack([xs, np.full(n, 1.5)]),
        np.column_stack([np.full(n, -2.0), ys]),
        np.column_stack([np.full(n, 2.0), ys]),
    ])


def test_kabsch2d_recovers_known_transform():
    rng = np.random.default_rng(3)
    source = rng.uniform(-1, 1, size=(30, 2))
    truth = (0.7, -0.3, 0.6)
    target = icp2d.transform2d(source, *truth)
    got = icp2d.kabsch2d(source, target)
    assert got == pytest.approx(truth, abs=1e-9)


def test_icp_recovers_pose_from_rough_initial():
    truth = (0.35, -0.22, 0.18)
    room = _room()
    # カメラが見ている壁（= 真の変換の逆を掛けたもの）
    observed = icp2d.transform2d(room, *_inverse(truth))
    result = icp2d.match(observed, room, initial=(0.2, -0.1, 0.1))
    assert result.converged
    assert result.residual < 0.01
    assert (result.x, result.y) == pytest.approx(truth[:2], abs=0.02)
    assert result.yaw == pytest.approx(truth[2], abs=0.02)


def test_icp_is_robust_to_objects_absent_from_the_map():
    """★ 机や椅子など「カメラには見えるが地図に無いもの」に引きずられない。"""
    rng = np.random.default_rng(11)
    truth = (0.3, 0.15, -0.12)
    room = _room()
    observed = icp2d.transform2d(room, *_inverse(truth))
    # 部屋の真ん中に地図に無い塊を足す（全点の 30%）
    clutter = rng.uniform(-0.6, 0.6, size=(len(observed) * 3 // 10, 2))
    polluted = np.vstack([observed, icp2d.transform2d(clutter, *_inverse(truth))])

    result = icp2d.match(polluted, room, initial=(0.2, 0.1, -0.05), trim_ratio=0.6)
    assert (result.x, result.y) == pytest.approx(truth[:2], abs=0.03)
    assert result.yaw == pytest.approx(truth[2], abs=0.03)


def test_icp_reports_low_inlier_ratio_when_it_does_not_fit():
    """合っていないことが inlier_ratio と residual に出る（黙って嘘をつかない）。"""
    rng = np.random.default_rng(13)
    noise = rng.uniform(-5, 5, size=(300, 2))
    result = icp2d.match(noise, _room(), initial=(0.0, 0.0, 0.0))
    assert result.residual > 0.05 or result.inlier_ratio < 0.5


def test_occupied_cells_maps_indices_to_metric_coordinates():
    grid = np.zeros((4, 3), dtype=np.int16)
    grid[1, 2] = 100          # row=1, col=2
    cells = icp2d.occupied_cells(
        grid.ravel(), width=3, height=4, resolution=0.05,
        origin_x=-1.0, origin_y=-2.0,
    )
    assert cells.shape == (1, 2)
    assert cells[0] == pytest.approx([-1.0 + 2.5 * 0.05, -2.0 + 1.5 * 0.05])


def test_slice_horizontal_selects_the_band():
    points = np.array([[0, 0, 0.0], [1, 1, 0.5], [2, 2, 1.0]])
    got = icp2d.slice_horizontal(points, 0.4, 0.6)
    assert got.shape == (1, 2)
    assert got[0] == pytest.approx([1.0, 1.0])


def test_slice_is_height_invariant_for_vertical_walls():
    """★ 壁が鉛直なら、どの高さで切っても同じ 2D 形になる。

    これが「2D マッチングでは z が決まらない」ことの数学的な理由であり、
    z を実測する根拠でもある。
    """
    footprint = _room(50)
    cloud = np.vstack([
        np.column_stack([footprint, np.full(len(footprint), h)])
        for h in (0.1, 0.5, 1.2)
    ])
    low = icp2d.slice_horizontal(cloud, 0.05, 0.15)
    high = icp2d.slice_horizontal(cloud, 1.15, 1.25)
    assert np.allclose(np.sort(low, axis=0), np.sort(high, axis=0))


def test_result_is_always_finite():
    """★ 較正値が inf/nan のまま static TF に流れると TF ツリー全体が壊れる。

    Mac の pytest では matmul が RuntimeWarning を出すが、それは Accelerate BLAS が
    フラグを誤って立てるだけで値は健全（icp2d の docstring 参照）。ここで
    値そのものを検査しておけば、本物の発散が起きたときには捕まる。
    """
    rng = np.random.default_rng(17)
    room = _room()
    for _ in range(5):
        source = rng.uniform(-8, 8, size=(200, 2))
        initial = tuple(rng.uniform(-3, 3, size=3))
        result = icp2d.match(source, room, initial=initial)
        assert all(math.isfinite(v) for v in result.as_tuple()) or not result.converged
        if result.converged:
            assert math.isfinite(result.residual)


def _inverse(pose):
    x, y, yaw = pose
    c, s = math.cos(-yaw), math.sin(-yaw)
    return (-(c * x - s * y), -(s * x + c * y), -yaw)
