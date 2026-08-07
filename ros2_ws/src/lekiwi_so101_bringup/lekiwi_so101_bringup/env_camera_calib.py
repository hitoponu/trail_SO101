"""環境固定 RealSense の map 上の位置姿勢を求める（IMU + LiDAR 地図マッチング）。

    ros2 run lekiwi_so101_bringup env_camera_calib --ros-args -p camera_height:=1.05

■ 自由度の分解（それぞれ最も適した手段で決める）

    roll / pitch  <- IMU の重力。カメラは静止しているので加速度計が読むのは
                     運動加速度の混ざらない純粋な重力
    z             <- ★ 実測値をパラメータで渡す。壁は鉛直なので 2D マッチングは
                     z に対して原理的に縮退している（icp2d の docstring 参照）。
                     map の z=0 は base_footprint（車輪接地面）＝床なので、
                     三脚の床からの高さがそのまま z になる
    x / y / yaw   <- 重力で水平化した点群を水平スライスし、slam_toolbox の
                     占有格子へ trimmed ICP で合わせる

■ 出力
    map -> <camera>_link の 6 数値と、残差 RMS / インライア率。
    .env へ貼る形と static_transform_publisher の引数の両方を印字する。

■ 何もしない
    このノードは TF も publish しないし、ロボットも動かさない。読むだけ。
    値の反映は人間が .env を書き換えて再起動する（誤った較正が黙って
    TF に入るのを防ぐため）。
"""

from __future__ import annotations

import math
import sys

import numpy as np
import rclpy
import tf2_ros
from nav_msgs.msg import OccupancyGrid
from rclpy.duration import Duration as RclDuration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import Imu, PointCloud2
from sensor_msgs_py import point_cloud2

from . import icp2d
from .gravity import gravity_health, level_points, roll_pitch_from_up


