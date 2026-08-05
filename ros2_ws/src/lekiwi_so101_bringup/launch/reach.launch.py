"""結合ロボット (LeKiwi ベース + SO-101 アーム) のアーム側 launch。

この launch が起動するもの:

  1. **結合ロボット全体**の robot_state_publisher (システム全体でこれ 1 つだけ)
  2. アーム側 (LeRobot ブリッジ + ros2_control + spawner) — follower.launch.py を include
  3. リーチノード
  4. RViz (システム全体でこれ 1 つだけ)

★ ベース側 (base_driver / scan_filter / slam_toolbox / Nav2) はここでは起動しない。
  それらは lekiwi_base_bringup と nav2/slam_toolbox に依存しており、
  このイメージには入っていない (アームのイメージにはメッシュと LeRobot が入る代わりに
  ベース側の依存は入れていない)。ベース側は別コンテナで

      ros2 launch lekiwi_base_bringup nav.launch.py \
        start_robot_state_publisher:=false start_rviz:=false

  として起動すること。docker/lekiwi_so101_bringup/compose.yaml がそうしている。

★ なぜ RSP をこちらが持つのか
  結合 URDF は lekiwi_description と so_arm101_description の両方を必要とし、
  両方を $(find) できるのはこのイメージだけ。xacro の $(find) はローカルの
  ファイルシステムを見るので、DDS では橋渡しできない。
  /robot_description は TRANSIENT_LOCAL / depth 1 なので publisher が 2 つあると
  後から繋いだ購読者がどちらの latch を掴むか非決定になる
  (CLAUDE.md の「RViz に別のロボットが出る」症状)。
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    share = Path(get_package_share_directory("lekiwi_so101_bringup"))
    arm_launch_dir = Path(get_package_share_directory("so101_bringup")) / "launch"
    xacro_file = share / "urdf" / "lekiwi_so101.urdf.xacro"

    backend = LaunchConfiguration("backend")
    joint_prefix = LaunchConfiguration("joint_prefix")
    usb_port = LaunchConfiguration("usb_port")
    robot_id = LaunchConfiguration("robot_id")
    start_rviz = LaunchConfiguration("start_rviz")
    rviz_config = LaunchConfiguration("rviz_config")
    controllers_file = LaunchConfiguration("controllers_file")
    reach_params_file = LaunchConfiguration("reach_params_file")

    mount_keys = ("x", "y", "z", "roll", "pitch", "yaw")

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
                for key in mount_keys
                for token in (
                    f" arm_mount_{key}:=",
                    LaunchConfiguration(f"arm_mount_{key}"),
                )
            ]
        ),
        value_type=str,
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "backend",
                default_value="mock",
                description="mock: シリアルを開かない / lerobot: 実機の SO-101",
            ),
            DeclareLaunchArgument(
                "joint_prefix",
                default_value="arm_",
                description=(
                    "結合 URDF・controllers_file・リーチノードで必ず一致させること。"
                    "上流マクロはリンク名だけでなく関節名にも適用する"
                ),
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
                "rviz_config", default_value=str(share / "rviz" / "reach.rviz")
            ),
            # ★ 実測待ち。arm_mount_link から見たアーム基部の姿勢。
            #   arm_mount_link 自体 (base_link から 0.08,-0.04,0.057) も CAD 由来で未実測。
            #   docs/agent/request.md の手順 0 / 3 で確定させる。
            *(
                DeclareLaunchArgument(f"arm_mount_{key}", default_value="0.0")
                for key in mount_keys
            ),
            # ---- システム全体で唯一の robot_state_publisher ----
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="robot_state_publisher",
                output="screen",
                parameters=[{"robot_description": robot_description}],
            ),
            # ---- アーム側 ----
            # follower.launch.py の起動順序 (bridge 待ち -> control_node ->
            # 直列 spawner -> bridge 終了で shutdown) をそのまま再利用する。
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(arm_launch_dir / "follower.launch.py")
                ),
                launch_arguments=[
                    ("start_robot_state_publisher", "false"),
                    ("start_rviz", "false"),
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
            # ---- システム全体で唯一の RViz ----
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
