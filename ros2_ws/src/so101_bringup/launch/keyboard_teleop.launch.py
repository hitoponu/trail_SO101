"""Start the opt-in SO-101 XYZ keyboard teleoperation nodes."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    linear_speed = LaunchConfiguration("linear_speed")
    control_rate = LaunchConfiguration("control_rate")
    trajectory_horizon = LaunchConfiguration("trajectory_horizon")
    max_joint_velocity = LaunchConfiguration("max_joint_velocity")
    joint_limit_margin = LaunchConfiguration("joint_limit_margin")
    command_timeout = LaunchConfiguration("command_timeout")
    damping = LaunchConfiguration("damping")

    jog = Node(
        package="so101_bringup",
        executable="so101_cartesian_jog",
        output="screen",
        parameters=[{
            "control_rate": control_rate,
            "trajectory_horizon": trajectory_horizon,
            "max_joint_velocity": max_joint_velocity,
            "joint_limit_margin": joint_limit_margin,
            "command_timeout": command_timeout,
            "damping": damping,
        }],
    )
    keyboard = Node(
        package="so101_bringup",
        executable="so101_keyboard_input",
        output="screen",
        parameters=[{"linear_speed": linear_speed, "publish_rate": control_rate}],
    )

    return LaunchDescription([
        DeclareLaunchArgument("linear_speed", default_value="0.02"),
        DeclareLaunchArgument("control_rate", default_value="20.0"),
        DeclareLaunchArgument("trajectory_horizon", default_value="0.10"),
        DeclareLaunchArgument("max_joint_velocity", default_value="0.5"),
        DeclareLaunchArgument("joint_limit_margin", default_value="0.10"),
        DeclareLaunchArgument("command_timeout", default_value="0.20"),
        DeclareLaunchArgument("damping", default_value="0.03"),
        jog,
        keyboard,
        RegisterEventHandler(OnProcessExit(
            target_action=keyboard,
            on_exit=[EmitEvent(event=Shutdown(reason="keyboard teleop exited"))],
        )),
    ])
