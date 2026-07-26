from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    camera_name = LaunchConfiguration("camera_name")
    depth_fps = LaunchConfiguration("depth_fps")
    color_fps = LaunchConfiguration("color_fps")
    start_rviz = LaunchConfiguration("start_rviz")

    rviz_config = str(
        Path(get_package_share_directory("realsense_bringup")) / "rviz" / "d435i.rviz"
    )

    return LaunchDescription([
        DeclareLaunchArgument("camera_name", default_value="camera"),
        DeclareLaunchArgument("depth_fps", default_value="30"),
        DeclareLaunchArgument("color_fps", default_value="30"),
        DeclareLaunchArgument("start_rviz", default_value="true"),

        Node(
            package="realsense2_camera",
            executable="realsense2_camera_node",
            name=camera_name,
            namespace=camera_name,
            output="screen",
            parameters=[{
                "enable_color": True,
                "enable_depth": True,
                "enable_infra1": False,
                "enable_infra2": False,
                "enable_accel": False,
                "enable_gyro": False,
                "depth_module.profile": "640x480x30",
                "rgb_camera.profile": "640x480x30",
                "align_depth.enable": True,
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
