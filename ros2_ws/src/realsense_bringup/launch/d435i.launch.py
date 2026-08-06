"""Intel RealSense D435i.

環境固定で使う場合（三脚などに据え置き、ロボットには載せない）は
`camera_name:=env_camera` とし、`lekiwi_so101_bringup/launch/env_camera.launch.py`
が `map -> env_camera_link` の static TF を出す。詳細は
`docker/lekiwi_so101_bringup/README.md`。
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
    align_depth = LaunchConfiguration("align_depth")
    decimation = LaunchConfiguration("decimation")
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
        #   30Hz では 147MB/s になる。環境固定でシーンも静止しているので
        #   低レートで十分 (decimation ×2 と併用して 6fps で約 7MB/s)。
        DeclareLaunchArgument("depth_fps", default_value="6"),
        DeclareLaunchArgument("color_fps", default_value="6"),

        DeclareLaunchArgument(
            "enable_pointcloud",
            default_value="false",
            description="/<ns>/<name>/depth/color/points を出す",
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
        DeclareLaunchArgument("start_rviz", default_value="true"),

        Node(
            package="realsense2_camera",
            executable="realsense2_camera_node",
            name=camera_name,
            namespace=camera_namespace,
            output="screen",
            parameters=[{
                # ★ これが無いと TF のフレーム名が camera_link のまま動かない。
                #   name=/namespace= はトピックにしか効かず、フレーム名は
                #   このパラメータから作られる (base_realsense_node.h の
                #   OPTICAL_FRAME_ID = <tf_prefix><camera_name>_<stream>_optical_frame)。
                #   「トピックは env_camera なのに TF は camera_link」という
                #   追跡困難な状態を防ぐ。
                "camera_name": camera_name,

                "enable_color": True,
                "enable_depth": True,
                "enable_infra1": False,
                "enable_infra2": False,
                "enable_accel": False,
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
                # カメラも被写体も静止しているので時間平均がいちばん効く。
                "temporal_filter.enable": True,
                "spatial_filter.enable": True,
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
