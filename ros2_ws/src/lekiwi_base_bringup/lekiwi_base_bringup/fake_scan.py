"""実機の LiDAR なしで ``/scan`` を作る仮想 2D スキャナ。

``base_driver`` を ``dry_run:=true`` で動かすと ``/cmd_vel`` から odom と TF は
出るが、``/scan`` の供給元が無いため SLAM も Nav2 も回せない。このノードは
**仮想の部屋** に対してレイキャストして ``sensor_msgs/LaserScan`` を publish し、
実機・LiDAR なしで「走らせる → 地図ができる → 経路を追従する」まで閉ループで
検証できるようにする。

■ 自己位置の扱い

    ``world_frame`` (既定 odom) → ``frame_id`` (既定 laser_link) の TF を引いて、
    その姿勢からレイを飛ばす。``dry_run`` の odom は指令値の積分なので誤差ゼロ、
    つまり **odom がそのまま真値** になる。

    ただしそれでは SLAM のスキャンマッチングが自明に成功してしまい、ロバスト性を
    何も検証できない。そこで ``odom_trans_scale`` / ``odom_yaw_scale`` で
    「odom が実際より何倍多く報告しているか」を与えられるようにしてある。
    1.03 なら odom が 3% 過大報告し、レイキャストは真値 (= odom / 1.03) で
    行われるため、SLAM が補正すべき誤差が生まれる。

    これは車輪半径や base_radius の誤りに相当する **系統誤差の粗いモデル** で
    あって、スリップの物理シミュレーションではない。乱数を使わないので再現性が
    ある (回帰テストに使える)。

■ 世界の定義

    軸平行な矩形の部屋 + 矩形障害物。全て ``world_frame`` 座標で与える。
    障害物は 4 要素ずつ ``(min_x, min_y, max_x, max_y)`` の平坦な配列で渡す
    (ROS パラメータは入れ子の配列を扱えないため)。幾何そのものは
    ``raycast.py`` にあり、ROS なしで単体テストできる。

    ``publish_world_markers`` が true なら真の壁を ``~/world`` に MarkerArray で
    出す。RViz で SLAM の地図と重ねれば、地図がどれだけ歪んでいるかが一目で分かる。

■ 実機との対応

    既定値は RPLIDAR A1M8 相当 (360°, 0.15〜12 m, 5.5 Hz)。``frame_id`` の既定は
    ``laser_link`` で、``rplidar_bringup/launch/a1_points.launch.py`` の既定と
    揃えてある。**片方だけ変えないこと。**

★ このノードは実機の LiDAR の代用であって、実機と同時に起動してはいけない
  (``/scan`` が二重に publish される)。
"""

from __future__ import annotations

import math

import numpy as np
import rclpy
from geometry_msgs.msg import Point
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformException, TransformListener
from visualization_msgs.msg import Marker, MarkerArray

from lekiwi_base_bringup import raycast as rc


