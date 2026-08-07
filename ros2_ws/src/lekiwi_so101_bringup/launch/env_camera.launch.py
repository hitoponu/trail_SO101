"""環境固定 RealSense を map へ繋ぐ static TF。

カメラは三脚などに据え置き、ロボットには載せない。したがって
`map -> env_camera_link` は「その設置での定数」であり、較正して求める。

★ map の原点はロボットが起動した位置であって床の印ではない。
  slam_toolbox で毎回地図を作り直すと map 原点が変わり、この較正値は無効になる。
  **保存済み地図 + amcl (nav_with_map.launch.py) での運用が前提。**

★ 既定値は未実測の仮値 (ENV_CAMERA_*_TBD)。この repo の laser_xyz_TBD /
  camera_xyz_TBD と同じ流儀で、実測が返るまで「置いてあるだけ」の値。
  較正手順は docs/env_camera_calibration.md。

mock_optical_frames:=true にすると、カメラ実機が無い環境でも
env_camera_link -> env_camera_depth_optical_frame を static で生やし、
TF ツリーの疎通と座標変換の向きだけを Mac で検証できる。
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    camera_name = LaunchConfiguration("camera_name")
    parent_frame = LaunchConfiguration("parent_frame")
    mock_optical_frames = LaunchConfiguration("mock_optical_frames")

    xyzrpy = [LaunchConfiguration(f"env_camera_{k}") for k in
              ("x", "y", "z", "roll", "pitch", "yaw")]

    return LaunchDescription([
        DeclareLaunchArgument("camera_name", default_value="env_camera"),
        DeclareLaunchArgument(
            "parent_frame",
            default_value="map",
            description="★ 較正値を凍結するフレーム。map 以外にすると "
                        "保存地図の運用前提が崩れる",
        ),
        # ★ 較正値。既定は環境変数 ENV_CAMERA_* から読む。
        #   env_camera_calib の出力を .env に貼れば、compose の environment 経由で
        #   ここに届く。launch 行に 6 個の引数を手打ちする必要は無い。
        #   環境変数も無ければ未実測の仮値になる（RViz でマゼンタ相当の扱い）。
        *(DeclareLaunchArgument(f"env_camera_{key}",
                                default_value=os.environ.get(f"ENV_CAMERA_{key.upper()}",
                                                             fallback))
          for key, fallback in (("x", "1.5"), ("y", "0.0"), ("z", "1.0"),
                                ("roll", "0.0"), ("pitch", "0.4"), ("yaw", "3.14159"))),
        DeclareLaunchArgument(
            "mock_optical_frames",
            default_value="false",
            description="カメラ実機なしで光学フレームを模す (Mac 検証用)",
        ),

        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="env_camera_tf",
            output="screen",
            arguments=[
                "--x", xyzrpy[0], "--y", xyzrpy[1], "--z", xyzrpy[2],
                "--roll", xyzrpy[3], "--pitch", xyzrpy[4], "--yaw", xyzrpy[5],
                "--frame-id", parent_frame,
                "--child-frame-id", [camera_name, "_link"],
            ],
        ),

        # ★ 実機では realsense2_camera がこの TF を自分で /tf_static へ出すので
        #   起動しないこと (二重定義になる)。Mac 検証専用。
        #
        #   REP-103 のボディ座標 (x前 y左 z上) から光学座標 (x右 y下 z前) への
        #   変換は rpy = (-pi/2, 0, -pi/2)。realsense2_camera が出すものと同じ。
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="env_camera_optical_tf_mock",
            output="screen",
            condition=IfCondition(mock_optical_frames),
            arguments=[
                "--x", "0", "--y", "0", "--z", "0",
                "--roll", "-1.5707963", "--pitch", "0", "--yaw", "-1.5707963",
                "--frame-id", [camera_name, "_link"],
                "--child-frame-id", [camera_name, "_depth_optical_frame"],
            ],
        ),
    ])