class EnvCameraCalib(Node):
    def __init__(self) -> None:
        super().__init__("env_camera_calib")

        defaults = {
            "camera_name": "env_camera",
            "map_topic": "/map",
            "cloud_topic": "",          # 空なら camera_name から組み立てる
            "accel_topic": "",          # 同上
            # ★ 実測値。三脚のカメラ光学中心の床からの高さ [m]。
            "camera_height": 1.0,
            # 粗い初期値。三脚の位置はおおよそ分かるので局所最適化で足りる。
            "initial_x": 0.0,
            "initial_y": 0.0,
            "initial_yaw": 0.0,
            # 切り出す高さ帯（map 基準、床からの高さ [m]）。
            # 壁が写っている帯を選ぶ。机の天板などは外れ値として trim される。
            "slice_z_min": 0.15,
            "slice_z_max": 1.20,
            "accel_samples": 200,
            "cloud_frames": 3,
            "max_points": 1500,
            "trim_ratio": 0.7,
            "max_correspondence": 0.5,
            # これを下回ったら「合っていない」として失敗させる。
            "min_inlier_ratio": 0.35,
            "max_residual": 0.10,
            "timeout": 30.0,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

        def param(name):
            return self.get_parameter(name).value

        self._camera = str(param("camera_name"))
        self._cloud_topic = str(param("cloud_topic")) or \
            f"/{self._camera}/{self._camera}/depth/color/points"
        self._accel_topic = str(param("accel_topic")) or \
            f"/{self._camera}/{self._camera}/accel/sample"
        self._height = float(param("camera_height"))
        self._initial = (float(param("initial_x")), float(param("initial_y")),
                         float(param("initial_yaw")))
        self._band = (float(param("slice_z_min")), float(param("slice_z_max")))
        self._want_accel = int(param("accel_samples"))
        self._want_frames = int(param("cloud_frames"))
        self._max_points = int(param("max_points"))
        self._trim = float(param("trim_ratio"))
        self._max_corr = float(param("max_correspondence"))
        self._min_inlier = float(param("min_inlier_ratio"))
        self._max_residual = float(param("max_residual"))
        self._timeout = float(param("timeout"))

        self._accel: list[np.ndarray] = []
        self._accel_frame = ""
        self._clouds: list[np.ndarray] = []
        self._map: OccupancyGrid | None = None

        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        sensor = QoSProfile(depth=5, durability=DurabilityPolicy.VOLATILE,
                            reliability=ReliabilityPolicy.BEST_EFFORT)

        self.create_subscription(OccupancyGrid, str(param("map_topic")),
                                 self._map_cb, latched)
        self.create_subscription(PointCloud2, self._cloud_topic, self._cloud_cb, sensor)
        self.create_subscription(Imu, self._accel_topic, self._accel_cb, sensor)

        self._buffer = tf2_ros.Buffer(cache_time=RclDuration(seconds=10.0))
        self._listener = tf2_ros.TransformListener(self._buffer, self, spin_thread=False)

        self.get_logger().info(
            f"収集中: map={param('map_topic')} cloud={self._cloud_topic} "
            f"accel={self._accel_topic}"
        )

    # ------------------------------------------------------------- 収集

    def _map_cb(self, message: OccupancyGrid) -> None:
        self._map = message

    def _accel_cb(self, message: Imu) -> None:
        if len(self._accel) < self._want_accel:
            a = message.linear_acceleration
            self._accel.append(np.array([a.x, a.y, a.z]))
            self._accel_frame = message.header.frame_id

    def _cloud_cb(self, message: PointCloud2) -> None:
        if len(self._clouds) >= self._want_frames:
            return
        points = point_cloud2.read_points_numpy(
            message, field_names=("x", "y", "z"), skip_nans=True)
        if len(points):
            self._clouds.append((np.asarray(points, dtype=float), message.header.frame_id))

    @property
    def ready(self) -> bool:
        """収集完了。★ TF が引けることまで含める。

        solve() は収集ループを抜けた後に呼ばれ、そこでは誰も spin していない。
        したがって lookup_transform の timeout は待つだけで**リトライにならず**、
        buffer にまだ無い TF は永久に来ない。加速度計は 250Hz なので 200 サンプルは
        0.8 秒で埋まり、/tf_static の配送がそれに間に合わないことがある。
        ここで TF まで待てば、その間欠故障が起きない。
        """
        if (self._map is None
                or len(self._accel) < self._want_accel
                or len(self._clouds) < self._want_frames):
            return False
        return not self._missing_transforms()

    def _missing_transforms(self) -> list[str]:
        link = f"{self._camera}_link"
        frames = {self._accel_frame} | {frame for _, frame in self._clouds}
        return [f"{frame} -> {link}" for frame in frames
                if frame and frame != link
                and not self._buffer.can_transform(link, frame, Time())]

    def missing(self) -> list[str]:
        out = []
        if self._map is None:
            out.append("/map（slam_toolbox か map_server が動いているか）")
        if len(self._accel) < self._want_accel:
            out.append(f"{self._accel_topic}（{len(self._accel)}/{self._want_accel}。"
                       "enable_accel:=true になっているか）")
        if len(self._clouds) < self._want_frames:
            out.append(f"{self._cloud_topic}（{len(self._clouds)}/{self._want_frames}。"
                       "enable_pointcloud:=true になっているか）")
        out += [f"TF {m}（realsense2_camera が publish_tf:=true で動いているか）"
                for m in self._missing_transforms()]
        return out

    # ------------------------------------------------------------- 計算

    def solve(self) -> int:
        link = f"{self._camera}_link"

        # 1. 重力 -> roll / pitch
        healthy, note = gravity_health(self._accel)
        if not healthy:
            self.get_logger().error(f"加速度計のサンプルが重力として妥当でない: {note}")
            return 1
        self.get_logger().info(f"加速度計: {note}")

        up = self._to_link(np.array([np.mean(self._accel, axis=0)]),
                           self._accel_frame, link, rotation_only=True)
        if up is None:
            return 1
        roll, pitch = roll_pitch_from_up(up[0])
        self.get_logger().info(
            f"重力から: roll={math.degrees(roll):.2f}deg pitch={math.degrees(pitch):.2f}deg")

        # 2. 点群を camera_link へ集めて水平化
        collected = []
        for points, frame in self._clouds:
            moved = self._to_link(points, frame, link)
            if moved is None:
                return 1
            collected.append(moved)
        cloud = np.vstack(collected)
        levelled = level_points(cloud, roll, pitch)

        # 3. 高さ帯で切る。levelled の z=0 はカメラ高なので、床基準へ直す。
        band = (self._band[0] - self._height, self._band[1] - self._height)
        sliced = icp2d.slice_horizontal(levelled, band[0], band[1])
        if len(sliced) < 50:
            self.get_logger().error(
                f"スライスに点がほとんど無い（{len(sliced)}点）。"
                f"床から {self._band[0]:.2f}〜{self._band[1]:.2f}m の帯に壁が写っているか、"
                f"camera_height={self._height:.2f} が正しいかを確認すること")
            return 1
        sliced = self._subsample(sliced, self._max_points)

        # 4. 占有格子へ合わせる
        grid = self._map
        # ★ occupied_cells は origin の並進しか使わない。姿勢が非ゼロだと
        #   全セルの座標が狂い、ICP は「それらしく収束」して**黙って間違った
        #   較正値**を出す。slam_toolbox も map_server も通常は単位四元数だが、
        #   前提が崩れていたら止める。
        q = grid.info.origin.orientation
        if abs(q.x) > 1e-6 or abs(q.y) > 1e-6 or abs(q.z) > 1e-6 or abs(q.w - 1.0) > 1e-6:
            self.get_logger().error(
                f"地図原点の姿勢が単位四元数でない (x={q.x} y={q.y} z={q.z} w={q.w})。"
                "この較正は回転した地図に対応していない")
            return 1
        target = icp2d.occupied_cells(
            grid.data, grid.info.width, grid.info.height, grid.info.resolution,
            grid.info.origin.position.x, grid.info.origin.position.y)
        if len(target) < 50:
            self.get_logger().error(
                f"地図の占有セルが少なすぎる（{len(target)}）。地図が空の可能性")
            return 1

        result = icp2d.match(sliced, target, initial=self._initial,
                             trim_ratio=self._trim,
                             max_correspondence=self._max_corr)
        return self._report(result, roll, pitch, len(sliced), len(target), link)

    def _report(self, result, roll, pitch, n_source, n_target, link) -> int:
        self.get_logger().info(
            f"マッチング: 点群 {n_source} / 地図 {n_target} セル、"
            f"{result.iterations} 反復、収束={result.converged}")
        self.get_logger().info(
            f"残差 RMS={result.residual*100:.1f}cm  インライア率={result.inlier_ratio:.2f}")

        bad = []
        # ★ 上限に達しただけなら棄却しない。converged は「残差の変化が
        #   tolerance を下回った」という打ち切り判定にすぎず、姿勢の良し悪しでは
        #   ない。実際、初期値が 0.5m ずれた合成シーンでは 60 反復では
        #   converged=False のまま xy 誤差 0.44cm の正しい解が出ていた。
        #   品質は残差とインライア率で判断する。
        if not result.converged:
            self.get_logger().warning(
                f"反復上限 {result.iterations} に達した（残差の変化が収束判定を"
                "下回らなかった）。残差とインライア率が基準内なら採用する")
        if not all(math.isfinite(v) for v in result.as_tuple()):
            bad.append("発散した")
        if result.inlier_ratio < self._min_inlier:
            bad.append(f"インライア率が低い（{result.inlier_ratio:.2f} < {self._min_inlier}）")
        if result.residual > self._max_residual:
            bad.append(f"残差が大きい（{result.residual*100:.1f}cm > "
                       f"{self._max_residual*100:.0f}cm）")
        if bad:
            self.get_logger().error("較正を採用できない: " + " / ".join(bad))
            self.get_logger().error(
                "初期値 (initial_x/y/yaw) が実際と大きく違う、"
                "切り出した帯に壁が写っていない、地図が古い、のいずれかを疑うこと")
            return 1

        print("\n" + "=" * 68)
        print(f"  map -> {link}")
        print("=" * 68)
        print(f"  x     = {result.x:+.4f}")
        print(f"  y     = {result.y:+.4f}")
        print(f"  z     = {self._height:+.4f}   ← 実測値をそのまま使用")
        print(f"  roll  = {roll:+.4f}   ({math.degrees(roll):+.2f} deg)")
        print(f"  pitch = {pitch:+.4f}   ({math.degrees(pitch):+.2f} deg)")
        print(f"  yaw   = {result.yaw:+.4f}   ({math.degrees(result.yaw):+.2f} deg)")
        print(f"\n  残差 RMS = {result.residual*100:.1f} cm   "
              f"インライア率 = {result.inlier_ratio:.2f}")
        print("\n--- docker/lekiwi_so101_bringup/.env へ貼る ---")
        print(f"ENV_CAMERA_X={result.x:.4f}")
        print(f"ENV_CAMERA_Y={result.y:.4f}")
        print(f"ENV_CAMERA_Z={self._height:.4f}")
        print(f"ENV_CAMERA_ROLL={roll:.4f}")
        print(f"ENV_CAMERA_PITCH={pitch:.4f}")
        print(f"ENV_CAMERA_YAW={result.yaw:.4f}")
        print("\n--- その場で確かめる場合 ---")
        print(f"ros2 run tf2_ros static_transform_publisher "
              f"--x {result.x:.4f} --y {result.y:.4f} --z {self._height:.4f} "
              f"--roll {roll:.4f} --pitch {pitch:.4f} --yaw {result.yaw:.4f} "
              f"--frame-id map --child-frame-id {link}")
        print("=" * 68 + "\n")
        return 0

    # ------------------------------------------------------------ 補助

    def _to_link(self, points, source_frame: str, link: str,
                 rotation_only: bool = False):
        """カメラ内部の static TF で points を <camera>_link へ移す。"""
        if not source_frame:
            self.get_logger().error("メッセージの frame_id が空")
            return None
        if source_frame == link:
            return np.asarray(points, dtype=float)
        try:
            tf = self._buffer.lookup_transform(link, source_frame, Time(),
                                               timeout=RclDuration(seconds=2.0))
        except tf2_ros.TransformException as exc:
            self.get_logger().error(
                f"{source_frame} -> {link} が引けない: {exc}\n"
                "  realsense2_camera が publish_tf:=true で動いているか、"
                "  camera_name がフレーム名に効いているかを確認すること")
            return None
        q = tf.transform.rotation
        x, y, z, w = q.x, q.y, q.z, q.w
        rotation = np.array([
            [1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
            [2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)],
            [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)]])
        moved = np.asarray(points, dtype=float) @ rotation.T
        if rotation_only:
            return moved
        t = tf.transform.translation
        return moved + np.array([t.x, t.y, t.z])

    @staticmethod
    def _subsample(points, limit: int) -> np.ndarray:
        if len(points) <= limit:
            return points
        # 決定的に間引く（乱数を使わないので報告が再現する）。
        step = len(points) / limit
        index = (np.arange(limit) * step).astype(int)
        return points[index]


def main(args=None) -> None:
    rclpy.init(args=args)
    node = EnvCameraCalib()
    code = 1
    try:
        deadline = node.get_clock().now() + RclDuration(seconds=node._timeout)
        while rclpy.ok() and not node.ready and node.get_clock().now() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not node.ready:
            node.get_logger().error("入力が揃わなかった:\n  - " + "\n  - ".join(node.missing()))
        else:
            code = node.solve()
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001 - 較正は単発コマンドなので原因を出して終わる
        print(f"較正に失敗: {exc}", file=sys.stderr)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
