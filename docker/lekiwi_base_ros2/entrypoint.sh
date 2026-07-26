#!/usr/bin/env bash
set -e

source /opt/ros/jazzy/setup.bash
source /ros2_ws/install/setup.bash

if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
  mkdir -p "${XDG_RUNTIME_DIR}"
  chmod 700 "${XDG_RUNTIME_DIR}"
fi

# exec はシグナル伝達に必須。この後に処理を足さないこと。
# SIGINT がドライバに届かないと、停止処理(速度ゼロ + トルクOFF)が走らず
# ホイールが最後の指令速度で回り続ける。
exec "$@"
