#!/usr/bin/env bash
# 開発用オーバーレイ（compose.dev.yaml）の初期化。
#
#   docker compose -f compose.yaml -f compose.dev.yaml run --rm so101-follower \
#     bash /bootstrap.sh
#
# ホスト側の ros2_ws を使うので、上流の取得とビルドを一度だけホスト側へ行う。
# 2回目以降は不要（必要になるのは上流の SHA を変えたときくらい）。
set -eo pipefail

# ROS の setup.bash は未定義変数を参照するので set -u とは併用できない
# (AMENT_TRACE_SETUP_FILES: unbound variable になる)。
source /opt/ros/jazzy/setup.bash

cd /ros2_ws

if [ ! -d src/ros2_so_arm ]; then
  echo "== 上流 (ros2_so_arm) を取得します =="
  vcs import src < so101_upstream.repos
else
  echo "== 上流は取得済み。スキップします =="
  echo "   (更新するには src/ros2_so_arm を消してから再実行)"
fi

echo
echo "== ビルドします =="
# rplidar_bringup / realsense_bringup は依存 (laser_geometry 等) が
# このイメージに入っていないので対象外にする。
colcon build --symlink-install \
  --packages-select so_arm_utils so_arm101_description so101_bringup

echo
echo "== 完了 =="
echo "以降は次で起動できます:"
echo "  docker compose -f compose.yaml -f compose.dev.yaml up"
echo
echo "設定やPythonコードを編集したら再起動するだけで反映されます。"
echo "ファイルを追加した場合だけ、コンテナ内で colcon build してください:"
echo "  docker compose exec so101-follower /entrypoint.sh \\"
echo "    bash -c 'cd /ros2_ws && colcon build --symlink-install --packages-select so101_bringup'"
