"""SLAM で構築した地図をファイルに保存する。

nav.launch.py が動いている状態で呼び出す。

    ros2 run lekiwi_base_bringup save_map             # → /maps/my_room
    ros2 run lekiwi_base_bringup save_map living_room # → /maps/living_room
    ros2 run lekiwi_base_bringup save_map /tmp/test   # 絶対パスも可

/maps/ はコンテナ起動時にホストの MAP_DIR をマウントしたディレクトリ。
ホストから確認するには MAP_DIR (既定: ~/maps) を参照。

nav.launch.py が (start_slam:=true のとき) map_saver_server を起動して
/map_saver/save_map サービスを提供しているため、そのサービスを呼び出して
yaml + pgm を生成する。
"""

from __future__ import annotations

import sys

import rclpy
import rclpy.utilities
from nav2_msgs.srv import SaveMap
from rclpy.node import Node


def main(args=None) -> None:
    rclpy.init(args=args)

    # ROS 固有の引数 (--ros-args 以降) を除いてユーザー引数だけ取り出す
    user_args = rclpy.utilities.remove_ros_args(sys.argv[1:])
    name = user_args[0] if user_args else "my_room"

    # 相対名なら /maps/ を付ける、絶対パスならそのまま
    output = name if name.startswith("/") else f"/maps/{name}"

    node = Node("map_saver_client")
    client = node.create_client(SaveMap, "/map_saver/save_map")

    node.get_logger().info("map_saver サービスを待機中 (最大 10 秒)...")
    if not client.wait_for_service(timeout_sec=10.0):
        node.get_logger().error(
            "/map_saver/save_map サービスが見つかりません。\n"
            "nav.launch.py (または compose.nav.yaml) が起動しているか確認してください。"
        )
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    req = SaveMap.Request()
    req.map_url = output
    req.image_format = "pgm"
    req.map_mode = "trinary"
    req.free_thresh = 0.25
    req.occupied_thresh = 0.65

    node.get_logger().info(f"保存先: {output}.yaml / {output}.pgm")
    future = client.call_async(req)
    rclpy.spin_until_future_complete(node, future, timeout_sec=15.0)

    if not future.done():
        node.get_logger().error("タイムアウト: map_saver が 15 秒以内に応答しませんでした")
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    if future.result().result:
        node.get_logger().info(f"保存完了: {output}.yaml")
    else:
        node.get_logger().error("保存に失敗しました (map_saver が false を返しました)")
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
