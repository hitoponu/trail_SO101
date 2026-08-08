"""アームの手先をデカルト座標 (XYZ) でジョグする。

    # ① 別ターミナルでロボットを起動しておく
    ros2 launch lekiwi_so101_bringup robot.launch.py backend:=lerobot robot_id:=my_follower

    # ② こちらを起動する
    ros2 launch lekiwi_examples cartesian_teleop.launch.py

キー: w/s = +x/-x, a/d = +y/-y, r/f = +z/-z

★ 関節ごとに動かしたいときは `ros2 run lekiwi_examples teleop_keyboard`。
  あちらはベースも同時に操作できる。
"""

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
    joint_prefix = LaunchConfiguration("joint_prefix")

    jog = Node(
        package="lekiwi_examples",
        executable="cartesian_jog",
        output="screen",
        parameters=[{
            "joint_prefix": joint_prefix,
            "control_rate": control_rate,
            "trajectory_horizon": trajectory_horizon,
            "max_joint_velocity": max_joint_velocity,
            "joint_limit_margin": joint_limit_margin,
            "command_timeout": command_timeout,
            "damping": damping,
        }],
    )
    keyboard = Node(
        package="lekiwi_examples",
        executable="cartesian_keyboard",
        output="screen",
        parameters=[{"linear_speed": linear_speed, "publish_rate": control_rate}],
    )

    return LaunchDescription([
        # ★ 結合ロボット (robot.launch.py) では関節名に arm_ が付く。
        #   アーム単体 (arm.launch.py を joint_prefix:="" で起動) なら空にする。
        DeclareLaunchArgument("joint_prefix", default_value="arm_"),
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
