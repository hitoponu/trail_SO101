"""Start the SO-ARM101 ROS 2 bringup together with MoveIt."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    backend = LaunchConfiguration("backend")
    usb_port = LaunchConfiguration("usb_port")
    robot_id = LaunchConfiguration("robot_id")
    calibration_dir = LaunchConfiguration("calibration_dir")
    start_moveit_rviz = LaunchConfiguration("start_moveit_rviz")

    follower_launch = PathJoinSubstitution(
        [FindPackageShare("so101_bringup"), "launch", "follower.launch.py"]
    )
    move_group_launch = PathJoinSubstitution(
        [FindPackageShare("so101_moveit_config"), "launch", "move_group.launch.py"]
    )

    follower = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(follower_launch),
        launch_arguments={
            "backend": backend,
            "usb_port": usb_port,
            "robot_id": robot_id,
            "calibration_dir": calibration_dir,
            # MoveIt RViz is controlled independently below.
            "start_rviz": "false",
        }.items(),
    )

    move_group = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(move_group_launch),
        launch_arguments={
            "usb_port": usb_port,
            "start_rviz": start_moveit_rviz,
        }.items(),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("backend", default_value="mock"),
            DeclareLaunchArgument("usb_port", default_value="/dev/so101_follower"),
            DeclareLaunchArgument("robot_id", default_value=""),
            DeclareLaunchArgument(
                "calibration_dir",
                default_value=(
                    "/root/.cache/huggingface/lerobot/calibration/robots/so_follower"
                ),
            ),
            DeclareLaunchArgument("start_moveit_rviz", default_value="false"),
            follower,
            move_group,
        ]
    )
