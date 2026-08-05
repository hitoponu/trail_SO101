"""Launch the SO-101 with ros2_control over a thin LeRobot bridge."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    RegisterEventHandler,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    backend = LaunchConfiguration("backend")
    usb_port = LaunchConfiguration("usb_port")
    robot_id = LaunchConfiguration("robot_id")
    calibration_dir = LaunchConfiguration("calibration_dir")
    controllers_file = LaunchConfiguration("controllers_file")
    start_rviz = LaunchConfiguration("start_rviz")
    rviz_config = LaunchConfiguration("rviz_config")

    bringup_share = Path(get_package_share_directory("so101_bringup"))
    description_share = Path(get_package_share_directory("so_arm101_description"))
    xacro_file = description_share / "urdf" / "so_arm101.urdf.xacro"
    control_file = bringup_share / "control" / "so101_follower.ros2_control.xacro"

    # The upstream description still requires legacy xacro argument names. The
    # selected control file ignores their values and always uses the ROS topic
    # hardware adapter; backend selection belongs only to the bridge.
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

    bridge = Node(
        package="so101_bringup",
        executable="so101_lerobot_bridge",
        name="lerobot_bridge",
        output="screen",
        parameters=[
            {
                "backend": backend,
                "usb_port": usb_port,
                "robot_id": robot_id,
                "calibration_dir": calibration_dir,
                "robot_description": robot_description,
                "update_rate": 50.0,
                "command_timeout": 0.5,
            }
        ],
    )

    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        output="screen",
        parameters=[controllers_file],
        remappings=[("~/robot_description", "/robot_description")],
    )

    def spawner(name):
        return Node(
            package="controller_manager",
            executable="spawner",
            arguments=[name, "--controller-manager", "/controller_manager"],
            output="screen",
        )

    jsb = spawner("joint_state_broadcaster")
    jtc = spawner("joint_trajectory_controller")
    gripper = spawner("gripper_controller")

    # `ros2 service call` waits for the service to appear. The service is
    # created only after calibration validation and backend connection finish.
    wait_for_bridge = ExecuteProcess(
        cmd=[
            "ros2",
            "service",
            "call",
            "/so101/lerobot_bridge/ready",
            "std_srvs/srv/Trigger",
            "{}",
        ],
        output="screen",
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "backend",
                default_value="mock",
                description="mock: no serial access / lerobot: physical SO-101",
            ),
            DeclareLaunchArgument("usb_port", default_value="/dev/so101_follower"),
            DeclareLaunchArgument(
                "robot_id",
                default_value="",
                description="LeRobot calibration ID; required for backend:=lerobot",
            ),
            DeclareLaunchArgument(
                "calibration_dir",
                default_value=(
                    "/root/.cache/huggingface/lerobot/calibration/robots/so_follower"
                ),
            ),
            DeclareLaunchArgument(
                "controllers_file",
                default_value=str(bringup_share / "config" / "ros2_controllers.yaml"),
            ),
            DeclareLaunchArgument("start_rviz", default_value="true"),
            DeclareLaunchArgument(
                "rviz_config",
                default_value=str(description_share / "rviz" / "config.rviz"),
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="robot_state_publisher",
                output="screen",
                parameters=[{"robot_description": robot_description}],
            ),
            bridge,
            wait_for_bridge,
            RegisterEventHandler(
                OnProcessExit(target_action=wait_for_bridge, on_exit=[control_node])
            ),
            # Spawners wait for controller_manager, then are serialized to avoid
            # competing load/configure requests during startup.
            jsb,
            RegisterEventHandler(OnProcessExit(target_action=jsb, on_exit=[jtc])),
            RegisterEventHandler(OnProcessExit(target_action=jtc, on_exit=[gripper])),
            RegisterEventHandler(
                OnProcessExit(
                    target_action=bridge,
                    on_exit=[EmitEvent(event=Shutdown(reason="LeRobot bridge exited"))],
                )
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="rviz2",
                arguments=["-d", rviz_config],
                condition=IfCondition(start_rviz),
                output="screen",
            ),
        ]
    )
