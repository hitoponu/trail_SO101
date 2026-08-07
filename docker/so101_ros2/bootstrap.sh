#!/usr/bin/env bash
# ホストからマウントした ros2_ws の初期化。
#
#   docker compose run --rm so101-follower bash /bootstrap.sh
#
# 上流の取得と colcon build をここに集約する。
# 成果物はホスト側の ros2_ws/build・install に残るので、イメージの
# 作り直しやコンテナの作り直しで消えない。
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

# --symlink-install の成果物には src を指すシンボリックリンクが残る。
# データファイルを消したりブランチを切り替えたりすると、リンク先が消えて
# 「壊れたリンク」になり、setuptools が存在しないファイルをコピーしようとして
#   error: can't copy '...': doesn't exist or not a regular file
# で失敗する。該当パッケージの生成物だけを消して作り直す。
#
# ★ ブランチ切り替えで頻繁に起きる (例: feat/env-camera にしか無い
#   env_camera.launch.py のリンクが build に残ったまま別ブランチへ戻る)。
#   パッケージ名を決め打ちせず、壊れたリンクを持つものを全部拾う。
for pkg_build in build/*/; do
  pkg="$(basename "$pkg_build")"
  if find "$pkg_build" -xtype l -print -quit 2>/dev/null | grep -q .; then
    echo
    echo "== $pkg に壊れたシンボリックリンクがあるので作り直します =="
    find "$pkg_build" -xtype l -printf '   %p -> %l\n' 2>/dev/null | head -5
    rm -rf "build/$pkg" "install/$pkg"
  fi
done

echo
echo "== ビルドします =="
# rplidar_bringup / realsense_bringup は依存 (laser_geometry 等) が
# このイメージに入っていないので対象外にする。
#
# lekiwi_description と lekiwi_so101_bringup は、LeKiwi ベースにアームを
# 載せた結合構成 (docker/lekiwi_so101_bringup) のためにビルドする。
# lekiwi_base_bringup は対象外 — nav2 / slam_toolbox がこのイメージに
# 入っておらず、ベース側のノードは別コンテナで動かすため。
colcon build --symlink-install \
  --packages-select so_arm_utils so_arm101_description so101_bringup \
                    lekiwi_description lekiwi_so101_bringup

# ★ Dockerfile にあった静的スモークテストの移設先。
#   ワークスペースをマウントする方式ではビルド時に検査できないので、
#   ここで毎回走らせる。壊れたまま実機に持っていくのを防ぐのが目的。
echo
echo "== 静的検査 =="
source install/setup.bash

python3 -c "from so101_bringup import bridge_core, cartesian_jog, cartesian_math, \
    keyboard_input, lerobot_backend, lerobot_bridge, reach_solver, reach_to_point"
python3 -c "import lerobot; from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig"
echo "  Python import: OK"

# アーム単体の URDF
D="$(ros2 pkg prefix so_arm101_description)/share/so_arm101_description"
B="$(ros2 pkg prefix so101_bringup)/share/so101_bringup"
xacro "$D/urdf/so_arm101.urdf.xacro" \
  ros2_control_hardware_type:=real \
  ros2_control_file:="$B/control/so101_follower.ros2_control.xacro" > /tmp/arm.urdf
check_urdf /tmp/arm.urdf > /dev/null
grep -q 'joint_state_topic_hardware_interface/JointStateTopicSystem' /tmp/arm.urdf
echo "  アーム単体 URDF: OK"

# 結合 URDF。ルートが base_footprint 1 つで、リンク名が衝突せず、
# controllers 設定の関節名が実在することを確認する。
C="$(ros2 pkg prefix lekiwi_so101_bringup)/share/lekiwi_so101_bringup"
xacro "$C/urdf/lekiwi_so101.urdf.xacro" > /tmp/combined.urdf
check_urdf /tmp/combined.urdf | grep -q '^root Link: base_footprint'
python3 - "$C/config/ros2_controllers.yaml" <<'PY'
import sys, yaml, xml.etree.ElementTree as ET
root = ET.parse('/tmp/combined.urdf').getroot()
links = [e.get('name') for e in root.findall('link')]
dup = sorted({n for n in links if links.count(n) > 1})
if dup:
    sys.exit(f'リンク名が重複: {dup}')
joints = {e.get('name') for e in root.findall('joint')}
cfg = yaml.safe_load(open(sys.argv[1]))
want = set(cfg['joint_trajectory_controller']['ros__parameters']['joints']) \
       | {cfg['gripper_controller']['ros__parameters']['joint']}
if want - joints:
    sys.exit(f'controllers が存在しない関節を参照: {sorted(want - joints)}')
need = {'arm_base_link', 'arm_gripper_frame_link', 'base_footprint'}
if not need <= set(links):
    sys.exit(f'必要なリンクが無い: {sorted(need - set(links))}')
PY
echo "  結合 URDF: OK"

echo
echo "== 完了 =="
echo "以降は次で起動できます:"
echo "  docker compose up -d"
echo
echo "設定やPythonコードを編集したら再起動するだけで反映されます。"
echo "ファイルを追加した場合だけ、コンテナ内で colcon build してください:"
echo "  docker compose exec so101-follower /entrypoint.sh \\"
echo "    bash -c 'cd /ros2_ws && colcon build --symlink-install --packages-select so101_bringup'"
