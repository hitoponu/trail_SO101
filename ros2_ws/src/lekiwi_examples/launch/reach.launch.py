"""map 上の点へアームを伸ばすリーチノードを起動する。

    # ① 別ターミナルでロボットを起動しておく
    ros2 launch lekiwi_so101_bringup robot.launch.py backend:=lerobot robot_id:=my_follower

    # ② こちらを起動する
    ros2 launch lekiwi_examples reach.launch.py

★ **ロボットが起動していることが前提**。このノードはハードウェアに直接触らず、
  ROS のインターフェースだけを使う:

    /clicked_point  (RViz の "Publish Point")  ─┐
    /so101/reach_target                        ─┴─> リーチノード
    /robot_description, /joint_states, /tf     ───> 現在姿勢と URDF
                                                 └─> FollowJointTrajectory アクション

★ joint_prefix は robot.launch.py 側と必ず一致させること (既定 arm_)。
  結合 URDF では上流マクロがリンク名だけでなく関節名にも接頭辞を付ける。
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory("lekiwi_examples"))

    return LaunchDescription([
        DeclareLaunchArgument(
            "params_file",
            default_value=str(share / "config" / "reach.yaml"),
            description="リーチのパラメータ。到達半径・床のガード・停滞判定など",
        ),
        DeclareLaunchArgument(
            "joint_prefix",
            default_value="arm_",
            description="★ robot.launch.py と必ず一致させること",
        ),
        Node(
            package="lekiwi_examples",
            executable="reach_to_point",
            name="so101_reach_to_point",
            output="screen",
            parameters=[
                LaunchConfiguration("params_file"),
                {"joint_prefix": LaunchConfiguration("joint_prefix")},
            ],
        ),
    ])
