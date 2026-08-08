"""Intel RealSense D435i.

■ 手首カメラとして使う場合（このブランチの用途）
`camera_name:=wrist_camera` とする。取り付けは結合 URDF
(`lekiwi_so101_bringup/urdf/lekiwi_so101.urdf.xacro`) が
`arm_gripper_link -> wrist_camera_mount_link -> wrist_camera_link` を出すので、
**外部キャリブレーションは要らない**。realsense2_camera は
`wrist_camera_link` を根として光学フレームを /tf_static へ出すだけで、
`wrist_camera_link` を子にする TF は出さないので二重定義にならない
（`laser_link` と同じパターン）。

★ `enable_imu` は手首カメラでは不要。姿勢は TF から出る。
  環境固定構成（別ブランチ）で重力から roll/pitch を出すために使う。
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    camera_namespace = LaunchConfiguration("camera_namespace")
    camera_name = LaunchConfiguration("camera_name")
    depth_width = LaunchConfiguration("depth_width")
    depth_height = LaunchConfiguration("depth_height")
    depth_fps = LaunchConfiguration("depth_fps")
    color_width = LaunchConfiguration("color_width")
    color_height = LaunchConfiguration("color_height")
    color_fps = LaunchConfiguration("color_fps")
    enable_pointcloud = LaunchConfiguration("enable_pointcloud")
    enable_imu = LaunchConfiguration("enable_imu")
    align_depth = LaunchConfiguration("align_depth")
    decimation = LaunchConfiguration("decimation")
    temporal_filter = LaunchConfiguration("temporal_filter")
    spatial_filter = LaunchConfiguration("spatial_filter")
    reconnect_timeout = LaunchConfiguration("reconnect_timeout")
    start_rviz = LaunchConfiguration("start_rviz")

    rviz_config = str(
        Path(get_package_share_directory("realsense_bringup")) / "rviz" / "d435i.rviz"
    )

    # realsense2_camera はプロファイルを "WxHxFPS" の 1 文字列で受け取る。
    # ★ 以前は "640x480x30" がハードコードされており、depth_fps / color_fps の
    #   launch 引数は宣言されているだけでノードに一切渡っていなかった
    #   (= 効いているつもりのつまみ)。ここで実際に組み立てる。
    def profile(width, height, fps):
        return PythonExpression(["'", width, "x", height, "x", fps, "'"])

    return LaunchDescription([
        # ★ 上流の rs_launch.py と同じく namespace と name を分ける。
        #   既定のままだと /camera/camera/... になるが、これは上流の慣習どおり。
        DeclareLaunchArgument("camera_namespace", default_value="camera"),
        DeclareLaunchArgument(
            "camera_name",
            default_value="camera",
            description="★ トピックだけでなく TF のフレーム名にも効く "
                        "(<camera_name>_link, <camera_name>_depth_optical_frame ...)",
        ),

        DeclareLaunchArgument("depth_width", default_value="640"),
        DeclareLaunchArgument("depth_height", default_value="480"),
        DeclareLaunchArgument("color_width", default_value="640"),
        DeclareLaunchArgument("color_height", default_value="480"),
        # ★ 点群を出すなら 30fps は重すぎる。640x480 の点群は 1 枚 4.9MB あり、
        #   30Hz では 147MB/s になる。静止して撮る運用なので低レートで十分
        #   (decimation ×2 と併用して 6fps で約 7MB/s)。
        DeclareLaunchArgument("depth_fps", default_value="6"),
        DeclareLaunchArgument("color_fps", default_value="6"),

        DeclareLaunchArgument(
            "enable_pointcloud",
            default_value="false",
            description="/<ns>/<name>/depth/color/points を出す",
        ),
        DeclareLaunchArgument(
            "enable_imu",
            default_value="false",
            description="★ 環境固定での較正に使う。静止しているので加速度計は "
                        "純粋な重力を読み、roll/pitch がシーンに依らず決まる",
        ),
        DeclareLaunchArgument(
            "align_depth",
            default_value="false",
            description="★ 点群には無関係 (点群フィルタは align より前に適用される)。"
                        "aligned_depth_to_color が要るときだけ true",
        ),
        DeclareLaunchArgument(
            "decimation",
            default_value="2",
            description="点群の間引き。2 で点数 1/4",
        ),
        DeclareLaunchArgument(
            "temporal_filter",
            default_value="false",
            description="★ 静止して撮るときだけ true。手首カメラは動くので、"
                        "動作中に有効だと過去フレームを混ぜて深度を引きずる",
        ),
        DeclareLaunchArgument("spatial_filter", default_value="false"),
        DeclareLaunchArgument(
            "reconnect_timeout",
            default_value="6.0",
            description=(
                "デバイス切断後、次の再接続試行まで待つ秒数。"
                "V4L2の切断エラーを高速再試行しないための間隔"
            ),
        ),
        DeclareLaunchArgument("start_rviz", default_value="true"),

        Node(
            package="realsense_bringup",
            executable="realsense_camera_watchdog.py",
            name=camera_name,
            namespace=camera_namespace,
            output="screen",
            arguments=["--watchdog-restart-delay", reconnect_timeout],
            parameters=[{
                # ★ これが無いと TF のフレーム名が camera_link のまま動かない。
                #   name=/namespace= はトピックにしか効かず、フレーム名は
                #   このパラメータから作られる (base_realsense_node.h の
                #   OPTICAL_FRAME_ID = <tf_prefix><camera_name>_<stream>_optical_frame)。
                #   「トピックは env_camera なのに TF は camera_link」という
                #   追跡困難な状態を防ぐ。
                "camera_name": camera_name,
                # デバイス切断後の再接続試行間隔。明示的に渡して、
                # realsense2_camera の既定値に依存しないようにする。
                "reconnect_timeout": reconnect_timeout,

                "enable_color": True,
                "enable_depth": True,
                "enable_infra1": False,
                "enable_infra2": False,
                # ★ 環境固定の較正では加速度計を使う (重力 -> roll/pitch)。
                #   ジャイロは静止しているので不要。
                "enable_accel": enable_imu,
                "enable_gyro": False,
                "depth_module.profile": profile(depth_width, depth_height, depth_fps),
                "rgb_camera.profile": profile(color_width, color_height, color_fps),
                "align_depth.enable": align_depth,

                # ---- 点群 ----
                "pointcloud.enable": enable_pointcloud,
                # ★ 既定は RELIABLE。数 MB のメッセージを RELIABLE で流すと詰まる。
                "pointcloud.pointcloud_qos": "SENSOR_DATA",
                "pointcloud.ordered_pc": False,
                "pointcloud.allow_no_texture_points": False,

                # ---- フィルタ ----
                # 適用順は decimation -> spatial -> temporal -> hole_filling
                #          -> pointcloud -> align_depth。
                "decimation_filter.enable": True,
                "decimation_filter.filter_magnitude": decimation,
                # ★ 既定 false（上流と同じ）。手首カメラは**カメラ自身が動く**ので、
                #   temporal フィルタは過去フレームを混ぜて動作中の深度を引きずる。
                #   静止して撮る運用なら true にすると効く。
                #   環境固定カメラ（別ブランチ）はカメラも被写体も静止しているので
                #   常時 true でよいが、ここでは前提が逆になる。
                "temporal_filter.enable": temporal_filter,
                "spatial_filter.enable": spatial_filter,
                # ★ 穴埋めは有効にしない。存在しない点を捏造するので、
                #   それをクリックすると「実在しない目標」へアームが動く。
                "hole_filling_filter.enable": False,
            }],
        ),

        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            arguments=["-d", rviz_config],
            condition=IfCondition(start_rviz),
            output="screen",
        ),
    ])
