"""Publish base-frame Cartesian velocity commands from an X11 keyboard."""

from __future__ import annotations

import threading

import rclpy
from geometry_msgs.msg import TwistStamped
from rclpy.node import Node

from lekiwi_examples.cartesian_math import KEY_DIRECTIONS, velocity_from_keys


class KeyboardInput(Node):
    def __init__(self) -> None:
        super().__init__("so101_keyboard_input")
        self.declare_parameter("linear_speed", 0.02)
        self.declare_parameter("publish_rate", 20.0)
        self.declare_parameter("command_topic", "/so101/cartesian_twist")
        self.declare_parameter("command_frame", "base_link")

        self._speed = float(self.get_parameter("linear_speed").value)
        rate = float(self.get_parameter("publish_rate").value)
        self._frame = str(self.get_parameter("command_frame").value)
        self._publisher = self.create_publisher(
            TwistStamped, str(self.get_parameter("command_topic").value), 10
        )
        self._pressed: set[str] = set()
        self._lock = threading.Lock()
        self._quit_requested = False
        self._listener = self._start_listener()
        self._timer = self.create_timer(1.0 / rate, self._publish)
        self.get_logger().info(
            "操作開始: W/S=+X/-X, A/D=+Y/-Y, R/F=+Z/-Z, Q/Esc=終了 "
            f"(base_link, {self._speed:.3f} m/s)"
        )
        self.get_logger().warn("起動中は X11 のキーボード入力をグローバルに取得します")

    def _start_listener(self):
        try:
            from pynput import keyboard

            def on_press(key):
                if key == keyboard.Key.esc:
                    self._quit_requested = True
                    return False
                try:
                    character = key.char.lower()
                except (AttributeError, TypeError):
                    return None
                if character == "q":
                    self._quit_requested = True
                    return False
                if character in KEY_DIRECTIONS:
                    with self._lock:
                        self._pressed.add(character)
                return None

            def on_release(key):
                try:
                    character = key.char.lower()
                except (AttributeError, TypeError):
                    return
                with self._lock:
                    self._pressed.discard(character)

            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.start()
            return listener
        except Exception as exc:
            raise RuntimeError(
                "X11 キーボードを開始できません。DISPLAY と xhost 設定を確認してください"
            ) from exc

    def _message(self, velocity) -> TwistStamped:
        message = TwistStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = self._frame
        message.twist.linear.x = float(velocity[0])
        message.twist.linear.y = float(velocity[1])
        message.twist.linear.z = float(velocity[2])
        return message

    def _publish(self) -> None:
        with self._lock:
            velocity = velocity_from_keys(self._pressed, self._speed)
        self._publisher.publish(self._message(velocity))
        if self._quit_requested:
            self._publisher.publish(self._message(velocity * 0.0))
            rclpy.shutdown()

    def stop(self) -> None:
        if rclpy.ok():
            self._publisher.publish(self._message(velocity_from_keys(set(), self._speed)))
        self._listener.stop()


def main() -> None:
    rclpy.init()
    node = None
    try:
        node = KeyboardInput()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        if node is None:
            print(f"so101_keyboard_input: {exc}")
        else:
            node.get_logger().error(str(exc))
        raise SystemExit(1)
    finally:
        if node is not None:
            node.stop()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
