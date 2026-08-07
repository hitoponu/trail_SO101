#!/usr/bin/env bash
# ホストからマウントした ros2_ws の初期化。統合イメージ用。
#
#   cd docker/robot && make bootstrap
#   （実体は docker compose run --rm robot bash /bootstrap.sh）
#
# 上流の取得と colcon build をここに集約する。
# 成果物はホスト側の ros2_ws/build・install に残るので、イメージの
# 作り直しやコンテナの作り直しで消えない。
#
# ★ 旧 docker/so101_ros2/bootstrap.sh との違い
#   ビルド対象を全パッケージへ広げた。以前はアームのイメージに nav2 も
#   laser_geometry も realsense2_camera も入っていなかったので、
#   lekiwi_base_bringup / rplidar_bringup / realsense_bringup を除外していた。
#   統合イメージには全部入っているので除外理由が消えた。
set -eo pipefail

# ROS の setup.bash は未定義変数を参照するので set -u とは併用できない
# (AMENT_TRACE_SETUP_FILES: unbound variable になる)。
source /opt/ros/jazzy/setup.bash

cd /ros2_ws

# ── 上流の取得 ────────────────────────────────────────────────────────
# ros2_so_arm (アームの description) と sllidar_ros2 (LiDAR ドライバ)。
# どちらも so101_upstream.repos で SHA 固定。
# vcs import は既存ディレクトリを skip するので、足りないものがあるときだけ走らせる。
missing=()
for repo in ros2_so_arm sllidar_ros2; do
  [ -d "src/$repo" ] || missing+=("$repo")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "== 上流を取得します: ${missing[*]} =="
  vcs import src < so101_upstream.repos
else
  echo "== 上流は取得済み。スキップします =="
  echo "   (更新するには src/ros2_so_arm や src/sllidar_ros2 を消してから再実行)"
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
# ★ --packages-select で明示する。ワークスペース全体を build すると
#   src/ros2_so_arm/ に同梱されている so_arm100_moveit_config や so_arm_gz まで
#   対象になり、MoveIt と Gazebo が入っていないこのイメージでは失敗する。
colcon build --symlink-install \
  --packages-select so_arm_utils so_arm101_description sllidar_ros2 \
                    so101_bringup \
                    lekiwi_description lekiwi_base_bringup lekiwi_so101_bringup \
                    rplidar_bringup realsense_bringup

# ★ Dockerfile にあった静的スモークテストの移設先。
#   ワークスペースをマウントする方式ではビルド時に検査できないので、
#   ここで毎回走らせる。壊れたまま実機に持っていくのを防ぐのが目的。
echo
echo "== 静的検査 =="
source install/setup.bash

python3 -c "from so101_bringup import bridge_core, cartesian_jog, cartesian_math, \
    keyboard_input, lerobot_backend, lerobot_bridge, reach_solver, reach_to_point"
python3 -c "import lerobot; from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig"
# ★ ベース側。統合により numpy が dpkg 版から pip の 2.2.6 に変わったので、
#   import が通ることをここで毎回確かめる。
python3 -c "import scservo_sdk, serial, numpy"
python3 -c "from lekiwi_base_bringup import base_driver, kinematics, sts_bus"
python3 -c "from lekiwi_so101_bringup import release_all"
echo "  Python import: OK"

# ★ 統合イメージにだけ必要な検査。以前は「アームのイメージに nav2 が無い」
#   ことが原因で /navigate_to_pose を叩くと action type invalid になっていた。
#   1 コンテナ化の目的そのものなので、ここで実在を確かめる。
python3 -c "import nav2_msgs.action, slam_toolbox.srv"
ros2 pkg prefix nav2_bringup > /dev/null
ros2 pkg prefix slam_toolbox > /dev/null
ros2 pkg prefix realsense2_camera > /dev/null
ros2 pkg prefix sllidar_ros2 > /dev/null
echo "  ナビ・LiDAR・カメラのパッケージ: OK"

# アーム単体の URDF
D="$(ros2 pkg prefix so_arm101_description)/share/so_arm101_description"
B="$(ros2 pkg prefix so101_bringup)/share/so101_bringup"
xacro "$D/urdf/so_arm101.urdf.xacro" \
  ros2_control_hardware_type:=real \
  ros2_control_file:="$B/control/so101_follower.ros2_control.xacro" > /tmp/arm.urdf
check_urdf /tmp/arm.urdf > /dev/null
grep -q 'joint_state_topic_hardware_interface/JointStateTopicSystem' /tmp/arm.urdf
echo "  アーム単体 URDF: OK"

# ベース単体の URDF (lekiwi_base_bringup の nav.launch.py が使う)
L="$(ros2 pkg prefix lekiwi_description)/share/lekiwi_description"
xacro "$L/urdf/lekiwi_base.urdf.xacro" use_mesh:=false > /dev/null
echo "  ベース単体 URDF: OK"

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
need = {'arm_base_link', 'arm_gripper_frame_link', 'base_footprint', 'laser_link'}
if not need <= set(links):
    sys.exit(f'必要なリンクが無い: {sorted(need - set(links))}')
# ★ 手首カメラ: <name>_link を子とする joint が**ちょうど 1 個**であること。
#   realsense2_camera は <name>_link を子にする TF を出さない前提なので、
#   URDF 側が 1 個だけ親を与えるのが正しい。0 個なら孤立フレームになり
#   map -> 点群 が解けず、2 個なら tf2 が後着勝ちで非決定になる。
cam = [j for j in root.findall('joint')
       if j.find('child').get('link') == 'wrist_camera_link']
if 'wrist_camera_link' in links and len(cam) != 1:
    sys.exit(f'wrist_camera_link を子とする joint が {len(cam)} 個 (1 であること)')
PY
echo "  結合 URDF: OK"

# ★ launch ファイルが読み込めること。--show-args は generate_launch_description() を
#   実行して引数を列挙するだけで、ノードは 1 つも起動しない。
#   include 先のパッケージが見つからない・引数名を打ち間違えた、といった
#   「起動して初めて分かる」種類の壊れをここで拾う。
ros2 launch lekiwi_so101_bringup robot.launch.py --show-args > /dev/null
ros2 launch lekiwi_so101_bringup reach.launch.py --show-args > /dev/null
echo "  launch の読み込み: OK"

echo
echo "== 完了 =="
echo "以降は次で起動できます:"
echo "  docker compose up -d"
echo "  docker compose exec -it robot bash"
echo "  ros2 launch lekiwi_so101_bringup robot.launch.py backend:=lerobot robot_id:=my_follower"
echo
echo "設定や Python コードを編集したら launch を上げ直すだけで反映されます。"
echo "ファイルを追加した場合だけ、コンテナ内で colcon build してください:"
echo "  colcon build --symlink-install --packages-select so101_bringup"
