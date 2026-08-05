"""LeKiwi ベース + SO-101 アームで map 上の点へリーチする合成 launch。

この launch が「唯一の合成点」で、次の 3 つを 1 つに束ねる:

  1. 結合ロボット全体の robot_state_publisher (このプロセスに 1 つだけ)
  2. ベース側 (base_driver + scan_filter + slam_toolbox + Nav2)
  3. アーム側 (LeRobot ブリッジ + ros2_control + spawner)

★ ベース側とアーム側の launch は start_robot_state_publisher:=false で include する。
  /robot_description は TRANSIENT_LOCAL / depth 1 なので publisher が複数あると
  後から繋いだ購読者がどれを掴むか非決定になる。

★ RViz もこの launch が 1 つだけ起動する。両方の include で start_rviz:=false。
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    share = Path(get_package_share_directory("lekiwi_so101_bringup"))
    base_launch_dir = Path(get_package_share_directory("lekiwi_base_bringup")) / "launch"
    arm_launch_dir = Path(get_package_share_directory("so101_bringup")) / "launch"

    xacro_file = share / "urdf" / "lekiwi_so101.urdf.xacro"

    sim = LaunchConfiguration("sim")
    backend = LaunchConfiguration("backend")
    joint_prefix = LaunchConfiguration("joint_prefix")
    usb_port = LaunchConfiguration("usb_port")
    robot_id = LaunchConfiguration("robot_id")
    start_rviz = LaunchConfiguration("start_rviz")
    start_lidar = LaunchConfiguration("start_lidar")
    rviz_config = LaunchConfiguration("rviz_config")
    controllers_file = LaunchConfiguration("controllers_file")
    reach_params_file = LaunchConfiguration("reach_params_file")

    # ★ TBD の実測値をここから上書きできるようにしておく。既定は URDF 側の 0。
    mount = {
        key: LaunchConfiguration(f"arm_mount_{key}")
        for key in ("x", "y", "z", "roll", "pitch", "yaw")
    }

    robot_description = ParameterValue(
        Command(
            [
                "xacro ",
                str(xacro_file),
                " use_mesh:=false",
                " prefix:=",
                joint_prefix,
                " usb_port:=",
                usb_port,
            ]
            + [
                token
                for key, value in mount.items()
                for token in (f" arm_mount_{key}:=", value)
            ]
        ),
        value_type=str,
    )

    shared_base_args = {
        # この launch が唯一の RSP と RViz を持つ。
        "start_robot_state_publisher": "false",
        "start_rviz": "false",
    }

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "sim",
                default_value="false",
                description="true: 実機に触れず sim_nav (dry_run + fake_scan) を使う",
            ),
            DeclareLaunchArgument(
                "backend",
                default_value="mock",
                description="mock: シリアルを開かない / lerobot: 実機の SO-101",
            ),
            DeclareLaunchArgument(
                "joint_prefix",
                default_value="arm_",
                description="結合 URDF・controllers_file・リーチノードで必ず一致させること",
            ),
            DeclareLaunchArgument("usb_port", default_value="/dev/so101_follower"),
            DeclareLaunchArgument(
                "robot_id",
                default_value="",
                description="backend:=lerobot では必須の LeRobot 較正 ID",
            ),
            DeclareLaunchArgument(
                "controllers_file",
                default_value=str(share / "config" / "ros2_controllers.yaml"),
            ),
            DeclareLaunchArgument(
                "reach_params_file",
                default_value=str(share / "config" / "reach.yaml"),
            ),
            DeclareLaunchArgument("start_rviz", default_value="true"),
            DeclareLaunchArgument(
                "start_lidar",
                default_value="false",
                description="false: /scan は rplidar コンテナ等の外部に任せる",
            ),
            DeclareLaunchArgument(
                "rviz_config", default_value=str(share / "rviz" / "reach.rviz")
            ),
            # ★ 実測待ち。arm_mount_link から見たアーム基部の姿勢。
            #   docs/agent/request.md の手順 0 / 3 で確定させる。
            DeclareLaunchArgument("arm_mount_x", default_value="0.0"),
            DeclareLaunchArgument("arm_mount_y", default_value="0.0"),
            DeclareLaunchArgument("arm_mount_z", default_value="0.0"),
            DeclareLaunchArgument("arm_mount_roll", default_value="0.0"),
            DeclareLaunchArgument("arm_mount_pitch", default_value="0.0"),
            DeclareLaunchArgument("arm_mount_yaw", default_value="0.0"),
            # ---- 唯一の robot_state_publisher ----
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="robot_state_publisher",
                output="screen",
                parameters=[{"robot_description": robot_description}],
            ),
            # ---- ベース側 ----
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(base_launch_dir / "nav.launch.py")),
                launch_arguments=[
                    *shared_base_args.items(),
                    ("start_lidar", start_lidar),
                ],
                condition=UnlessCondition(sim),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(base_launch_dir / "sim_nav.launch.py")
                ),
                launch_arguments=list(shared_base_args.items()),
                condition=IfCondition(sim),
            ),
            # ---- アーム側 ----
            # follower.launch.py の起動順序 (bridge 待ち -> control_node ->
            # 直列 spawner -> bridge 終了で shutdown) をそのまま再利用する。
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(arm_launch_dir / "follower.launch.py")
                ),
                launch_arguments=[
                    *shared_base_args.items(),
                    ("backend", backend),
                    ("usb_port", usb_port),
                    ("robot_id", robot_id),
                    ("description_file", str(xacro_file)),
                    ("joint_prefix", joint_prefix),
                    ("controllers_file", controllers_file),
                ],
            ),
            # ---- リーチ ----
            Node(
                package="so101_bringup",
                executable="so101_reach_to_point",
                name="so101_reach_to_point",
                output="screen",
                parameters=[reach_params_file, {"joint_prefix": joint_prefix}],
            ),
            # ---- 唯一の RViz ----
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
