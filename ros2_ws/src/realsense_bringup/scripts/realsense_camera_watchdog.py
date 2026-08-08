#!/usr/bin/env python3
"""Restart the RealSense node when a disconnected V4L2 device is detected.

The upstream ``reconnect_timeout`` handles device discovery retries, but it
does not stop a streaming node whose V4L2 file descriptors are already stale.
In that state librealsense can emit ``VIDIOC_QBUF`` errors in a tight loop and
make shutdown unnecessarily slow.  This wrapper keeps the ROS arguments
unchanged, forwards the child's output, and restarts it after a recoverable
V4L2/USB error.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import threading
from typing import Optional


ERROR_MARKERS = (
    "VIDIOC_QBUF",
    "No such device",
    "map_device_descriptor",
    "Failed to start device",
)


class CameraWatchdog:
    def __init__(self, child_args: list[str], restart_delay: float) -> None:
        self.child_args = child_args
        self.restart_delay = max(0.5, restart_delay)
        self.stop_requested = threading.Event()
        self.child: Optional[subprocess.Popen[str]] = None

    def request_stop(self, _signum: int, _frame: object) -> None:
        self.stop_requested.set()
        self._terminate_child()

    def _terminate_child(self) -> None:
        child = self.child
        if child is None or child.poll() is not None:
            return

        try:
            # The child starts a new process group so a shutdown also reaches
            # any helper threads/processes created by librealsense.
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        try:
            child.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    @staticmethod
    def _node_path() -> str:
        found = shutil.which("realsense2_camera_node")
        if found:
            return found

        ros_distro = os.environ.get("ROS_DISTRO", "jazzy")
        candidates = (
            Path("/opt/ros") / ros_distro / "lib/realsense2_camera/realsense2_camera_node",
        )
        for candidate in candidates:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)

        raise FileNotFoundError("realsense2_camera_node が見つかりません")

    @staticmethod
    def _is_recoverable_error(line: str) -> bool:
        return any(marker in line for marker in ERROR_MARKERS)

    def run(self) -> int:
        node_path = self._node_path()
        print(
            f"[realsense_watchdog] node={node_path} "
            f"restart_delay={self.restart_delay:g}s",
            file=sys.stderr,
            flush=True,
        )

        while not self.stop_requested.is_set():
            restart_requested = False
            print("[realsense_watchdog] RealSenseノードを起動します", file=sys.stderr, flush=True)
            try:
                self.child = subprocess.Popen(
                    [node_path, *self.child_args],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )
            except OSError as exc:
                print(f"[realsense_watchdog] 起動失敗: {exc}", file=sys.stderr, flush=True)
                if self.stop_requested.wait(self.restart_delay):
                    break
                continue

            assert self.child.stdout is not None
            for line in self.child.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                if (
                    not self.stop_requested.is_set()
                    and self._is_recoverable_error(line)
                ):
                    restart_requested = True
                    print(
                        "[realsense_watchdog] V4L2/USB切断エラーを検出したため、"
                        "RealSenseノードを再起動します",
                        file=sys.stderr,
                        flush=True,
                    )
                    self._terminate_child()
                    break

            return_code = self.child.wait()
            self.child = None
            if self.stop_requested.is_set():
                break

            if not restart_requested:
                print(
                    f"[realsense_watchdog] RealSenseノードが終了しました "
                    f"(code={return_code})。再起動します",
                    file=sys.stderr,
                    flush=True,
                )

            if self.stop_requested.wait(self.restart_delay):
                break

        self._terminate_child()
        return 0


def parse_args() -> tuple[float, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--watchdog-restart-delay",
        type=float,
        default=float(os.environ.get("REALSENSE_WATCHDOG_RESTART_DELAY", "6.0")),
    )
    options, child_args = parser.parse_known_args()
    return options.watchdog_restart_delay, child_args


def main() -> int:
    restart_delay, child_args = parse_args()
    watchdog = CameraWatchdog(child_args, restart_delay)
    signal.signal(signal.SIGINT, watchdog.request_stop)
    signal.signal(signal.SIGTERM, watchdog.request_stop)
    return watchdog.run()


if __name__ == "__main__":
    raise SystemExit(main())
