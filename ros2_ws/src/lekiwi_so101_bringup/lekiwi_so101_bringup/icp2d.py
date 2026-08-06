"""占有格子に対する 2D の剛体マッチング（trimmed ICP）。

環境固定カメラの較正で、重力で水平化した点群を水平スライスして得た 2D 点を、
slam_toolbox が作った占有格子の占有セルへ合わせ、x / y / yaw を求める。

★ z は決められない。壁は鉛直なので、どの高さで切っても footprint が同じで、
  2D マッチングは z に対して原理的に縮退している。z は実測する。

★ 外れ値の除去（trimming）が必須。カメラには見えるが LiDAR の地図に無いもの
  （机の天板、椅子、人）が必ず混ざる。素の ICP はそれに引きずられる。

ROS 非依存の純 numpy（scipy はイメージに入っていない）。Mac で pytest できる。

★ Mac で pytest すると matmul から "divide by zero" 等の RuntimeWarning が出るが、
  これは **macOS の Accelerate BLAS が浮動小数点フラグを誤って立てる**もので、
  入力にも出力にも inf/nan は無い。実機と同じ Linux コンテナ (OpenBLAS) では出ない。
      np.ones((1600, 2)) @ np.eye(2)   # Mac: 警告が出る / Linux: 出ない
  警告を握りつぶすと**本物の inf/nan を見逃す**ので、代わりに match() が
  結果の有限性を明示的に検査する。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class MatchResult:
    x: float
    y: float
    yaw: float
    #: インライアのみの RMS 残差 [m]
    residual: float
    #: 使われた点の割合。低いと「合っていない」か「外れ値だらけ」
    inlier_ratio: float
    iterations: int
    converged: bool

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.yaw)


def transform2d(points, x: float, y: float, yaw: float) -> np.ndarray:
    """2D 点群を回転 yaw → 並進 (x, y) で移す。"""
    array = np.asarray(points, dtype=float)
    c, s = math.cos(yaw), math.sin(yaw)
    rotation = np.array([[c, -s], [s, c]])
    return array @ rotation.T + np.array([x, y])


def kabsch2d(source, target) -> tuple[float, float, float]:
    """対応済みの 2D 点対から剛体変換 (x, y, yaw) を最小二乗で求める。

    source を移して target に重ねる変換を返す。
    """
    a = np.asarray(source, dtype=float)
    b = np.asarray(target, dtype=float)
    if a.shape != b.shape or a.ndim != 2 or a.shape[1] != 2:
        raise ValueError("source と target は同じ形の (N, 2) であること")
    if len(a) < 2:
        raise ValueError("2 点以上必要")

    ca, cb = a.mean(axis=0), b.mean(axis=0)
    da, db = a - ca, b - cb
    # 2D なので SVD を使わずに閉形式で解ける。
    #   yaw = atan2( Σ(x_a·y_b − y_a·x_b), Σ(x_a·x_b + y_a·y_b) )
    numerator = float(np.sum(da[:, 0] * db[:, 1] - da[:, 1] * db[:, 0]))
    denominator = float(np.sum(da[:, 0] * db[:, 0] + da[:, 1] * db[:, 1]))
    yaw = math.atan2(numerator, denominator)
    c, s = math.cos(yaw), math.sin(yaw)
    rotated = np.array([c * ca[0] - s * ca[1], s * ca[0] + c * ca[1]])
    translation = cb - rotated
    return float(translation[0]), float(translation[1]), yaw


def _nearest(source, target) -> tuple[np.ndarray, np.ndarray]:
    """総当たりの最近傍。scipy が無いので numpy で書く。

    地図の占有セルは数千点、スライスした点群も間引いて数千点なので、
    数千×数千の距離行列（数十 MB）で十分収まる。
    """
    diff = source[:, None, :] - target[None, :, :]
    distances = np.einsum("ijk,ijk->ij", diff, diff)
    index = np.argmin(distances, axis=1)
    return index, np.sqrt(distances[np.arange(len(source)), index])


def match(
    source,
    target,
    initial=(0.0, 0.0, 0.0),
    *,
    max_iterations: int = 60,
    trim_ratio: float = 0.7,
    max_correspondence: float = 0.5,
    tolerance: float = 1e-5,
) -> MatchResult:
    """trimmed ICP。source（カメラ）を target（地図の占有セル）へ合わせる。

    `initial` は手実測や RViz の目視から与える粗い初期値。
    **大域探索はしない。** 三脚の位置はおおよそ分かるので局所最適化で足り、
    大域探索を入れると「それらしいが間違った解」に落ちたときに気付きにくい。

    trim_ratio: 残差の小さいほうから何割を使うか。カメラには見えるが地図に
                無いもの（机・椅子・人）を落とすために必須。
    max_correspondence: この距離を超える対応は初めから捨てる [m]。
    """
    src = np.asarray(source, dtype=float)
    dst = np.asarray(target, dtype=float)
    if src.ndim != 2 or src.shape[1] != 2:
        raise ValueError("source は (N, 2) であること")
    if dst.ndim != 2 or dst.shape[1] != 2:
        raise ValueError("target は (M, 2) であること")
    if len(src) < 2 or len(dst) < 2:
        raise ValueError("source と target は 2 点以上必要")
    if not 0.0 < trim_ratio <= 1.0:
        raise ValueError("trim_ratio は (0, 1] であること")

    x, y, yaw = (float(v) for v in initial)
    residual = float("inf")
    inlier_ratio = 0.0
    converged = False
    iteration = 0

    for iteration in range(1, max_iterations + 1):
        moved = transform2d(src, x, y, yaw)
        index, distance = _nearest(moved, dst)

        keep = distance < max_correspondence
        if keep.sum() < 2:
            break
        # 残差の小さいほうから trim_ratio を採る。
        kept_distance = distance[keep]
        threshold = np.quantile(kept_distance, trim_ratio)
        keep &= distance <= max(threshold, 1e-12)
        if keep.sum() < 2:
            break

        step = kabsch2d(moved[keep], dst[index[keep]])
        x, y, yaw = (
            *transform2d([[x, y]], step[0], step[1], step[2])[0],
            _wrap(yaw + step[2]),
        )

        # ★ 発散したら黙って壊れた値を返さない。較正値が inf/nan のまま
        #   static TF に流れると、TF ツリー全体が使えなくなる。
        if not all(math.isfinite(v) for v in (x, y, yaw)):
            return MatchResult(
                x=float("nan"), y=float("nan"), yaw=float("nan"),
                residual=float("inf"), inlier_ratio=0.0,
                iterations=iteration, converged=False,
            )

        new_residual = float(np.sqrt(np.mean(distance[keep] ** 2)))
        inlier_ratio = float(keep.sum()) / len(src)
        if abs(residual - new_residual) < tolerance:
            residual = new_residual
            converged = True
            break
        residual = new_residual

    return MatchResult(
        x=x, y=y, yaw=_wrap(yaw),
        residual=residual, inlier_ratio=inlier_ratio,
        iterations=iteration, converged=converged,
    )


def _wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def occupied_cells(grid, width: int, height: int, resolution: float,
                   origin_x: float, origin_y: float,
                   threshold: int = 65) -> np.ndarray:
    """nav_msgs/OccupancyGrid の data から占有セルの map 座標を取り出す。

    ROS のメッセージ型には依存せず、素の配列と諸元だけを受け取る。
    """
    data = np.asarray(grid, dtype=np.int16).reshape(height, width)
    rows, cols = np.nonzero(data >= threshold)
    # セル中心。origin はセルの左下隅を指す。
    xs = origin_x + (cols + 0.5) * resolution
    ys = origin_y + (rows + 0.5) * resolution
    return np.column_stack([xs, ys])


def slice_horizontal(points, z_min: float, z_max: float) -> np.ndarray:
    """水平化済みの点群から、高さ帯を切って 2D 点を得る。

    ★ 呼ぶ前に gravity.level_points で水平化しておくこと。傾いたまま切ると
      壁が斜めの帯になり、マッチングが系統的にずれる。
    """
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError("points は (N, 3) であること")
    keep = (array[:, 2] >= z_min) & (array[:, 2] <= z_max)
    return array[keep][:, :2]
