#!/usr/bin/env bash
set -e

source /opt/ros/jazzy/setup.bash

# ホストからマウントした ros2_ws は、初回だけ install 空間が存在しない。
# その場合に落とさず初期化方法を案内する。
if [ -f /ros2_ws/install/setup.bash ]; then
  source /ros2_ws/install/setup.bash
else
  echo "警告: /ros2_ws/install/setup.bash がありません。" >&2
  echo "      先にホストマウント式ワークスペースを初期化してください:" >&2
  echo "        docker/so101_ros2       : docker compose run --rm so101-follower bash /bootstrap.sh" >&2
  echo "        docker/lekiwi_so101_bringup : make bootstrap" >&2
fi

if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
  mkdir -p "${XDG_RUNTIME_DIR}"
  chmod 700 "${XDG_RUNTIME_DIR}"
fi

# exec はシグナル伝達に必須。この後に処理を足さないこと。
# SIGINT must reach the bridge so LeRobot can disable torque and close serial.
exec "$@"
