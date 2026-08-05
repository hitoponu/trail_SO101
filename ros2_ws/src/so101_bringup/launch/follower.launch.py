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
    description_file = LaunchConfiguration("description_file")
    joint_prefix = LaunchConfiguration("joint_prefix")
    start_robot_state_publisher = LaunchConfiguration("start_robot_state_publisher")
    start_rviz = LaunchConfiguration("start_rviz")
    rviz_config = LaunchConfiguration("rviz_config")

    bringup_share = Path(get_package_share_directory("so101_bringup"))
    description_share = Path(get_package_share_directory("so_arm101_description"))
    control_file = bringup_share / "control" / "so101_follower.ros2_control.xacro"

    # The upstream description still requires legacy xacro argument names. The
    # selected control file ignores their values and always uses the ROS topic
    # hardware adapter; backend selection belongs only to the bridge.
    #
    # `description_file` is overridable so a composed robot (arm bolted onto the
    # LeKiwi base) can reuse the startup ordering below instead of duplicating
    # it. Both the upstream top-level xacro and the composed one accept the same
    # four arguments, so this substitution is shared.
    robot_description = ParameterValue(
        Command(
            [
                "xacro ",
                description_file,
                " ros2_control_hardware_type:=real",
                " usb_port:=",
                usb_port,
                " ros2_control_file:=",
                str(control_file),
                " prefix:=",
                joint_prefix,
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
                "joint_prefix": joint_prefix,
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
            DeclareLaunchArgument(
                "description_file",
                default_value=str(
                    description_share / "urdf" / "so_arm101.urdf.xacro"
                ),
                description="Top-level xacro; override to launch a composed robot",
            ),
            DeclareLaunchArgument(
                "joint_prefix",
                default_value="",
                description=(
                    "Prefix applied to every link AND joint name by the upstream "
                    "macro; must match the controllers file"
                ),
            ),
            # /robot_description is TRANSIENT_LOCAL with depth 1. A second
            # publisher makes late-joining subscribers latch either sample
            # non-deterministically, which is the "RViz shows a different robot"
            # symptom recorded in CLAUDE.md. A composed launch starts its own
            # publisher for the whole robot and sets this to false.
            DeclareLaunchArgument(
                "start_robot_state_publisher", default_value="true"
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
                condition=IfCondition(start_robot_state_publisher),
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
