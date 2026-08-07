"""IMU の重力ベクトルから roll / pitch を求める。

環境固定カメラの較正で使う。**カメラが静止している**ことが前提で、
そのとき加速度計が読むのは運動加速度の混ざらない純粋な比力＝重力の反作用。

ROS 非依存の純 numpy。Mac で pytest できる。
"""

from __future__ import annotations

import math

import numpy as np

#: 標準重力 [m/s^2]
G = 9.80665


def mean_specific_force(samples) -> np.ndarray:
    """加速度計サンプルの平均。

    静止しているので単純平均でよい（運動加速度が無いため中央値の必要も薄いが、
    外れ値が心配なら reject_outliers を先に通す）。
    """
    array = np.asarray(samples, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError("samples は (N, 3) であること")
    if len(array) == 0:
        raise ValueError("サンプルが空")
    return array.mean(axis=0)


def gravity_health(samples, tolerance: float = 0.5) -> tuple[bool, str]:
    """重力として妥当なサンプルかを検査する。

    ★ 静止していない / 加速度計が有効になっていない / 単位が違う、といった
    失敗を**較正を走らせる前に**捕まえるための検査。これが無いと、
    でたらめな roll/pitch が残差に現れないまま較正結果に入り込む。
    """
    array = np.asarray(samples, dtype=float)
    mean = mean_specific_force(array)
    norm = float(np.linalg.norm(mean))
    if not math.isclose(norm, G, abs_tol=tolerance):
        return False, (
            f"平均ノルムが {norm:.3f} m/s^2 で重力 {G:.3f} から外れている "
            "(静止していない / 単位が違う / 軸が欠けている)"
        )
    # 各サンプルの平均からのずれ。静止していれば小さいはず。
    # ★ std ではなく max を見る。std は「ずれのノルムの標準偏差」なので、
    #   一定振幅の振動や一定角速度の回転のように**ノルムがほぼ一定の揺れ**では
    #   ゼロに近くなり、静止していないのに通ってしまう。
    deviation = np.linalg.norm(array - mean, axis=1)
    spread = float(deviation.max())
    if spread > tolerance:
        return False, (
            f"サンプルのばらつきが大きい (最大 {spread:.3f} m/s^2)。静止していない可能性"
        )
    return True, f"norm={norm:.3f} m/s^2, spread={spread:.3f}"


def roll_pitch_from_up(up) -> tuple[float, float]:
    """センサ座標系での「上」方向ベクトルから roll / pitch を求める。

    ★ 加速度計は静止時に**上向き**の比力を読む（重力の反作用）。
      自由落下していない限り、読み値の向き = 上。

    返す roll/pitch は、RPY (roll, pitch, yaw) の回転
    R = Rz(yaw)·Ry(pitch)·Rx(roll) がセンサ座標系を world へ移すときのもの。
    yaw はこの情報だけでは決まらない（重力は鉛直軸まわりの回転に不変）ので返さない。
    """
    vector = np.asarray(up, dtype=float)
    norm = float(np.linalg.norm(vector))
    if norm < 1e-9:
        raise ValueError("up ベクトルの長さがゼロ")
    x, y, z = vector / norm
    roll = math.atan2(y, z)
    pitch = math.atan2(-x, math.hypot(y, z))
    return roll, pitch


def roll_pitch_from_samples(samples) -> tuple[float, float]:
    """加速度計サンプルから直接 roll / pitch を求める。"""
    return roll_pitch_from_up(mean_specific_force(samples))


def rotation_rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """URDF と同じ固定軸 RPY の回転行列 R = Rz(yaw)·Ry(pitch)·Rx(roll)。"""
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ])


def level_points(points, roll: float, pitch: float) -> np.ndarray:
    """点群を重力方向で水平化する（yaw は回さない）。

    水平化後の z は「鉛直上向き」になるので、水平スライスが意味を持つようになる。
    """
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError("points は (N, 3) であること")
    return array @ rotation_rpy(roll, pitch, 0.0).T
