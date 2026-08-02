#!/usr/bin/env bash
set -e

source /opt/ros/jazzy/setup.bash

# 開発用オーバーレイ (compose.dev.yaml) でホストの ros2_ws をマウントすると、
# 最初は install 空間が存在しない。その場合に落とさず案内を出す。
if [ -f /ros2_ws/install/setup.bash ]; then
  source /ros2_ws/install/setup.bash
else
  echo "警告: /ros2_ws/install/setup.bash がありません。" >&2
  echo "      開発用オーバーレイを使っている場合は、先に初期化してください:" >&2
  echo "        docker compose -f compose.yaml -f compose.dev.yaml run --rm \\" >&2
  echo "          so101-follower bash /bootstrap.sh" >&2
fi

if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
  mkdir -p "${XDG_RUNTIME_DIR}"
  chmod 700 "${XDG_RUNTIME_DIR}"
fi

# exec はシグナル伝達に必須。この後に処理を足さないこと。
# SIGINT が controller_manager に届かないと on_deactivate が走らず、
# シリアルポートが開いたままトルクが入った状態でコンテナが消える。
exec "$@"
