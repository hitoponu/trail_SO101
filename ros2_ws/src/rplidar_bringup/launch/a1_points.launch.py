from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    serial_port = LaunchConfiguration("serial_port")
    start_rviz = LaunchConfiguration("start_rviz")
    frame_id = LaunchConfiguration("frame_id")
    rviz_config = str(
        Path(get_package_share_directory("rplidar_bringup")) / "rviz" / "a1_points.rviz"
    )

    return LaunchDescription([
        DeclareLaunchArgument("serial_port", default_value="/dev/ttyUSB0"),
        DeclareLaunchArgument("start_rviz", default_value="true"),
        # ★ sllidar_ros2 の既定は "laser" だが、lekiwi_description が定義する
        #   リンク名は "laser_link"。既定のままだと /scan の座標系が
        #   LeKiwi の TF ツリーへ繋がらず、costmap が一切埋まらない
        #   (Nav2/SLAM を載せたときに最初に踏む)。URDF 側の _link 命名規約
        #   (base_link, camera_mount_link, ...) を保つため、ここを合わせる。
        #   LiDAR 単体で使う場合は frame_id:=laser で従来どおり動く。
        DeclareLaunchArgument("frame_id", default_value="laser_link"),
        Node(
            package="sllidar_ros2",
            executable="sllidar_node",
            name="sllidar_node",
            output="screen",
            parameters=[{
                "channel_type": "serial",
                "serial_port": serial_port,
                "serial_baudrate": 115200,
                "frame_id": frame_id,
                "inverted": False,
                "angle_compensate": True,
                "scan_mode": "Standard",
            }],
        ),
        Node(
            package="rplidar_bringup",
            executable="scan_to_cloud",
            name="scan_to_cloud",
            output="screen",
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
