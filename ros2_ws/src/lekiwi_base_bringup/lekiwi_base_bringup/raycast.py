"""2D レイキャストの幾何。``fake_scan`` が仮想 LiDAR を作るのに使う。

``kinematics.py`` と同じ方針で **numpy にしか依存しない**。ROS 2 を入れていない
ホストでも単体テストできるよう、rclpy を import する ``fake_scan.py`` から
幾何だけを切り離してある。

世界は軸平行な矩形の集まり (部屋の壁 + 障害物) を線分に展開して表す。線分の配列は
形が ``(線分数, 2, 2)`` = ``(線分, 端点 A/B, xy)``。
"""

from __future__ import annotations

import numpy as np

#: 平行判定のしきい値。これ未満の外積はレイと線分が平行とみなす。
PARALLEL_EPS = 1e-12


def rectangle_segments(
    min_x: float, min_y: float, max_x: float, max_y: float
) -> np.ndarray:
    """軸平行な矩形を 4 本の線分にする。戻り値の形は ``(4, 2, 2)``。"""
    if max_x <= min_x or max_y <= min_y:
        raise ValueError(
            f"max は min より大きい必要がある: x {min_x}..{max_x}, y {min_y}..{max_y}"
        )
    corners = np.array(
        [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]], dtype=float
    )
    return np.stack([corners, np.roll(corners, -1, axis=0)], axis=1)


def build_world(
    room: tuple[float, float, float, float],
    obstacles_flat: list[float] | None = None,
) -> np.ndarray:
    """部屋 + 障害物を線分の配列にまとめる。

    ``obstacles_flat`` は 4 要素ずつ ``(min_x, min_y, max_x, max_y)`` を並べた
    平坦な配列 (ROS パラメータが入れ子の配列を扱えないため)。
    """
    parts = [rectangle_segments(*room)]

    flat = list(obstacles_flat or [])
    if len(flat) % 4 != 0:
        raise ValueError(
            "obstacles は 4 の倍数の要素数が必要 "
            f"(min_x, min_y, max_x, max_y の繰り返し): {len(flat)}"
        )
    for i in range(0, len(flat), 4):
        parts.append(rectangle_segments(*(float(v) for v in flat[i : i + 4])))

    return np.concatenate(parts, axis=0)


def raycast(
    segments: np.ndarray, origin: np.ndarray, angles: np.ndarray
) -> np.ndarray:
    """``origin`` から ``angles`` 方向へレイを飛ばし、各方向の距離 [m] を返す。

    どの線分にも当たらない方向は ``inf``。``angles`` は世界座標での絶対角
    (センサの向きは呼び出し側で足しておく)。

    ray:     ``P = O + t*D``          (``t >= 0``)
    segment: ``Q = A + u*(B - A)``    (``0 <= u <= 1``)
    を外積で解く。``t = cross(ao, seg) / cross(D, seg)``,
    ``u = cross(ao, D) / cross(D, seg)`` で分母が共通なので、
    レイ (R 本) × 線分 (S 本) を (R, S) の配列 1 枚でまとめて処理できる。
    """
    directions = np.stack([np.cos(angles), np.sin(angles)], axis=1)  # (R, 2)

    a = segments[:, 0, :]  # (S, 2)
    seg = segments[:, 1, :] - a  # (S, 2)
    ao = a - np.asarray(origin, dtype=float)  # (S, 2)

    denom = np.outer(directions[:, 0], seg[:, 1]) - np.outer(
        directions[:, 1], seg[:, 0]
    )  # (R, S)
    t_num = ao[:, 0] * seg[:, 1] - ao[:, 1] * seg[:, 0]  # (S,)
    u_num = np.outer(directions[:, 1], ao[:, 0]) - np.outer(
        directions[:, 0], ao[:, 1]
    )  # (R, S)

    with np.errstate(divide="ignore", invalid="ignore"):
        t = t_num[None, :] / denom
        u = u_num / denom

    # 平行 (denom≒0)、レイの後方 (t<0)、線分の外 (u∉[0,1]) を除外する。
    # 除外したものを inf にしておけば min で自然に落ちる。
    valid = (
        (np.abs(denom) > PARALLEL_EPS)
        & np.isfinite(t)
        & np.isfinite(u)
        & (t >= 0.0)
        & (u >= 0.0)
        & (u <= 1.0)
    )
    return np.where(valid, t, np.inf).min(axis=1)


def full_circle_angles(samples: int) -> np.ndarray:
    """全周を等間隔に分割した角度配列 [rad]。

    終端は始点と重複するので含めない (``endpoint=False``)。LaserScan の
    ``angle_min`` / ``angle_max`` / ``angle_increment`` はこの配列から導く。
    """
    if samples < 2:
        raise ValueError(f"samples は 2 以上が必要: {samples}")
    return np.linspace(-np.pi, np.pi, samples, endpoint=False)