class FakeScan(Node):
    def __init__(self) -> None:
        super().__init__("fake_scan")

        # ── 世界 ────────────────────────────────────────────────────
        self.declare_parameter("world_frame", "odom")
        self.declare_parameter("room_min_x", -2.5)
        self.declare_parameter("room_min_y", -2.0)
        self.declare_parameter("room_max_x", 2.5)
        self.declare_parameter("room_max_y", 2.0)
        # 4 要素ずつ (min_x, min_y, max_x, max_y)。既定は部屋の中に箱を 2 つ置く。
        self.declare_parameter("obstacles", [0.8, -0.4, 1.2, 0.4, -1.5, 0.6, -1.0, 1.4])

        # ── スキャナ (既定は RPLIDAR A1M8 相当) ─────────────────────
        self.declare_parameter("frame_id", "laser_link")
        self.declare_parameter("scan_topic", "scan")
        self.declare_parameter("samples", 360)
        self.declare_parameter("range_min", 0.15)
        self.declare_parameter("range_max", 12.0)
        self.declare_parameter("rate_hz", 5.5)
        self.declare_parameter("noise_stddev", 0.01)
        self.declare_parameter("seed", 0)

        # ── odom の系統誤差 (1.0 = 誤差なし) ────────────────────────
        self.declare_parameter("odom_trans_scale", 1.0)
        self.declare_parameter("odom_yaw_scale", 1.0)

        self.declare_parameter("publish_world_markers", True)

        p = self.get_parameter
        self.world_frame = str(p("world_frame").value)
        self.frame_id = str(p("frame_id").value)
        self.range_min = float(p("range_min").value)
        self.range_max = float(p("range_max").value)
        self.noise_stddev = float(p("noise_stddev").value)
        self.trans_scale = float(p("odom_trans_scale").value)
        self.yaw_scale = float(p("odom_yaw_scale").value)

        if self.range_max <= self.range_min:
            raise ValueError(
                f"range_max は range_min より大きい必要がある: {self.range_min}..{self.range_max}"
            )
        for name, value in (
            ("odom_trans_scale", self.trans_scale),
            ("odom_yaw_scale", self.yaw_scale),
        ):
            if value <= 0.0:
                raise ValueError(f"{name} は正の値が必要: {value}")

        room = (
            float(p("room_min_x").value),
            float(p("room_min_y").value),
            float(p("room_max_x").value),
            float(p("room_max_y").value),
        )
        self.segments = rc.build_world(room, p("obstacles").value)
        self.angles = rc.full_circle_angles(int(p("samples").value))
        self.angle_increment = 2.0 * math.pi / len(self.angles)
        self.rng = np.random.default_rng(int(p("seed").value))

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # LiDAR ドライバと同じ QoS (Best Effort)。slam_toolbox / Nav2 の
        # scan 購読側の既定と揃うので、ここを変えると受信されなくなる。
        self.scan_pub = self.create_publisher(
            LaserScan, str(p("scan_topic").value), qos_profile_sensor_data
        )

        rate = float(p("rate_hz").value)
        if rate <= 0.0:
            raise ValueError(f"rate_hz は正の値が必要: {rate}")
        self.scan_period = 1.0 / rate
        self.create_timer(self.scan_period, self._on_timer)

        self.marker_pub = None
        if bool(p("publish_world_markers").value):
            # 真の壁は動かないので transient_local で 1 回だけ出す。
            # 後から RViz を開いた購読者にも最後の 1 つが届く。
            self.marker_pub = self.create_publisher(
                MarkerArray,
                "~/world",
                QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
            )
            self._publish_world_markers()

        self.get_logger().info(
            f"fake_scan 起動: {len(self.angles)} points @ {rate:.1f}Hz "
            f"range {self.range_min}〜{self.range_max}m frame={self.frame_id}"
        )
        self.get_logger().info(
            f"世界: 部屋 x {room[0]}〜{room[2]} / y {room[1]}〜{room[3]} m, "
            f"線分 {len(self.segments)} 本 (障害物込み)"
        )
        if self.trans_scale != 1.0 or self.yaw_scale != 1.0:
            self.get_logger().warn(
                f"odom に系統誤差を入れています: trans x{self.trans_scale}, "
                f"yaw x{self.yaw_scale} "
                "(レイキャストは真値で行うので SLAM が補正すべき誤差になります)"
            )

    # ── 姿勢 ────────────────────────────────────────────────────────

    def _true_pose(self) -> tuple[np.ndarray, float] | None:
        """world → frame_id の TF から、レイキャストに使う真の姿勢を得る。

        TF は odom 由来なので、``odom_*_scale`` で「odom の過大報告」を割り戻して
        真値へ直す。誤差なし設定 (1.0) なら TF の値そのまま。
        """
        try:
            tf = self.tf_buffer.lookup_transform(
                self.world_frame, self.frame_id, rclpy.time.Time()
            )
        except TransformException as exc:
            self.get_logger().warn(
                f"TF {self.world_frame} → {self.frame_id} が引けません: {exc}",
                throttle_duration_sec=5.0,
            )
            return None

        tr = tf.transform.translation
        q = tf.transform.rotation
        yaw = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y**2 + q.z**2)
        )

        origin = np.array([tr.x / self.trans_scale, tr.y / self.trans_scale])
        return origin, yaw / self.yaw_scale

    # ── ループ ──────────────────────────────────────────────────────

    def _on_timer(self) -> None:
        pose = self._true_pose()
        if pose is None:
            return
        origin, yaw = pose

        # angles はセンサ基準なので、世界座標の絶対角にするため yaw を足す
        ranges = rc.raycast(self.segments, origin, self.angles + yaw)

        if self.noise_stddev > 0.0:
            ranges = ranges + self.rng.normal(0.0, self.noise_stddev, ranges.shape)

        # LaserScan の規約: 測距範囲外は inf にする。0 を入れると「距離 0 に
        # 障害物がある」と解釈する実装があるため。
        ranges = np.where(
            (ranges < self.range_min) | (ranges > self.range_max), np.inf, ranges
        )

        msg = LaserScan()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.angle_min = float(self.angles[0])
        msg.angle_max = float(self.angles[-1])
        msg.angle_increment = float(self.angle_increment)
        msg.time_increment = 0.0
        msg.scan_time = float(self.scan_period)
        msg.range_min = float(self.range_min)
        msg.range_max = float(self.range_max)
        msg.ranges = [float(r) for r in ranges]
        self.scan_pub.publish(msg)

    def _publish_world_markers(self) -> None:
        marker = Marker()
        marker.header.frame_id = self.world_frame
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.ns = "fake_world"
        marker.id = 0
        marker.type = Marker.LINE_LIST
        marker.action = Marker.ADD
        marker.scale.x = 0.02
        marker.color.r = 1.0
        marker.color.g = 0.6
        marker.color.a = 0.8
        marker.pose.orientation.w = 1.0

        for seg in self.segments:
            for x, y in seg:
                marker.points.append(Point(x=float(x), y=float(y), z=0.0))

        array = MarkerArray()
        array.markers.append(marker)
        self.marker_pub.publish(array)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = FakeScan()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except ValueError as exc:
        if node is not None:
            node.get_logger().fatal(str(exc))
        else:
            print(f"起動失敗: {exc}")
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
