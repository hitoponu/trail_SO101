"""``lekiwi_base_bringup.raycast`` の単体テスト。

``fake_scan`` が出す ``/scan`` の正しさはここで決まる。距離が間違っていれば
SLAM は歪んだ地図を作り、Nav2 は存在しない壁を避ける。ROS なしで回せるので
Docker を立てる前にここを通しておく。

実行:
    cd ros2_ws/src/lekiwi_base_bringup
    uv run --no-project --with pytest --with numpy pytest test/ -v
"""

import math

import numpy as np
import pytest

from lekiwi_base_bringup import raycast as rc

# 5m x 4m の部屋 (中心が原点)
ROOM = (-2.5, -2.0, 2.5, 2.0)


@pytest.fixture
def empty_room() -> np.ndarray:
    return rc.build_world(ROOM)


def cast(segments, origin, angle_deg):
    """1 方向だけ撃って距離を返すヘルパ。"""
    angles = np.array([math.radians(angle_deg)])
    return float(rc.raycast(segments, np.asarray(origin, dtype=float), angles)[0])


# ── 世界の構築 ──────────────────────────────────────────────────────────


def test_rectangle_segments_is_closed_loop() -> None:
    """4 本の線分が端点を共有して閉じていること。"""
    segs = rc.rectangle_segments(0.0, 0.0, 1.0, 2.0)
    assert segs.shape == (4, 2, 2)
    for i in range(4):
        # i 本目の終点は i+1 本目の始点
        np.testing.assert_allclose(segs[i, 1], segs[(i + 1) % 4, 0])


@pytest.mark.parametrize(
    "args",
    [
        (1.0, 0.0, 1.0, 1.0),  # x が退化
        (0.0, 1.0, 1.0, 1.0),  # y が退化
        (1.0, 1.0, 0.0, 0.0),  # min > max
    ],
)
def test_rectangle_segments_rejects_degenerate(args) -> None:
    with pytest.raises(ValueError):
        rc.rectangle_segments(*args)


def test_build_world_counts_segments(empty_room) -> None:
    assert empty_room.shape == (4, 2, 2)
    with_obstacles = rc.build_world(ROOM, [0.8, -0.4, 1.2, 0.4, -1.5, 0.6, -1.0, 1.4])
    assert with_obstacles.shape == (12, 2, 2)  # 部屋 4 + 障害物 4 x 2


def test_build_world_rejects_ragged_obstacles() -> None:
    """4 の倍数でない障害物配列は起動時に弾く (黙って無視しない)。"""
    with pytest.raises(ValueError, match="4 の倍数"):
        rc.build_world(ROOM, [0.0, 0.0, 1.0])


# ── 距離の正しさ ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "angle_deg, expected",
    [
        (0.0, 2.5),  # +x の壁
        (180.0, 2.5),  # -x の壁
        (90.0, 2.0),  # +y の壁
        (-90.0, 2.0),  # -y の壁
    ],
)
def test_distance_to_walls_from_center(empty_room, angle_deg, expected) -> None:
    """部屋の中心から軸方向へ撃つと、壁までの距離がそのまま出る。"""
    assert cast(empty_room, (0.0, 0.0), angle_deg) == pytest.approx(expected)


def test_diagonal_hits_corner(empty_room) -> None:
    """角へ向かうレイは対角距離になる。

    5x4 の部屋の中心から角までは sqrt(2.5^2 + 2.0^2)。角の方向は atan2(2.0, 2.5)。
    """
    angle = math.degrees(math.atan2(2.0, 2.5))
    expected = math.hypot(2.5, 2.0)
    assert cast(empty_room, (0.0, 0.0), angle) == pytest.approx(expected)


def test_off_center_origin(empty_room) -> None:
    """原点以外からでも正しい距離が出る (origin の扱いのミスを検出する)。"""
    assert cast(empty_room, (1.0, 0.5), 0.0) == pytest.approx(1.5)
    assert cast(empty_room, (1.0, 0.5), 180.0) == pytest.approx(3.5)
    assert cast(empty_room, (1.0, 0.5), 90.0) == pytest.approx(1.5)
    assert cast(empty_room, (1.0, 0.5), -90.0) == pytest.approx(2.5)


def test_nearest_hit_wins() -> None:
    """障害物が壁より手前にあれば障害物の距離になる。"""
    world = rc.build_world(ROOM, [1.0, -0.5, 1.5, 0.5])
    # +x 方向: 壁は 2.5 だが障害物の手前の面が 1.0
    assert cast(world, (0.0, 0.0), 0.0) == pytest.approx(1.0)
    # 障害物を外した方向では壁まで届く
    assert cast(world, (0.0, 1.0), 0.0) == pytest.approx(2.5)


