#!/usr/bin/env bash
set -e

source /opt/ros/jazzy/setup.bash
source /ros2_ws/install/setup.bash

if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
  mkdir -p "${XDG_RUNTIME_DIR}"
  chmod 700 "${XDG_RUNTIME_DIR}"
fi

# exec はシグナル伝達に必須。この後に処理を足さないこと。
# SIGINT が controller_manager に届かないと on_deactivate が走らず、
# シリアルポートが開いたままトルクが入った状態でコンテナが消える。
exec "$@"
