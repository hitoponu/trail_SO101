#!/usr/bin/env bash
set -e

source /opt/ros/jazzy/setup.bash

# ホストからマウントした ros2_ws は、初回だけ install 空間が存在しない。
# その場合に落とさず初期化方法を案内する。
if [ -f /ros2_ws/install/setup.bash ]; then
  source /ros2_ws/install/setup.bash
else
  echo "警告: /ros2_ws/install/setup.bash がありません。" >&2
  echo "      先にワークスペースを初期化してください:" >&2
  echo "        cd docker/robot && make bootstrap" >&2
fi

if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
  mkdir -p "${XDG_RUNTIME_DIR}"
  chmod 700 "${XDG_RUNTIME_DIR}"
fi

# exec はシグナル伝達に必須。この後に処理を足さないこと。
#
# ★ SIGINT が launch に届かないと停止処理が走らない。届いた場合に何が起きるかは
#   docker/robot/README.md の「異常終了したとき何が起きるか」を参照:
#     アーム: LeRobot が disconnect() でトルクを切る -> 支えが無ければ落ちる
#     ベース: safe_stop() が速度ゼロ + トルク OFF
#   SIGKILL ではどちらも走らない (アームは凍り、ホイールは回り続ける)。
exec "$@"
