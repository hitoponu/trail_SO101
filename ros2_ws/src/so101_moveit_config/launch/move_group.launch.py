"""Start MoveIt's planning node for the SO-ARM101 arm."""

from pathlib import Path
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    moveit_share = Path(get_package_share_directory("so101_moveit_config"))
    bringup_share = Path(get_package_share_directory("so101_bringup"))
    description_share = Path(get_package_share_directory("so_arm101_description"))

    xacro_file = description_share / "urdf" / "so_arm101.urdf.xacro"
    control_file = bringup_share / "control" / "so101_follower.ros2_control.xacro"
    srdf_file = moveit_share / "config" / "so101.srdf"
    kinematics_file = moveit_share / "config" / "kinematics.yaml"
    joint_limits_file = moveit_share / "config" / "joint_limits.yaml"
    ompl_file = moveit_share / "config" / "ompl_planning.yaml"
    controllers_file = moveit_share / "config" / "moveit_controllers.yaml"
    rviz_file = moveit_share / "rviz" / "moveit.rviz"

    usb_port = LaunchConfiguration("usb_port")
    start_rviz = LaunchConfiguration("start_rviz")

    # Keep the MoveIt model identical to the model used by follower.launch.py,
    # including the topic-based ros2_control hardware adapter.
    robot_description = ParameterValue(
        Command(
            [
                "xacro ",
                str(xacro_file),
                " ros2_control_hardware_type:=real",
                " usb_port:=",
                usb_port,
                " ros2_control_file:=",
                str(control_file),
            ]
        ),
        value_type=str,
    )

    robot_description_semantic = srdf_file.read_text()
    robot_description_kinematics = yaml.safe_load(kinematics_file.read_text())
    robot_description_planning = yaml.safe_load(joint_limits_file.read_text())
    ompl_planning = yaml.safe_load(ompl_file.read_text())
    moveit_controllers = yaml.safe_load(controllers_file.read_text())

    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        name="move_group",
        output="screen",
        parameters=[
            {"robot_description": robot_description},
            {"robot_description_semantic": robot_description_semantic},
            {"robot_description_kinematics": robot_description_kinematics},
            {"robot_description_planning": robot_description_planning},
            {"ompl": ompl_planning},
            moveit_controllers,
            {
                "planning_pipelines": ["ompl"],
                "default_planning_pipeline": "ompl",
                "publish_robot_description": True,
                "publish_robot_description_semantic": True,
                "allow_trajectory_execution": True,
                "trajectory_execution": {
                    "allowed_execution_duration_scaling": 1.2,
                    "allowed_goal_duration_margin": 0.5,
                    "execution_duration_monitoring": True,
                },
                "planning_scene_monitor_parameters": {
                    "publish_planning_scene": True,
                    "publish_geometry_updates": True,
                    "publish_state_updates": True,
                    "publish_transforms_updates": True,
                },
            },
        ],
    )

    # RViz is opt-in so headless/mock launches do not require an X server.
    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="moveit_rviz",
        arguments=["-d", str(rviz_file)],
        parameters=[
            {"robot_description": robot_description},
            {"robot_description_semantic": robot_description_semantic},
            {"robot_description_kinematics": robot_description_kinematics},
            {"robot_description_planning": robot_description_planning},
        ],
        output="screen",
        condition=IfCondition(start_rviz),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("usb_port", default_value="/dev/so101_follower"),
            DeclareLaunchArgument("start_rviz", default_value="false"),
            move_group,
            rviz,
        ]
    )
