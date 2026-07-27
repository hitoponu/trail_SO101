"""SO-101 follower アームの起動。

    # モックでのドライラン (シリアルを一切開かない。既定)
    ros2 launch so101_bringup follower.launch.py

    # 実機
    ros2 launch so101_bringup follower.launch.py \
        ros2_control_hardware_type:=real usb_port:=/dev/so101_follower

★ 既定が mock_components なのは意図的。引数なしでは実機に触れない。

キーボード/GUI からの操作は含めない。JTC 越しに動かすには別ターミナルから:

    ros2 run rqt_joint_trajectory_controller rqt_joint_trajectory_controller
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    hardware_type = LaunchConfiguration("ros2_control_hardware_type")
    usb_port = LaunchConfiguration("usb_port")
    joint_config_file = LaunchConfiguration("joint_config_file")
    controllers_file = LaunchConfiguration("controllers_file")
    start_rviz = LaunchConfiguration("start_rviz")
    rviz_config = LaunchConfiguration("rviz_config")

    bringup_share = Path(get_package_share_directory("so101_bringup"))
    description_share = Path(get_package_share_directory("so_arm101_description"))

    xacro_file = description_share / "urdf" / "so_arm101.urdf.xacro"
    # ★ 上流の ros2_control xacro は使わない (offset が無視される / p_cofficient の
    #   綴り間違い / joint_config_file が無い の3つのバグがある)。
    #   親 xacro の ros2_control_file 引数で自前のものへ差し替える。
    ros2_control_file = bringup_share / "control" / "so101_follower.ros2_control.xacro"

    # ParameterValue(..., value_type=str) は Jazzy では必須。
    # 無いと Command の出力が文字列として扱われず robot_state_publisher が落ちる。
    robot_description = ParameterValue(
        Command([
            "xacro ", str(xacro_file),
            " ros2_control_hardware_type:=", hardware_type,
            " usb_port:=", usb_port,
            " ros2_control_file:=", str(ros2_control_file),
            " joint_config_file:=", joint_config_file,
        ]),
        value_type=str,
    )

    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        output="screen",
        parameters=[controllers_file],
        # Jazzy の controller_manager はこの remap でロボット記述を受け取る
        remappings=[("~/robot_description", "/robot_description")],
    )

    def spawner(name, *extra):
        return Node(
            package="controller_manager",
            executable="spawner",
            arguments=[name, "--controller-manager", "/controller_manager", *extra],
            output="screen",
        )

    # joint_state_broadcaster を先に上げ、その終了を待って他を上げる。
    # 同時に spawn すると controller_manager が取り合って失敗することがある。
    jsb = spawner("joint_state_broadcaster")
    jtc = spawner("joint_trajectory_controller")
    grip = spawner("gripper_controller")
    # JTC と同じ command interface を要求するので inactive で置いておく。
    # 有効化すると補間なしで指令が飛ぶ (driver の速度は 2400 ≒ 210 deg/s 固定)。
    fwd = spawner("forward_position_controller", "--inactive")

    return LaunchDescription([
        DeclareLaunchArgument(
            "ros2_control_hardware_type",
            default_value="mock_components",
            description="mock_components: 実機に触れないドライラン / real: 実機",
        ),
        DeclareLaunchArgument("usb_port", default_value="/dev/so101_follower"),
        DeclareLaunchArgument(
            "joint_config_file",
            default_value=str(bringup_share / "config" / "so101_joints.yaml"),
        ),
        DeclareLaunchArgument(
            "controllers_file",
            default_value=str(bringup_share / "config" / "ros2_controllers.yaml"),
        ),
        DeclareLaunchArgument("start_rviz", default_value="true"),
        DeclareLaunchArgument(
            "rviz_config",
            # 上流の RViz 設定をそのまま使う (Grid + RobotModel + TF)
            default_value=str(description_share / "rviz" / "config.rviz"),
        ),

        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            output="screen",
            parameters=[{"robot_description": robot_description}],
        ),

        control_node,
        jsb,
        RegisterEventHandler(OnProcessExit(target_action=jsb, on_exit=[jtc])),
        RegisterEventHandler(OnProcessExit(target_action=jtc, on_exit=[grip])),
        RegisterEventHandler(OnProcessExit(target_action=grip, on_exit=[fwd])),

        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            arguments=["-d", rviz_config],
            condition=IfCondition(start_rviz),
            output="screen",
        ),
    ])