def test_ray_from_inside_obstacle_gap() -> None:
    """障害物の隙間を通り抜けて奥の壁に当たること。"""
    # y=0 に隙間を作る (障害物を y>0.2 と y<-0.2 に分ける)
    world = rc.build_world(ROOM, [1.0, 0.2, 1.5, 1.0, 1.0, -1.0, 1.5, -0.2])
    assert cast(world, (0.0, 0.0), 0.0) == pytest.approx(2.5)  # 隙間を通る
    assert cast(world, (0.0, 0.5), 0.0) == pytest.approx(1.0)  # 上の箱に当たる


# ── レイの向きと符号 ────────────────────────────────────────────────────


def test_backward_rays_are_not_counted(empty_room) -> None:
    """レイの後方 (t < 0) にある線分を拾わないこと。

    部屋の隅に寄せて外向きに撃つと、背後の壁までの距離が返ってはいけない。
    """
    # (2.0, 0.0) から +x を見る → 手前の壁 0.5。背後の壁 4.5 を拾ってはいけない。
    assert cast(empty_room, (2.0, 0.0), 0.0) == pytest.approx(0.5)


def test_rotation_shifts_pattern(empty_room) -> None:
    """センサを 90° 回すと、距離パターンが 90° 分ずれるだけであること。

    ``fake_scan`` は ``angles + yaw`` で向きを与えるので、ここが壊れると
    走行中に地図が回転して SLAM が発散する。
    """
    angles = rc.full_circle_angles(360)
    at_zero = rc.raycast(empty_room, np.zeros(2), angles)
    at_90 = rc.raycast(empty_room, np.zeros(2), angles + math.pi / 2.0)

    # 90° = 360 点中 90 点分のシフト
    np.testing.assert_allclose(at_90, np.roll(at_zero, -90), atol=1e-9)


# ── 当たらない方向 ──────────────────────────────────────────────────────


def test_outside_the_room_can_miss_entirely() -> None:
    """何にも当たらない方向は inf になる (0 ではない)。

    LaserScan で 0 は「距離 0 に障害物」と解釈されうるため、当たらないことを
    inf で表すのは重要。
    """
    box = rc.rectangle_segments(-0.5, -0.5, 0.5, 0.5)
    # 箱から離れた位置から、箱と反対方向へ撃つ
    assert cast(box, (5.0, 0.0), 0.0) == math.inf


def test_all_rays_hit_from_inside_a_closed_room(empty_room) -> None:
    """閉じた部屋の内側からは全方向必ず当たる (inf が出ない)。"""
    angles = rc.full_circle_angles(720)
    ranges = rc.raycast(empty_room, np.array([0.3, -0.7]), angles)
    assert np.all(np.isfinite(ranges))
    assert np.all(ranges > 0.0)
    # 部屋の外接対角より長い距離は出ないはず
    assert np.all(ranges <= math.hypot(5.0, 4.0) + 1e-9)


# ── 角度配列 ────────────────────────────────────────────────────────────


def test_full_circle_angles_no_duplicate_endpoint() -> None:
    """始点と終点が重複しないこと (重複すると 1 点だけ二重に出る)。"""
    angles = rc.full_circle_angles(360)
    assert len(angles) == 360
    assert angles[0] == pytest.approx(-math.pi)
    assert angles[-1] < math.pi
    increments = np.diff(angles)
    np.testing.assert_allclose(increments, 2.0 * math.pi / 360.0)


@pytest.mark.parametrize("samples", [0, 1, -5])
def test_full_circle_angles_rejects_too_few(samples) -> None:
    with pytest.raises(ValueError):
        rc.full_circle_angles(samples)


# ── 数値の頑健さ ────────────────────────────────────────────────────────


def test_parallel_ray_along_wall_does_not_crash(empty_room) -> None:
    """壁と平行なレイ (denom = 0) でゼロ除算警告を出さず、他の壁に当たること。"""
    with np.errstate(all="raise"):
        # y = 2.0 の壁の上を +x 方向へ。平行な壁は無視して +x の壁に当たる。
        d = cast(empty_room, (0.0, 2.0), 0.0)
    assert d == pytest.approx(2.5)


def test_no_nan_in_output(empty_room) -> None:
    """NaN が混ざらないこと。NaN は下流の costmap を静かに壊す。"""
    angles = rc.full_circle_angles(360)
    for origin in [(0.0, 0.0), (2.4999, 1.9999), (-2.4999, -1.9999), (0.0, 2.0)]:
        ranges = rc.raycast(empty_room, np.asarray(origin), angles)
        assert not np.any(np.isnan(ranges)), f"origin={origin} で NaN が出た"
