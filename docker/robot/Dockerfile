# LeKiwi ベース + RPLIDAR + SO-101 アーム + RealSense を 1 つに束ねたイメージ。
#
# 以前は 4 イメージ (lekiwi_base_ros2 / rplidar_ros2 / so101_ros2 / realsense_ros2)
# に分かれていた。分けた理由は「アームとベースで安全論理が逆で、compose の
# stop_signal はサービス単位にしか設定できないから」だったが、実際に踏んだ問題の
# 多くはコンテナ跨ぎであること自体に起因していた:
#
#   * ROS_DOMAIN_ID の食い違い (realsense 単体は既定 0、統合スタックは 7)
#   * nav2_msgs がベースのイメージにしか無く、アーム側から action を叩くと
#     "The passed action type is invalid"
#   * DDS discovery の遅れで `ros2 topic list` が不完全
#   * /robot_description の publisher を 1 つに保つための調整
#   * docker compose down が exec した launch に SIGINT を届けない
#     (★ これだけは統合しても消えない。launch を Ctrl+C する運用で回避する)
#
# 1 イメージ 1 コンテナにすればこれらは消える。停止方針が 1 つになる代わりに、
# 異常終了 (SIGKILL) からの復帰は専用コマンドで賄う:
#
#     ros2 run lekiwi_so101_bringup release_all
#
# ★ 既存の docker/{lekiwi_base_ros2,rplidar_ros2,so101_ros2,realsense_ros2} は
#   単体デバッグ用に残してある。通常の運用はこのイメージ 1 つで足りる。
FROM ros:jazzy-ros-base

ENV DEBIAN_FRONTEND=noninteractive

# ── Intel librealsense2 の apt リポジトリ ─────────────────────────────
# ros-jazzy-realsense2-camera の実行時依存 (librealsense2.so) の供給元。
# ★ このリポジトリは amd64 / arm64 の両方を持つ (dists/noble/Release で確認済み)
#   ので、実機の Linux PC でも Mac の検証でも同じ手順で通る。
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      gnupg \
      lsb-release \
    && mkdir -p /etc/apt/keyrings \
    && curl -sSf https://librealsense.realsenseai.com/Debian/librealsenseai.asc \
         | gpg --dearmor \
         | tee /etc/apt/keyrings/librealsenseai.gpg > /dev/null \
    && echo "deb [signed-by=/etc/apt/keyrings/librealsenseai.gpg] \
         https://librealsense.realsenseai.com/Debian/apt-repo $(lsb_release -cs) main" \
         > /etc/apt/sources.list.d/librealsense.list \
    && rm -rf /var/lib/apt/lists/*

# ── ビルドツールと共通の ROS パッケージ ───────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      git \
      liburdfdom-tools \
      python3-colcon-common-extensions \
      python3-numpy \
      python3-pip \
      python3-pynput \
      python3-vcstool \
      python3-yaml \
      ros-jazzy-robot-state-publisher \
      ros-jazzy-rviz2 \
      ros-jazzy-tf2-ros \
      ros-jazzy-tf2-tools \
      ros-jazzy-xacro \
    && rm -rf /var/lib/apt/lists/*

# ── アーム (旧 so101_ros2) ────────────────────────────────────────────
# ros-jazzy-ros2-control はメタパッケージとして入れる。
#   `ros2 control list_controllers` の実体は ros2controlcli にあり、
#   これを引いてくるのはメタパッケージだけ。hardware_interface と
#   joint_limits (enforce_command_limits) も入る。
#
# コントローラは ros-jazzy-ros2-controllers をまとめて入れず個別に指定する。
#   まとめると admittance_controller -> kinematics_interface -> KDL まで
#   引きずり込むが、いずれも使わない。
#
# ros-jazzy-parallel-gripper-controller が正しい apt 名。
#   プラグイン名前空間は parallel_gripper_action_controller で、パッケージ名と
#   一致しない (ここが引っかかりやすい)。
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-jazzy-control-msgs \
      ros-jazzy-joint-state-topic-hardware-interface \
      ros-jazzy-joint-state-broadcaster \
      ros-jazzy-joint-state-publisher \
      ros-jazzy-joint-state-publisher-gui \
      ros-jazzy-joint-trajectory-controller \
      ros-jazzy-parallel-gripper-controller \
      ros-jazzy-nav-msgs \
      ros-jazzy-ros2-control \
      ros-jazzy-rqt-joint-trajectory-controller \
      ros-jazzy-tf2-geometry-msgs \
      ros-jazzy-visualization-msgs \
    && rm -rf /var/lib/apt/lists/*

# ── ベースとナビゲーション (旧 lekiwi_base_ros2) ──────────────────────
# ★ nav2 が同じイメージに入るのが統合の主な利点。以前はアーム側から
#   /navigate_to_pose を叩くと nav2_msgs が無く action type invalid になった。
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-jazzy-navigation2 \
      ros-jazzy-nav2-bringup \
      ros-jazzy-slam-toolbox \
      ros-jazzy-twist-mux \
      ros-jazzy-teleop-twist-keyboard \
    && rm -rf /var/lib/apt/lists/*

# ── LiDAR (旧 rplidar_ros2) ───────────────────────────────────────────
# sllidar_ros2 本体は git clone しない。ros2_ws/so101_upstream.repos へ
# SHA 固定で移したので、bootstrap.sh の vcs import が取得する。
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-jazzy-laser-geometry \
    && rm -rf /var/lib/apt/lists/*

# ── RealSense (旧 realsense_ros2) ─────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
      librealsense2-utils \
      librealsense2-dev \
      ros-jazzy-realsense2-camera \
      ros-jazzy-realsense2-description \
    && rm -rf /var/lib/apt/lists/*

# ── 上流リポジトリ (ros2_so_arm / sllidar_ros2) ───────────────────────
# ★ /ros2_ws ではなく /opt/upstream に置く。
#   compose.yaml が ../../ros2_ws:/ros2_ws を bind mount するので、
#   **Dockerfile が /ros2_ws に書いたものは実行時に完全に隠れる**（実測確認済み）。
#   bootstrap.sh がここから ros2_ws/src/ へコピーする。
#
# これをイメージ側でやる理由:
#   * bootstrap がオフラインで完結する (実機 PC の回線に依存しない)
#   * SHA のドリフトが原理的に起きない。以前は bootstrap がディレクトリの
#     有無しか見ておらず、so101_upstream.repos の SHA を上げても既存の
#     チェックアウトを黙って使い続けていた
#   * 更新したいときは so101_upstream.repos を書き換えて make build
# ★ .git を消さないこと。`git -C src/ros2_so_arm rev-parse HEAD` が
#   「いま何が入っているか」を確かめる唯一の手段になる。
COPY ros2_ws/so101_upstream.repos /opt/so101_upstream.repos
RUN mkdir -p /opt/upstream \
    && vcs import /opt/upstream < /opt/so101_upstream.repos \
    && vcs export --exact /opt/upstream > /opt/upstream/.resolved.repos

WORKDIR /ros2_ws

# ── Python の実行依存 ─────────────────────────────────────────────────
# アームのハードウェア通信・較正・モータ設定はすべて LeRobot 経由。
# Feetech SDK や feetech_ros2_driver に直接依存を足さないこと。
#
# ★ ベースのドライバ (lekiwi_base_bringup/sts_bus.py) だけは例外で
#   scservo_sdk を直叩きする。lerobot[feetech] が引く feetech-servo-sdk が
#   その import 名を提供するので、追加の pip install は要らない。
#   バージョン制約は lerobot 0.5.1 が feetech-servo-sdk<2.0.0,>=1.0.0、
#   sts_bus.py の setPacketTimeout モンキーパッチは 1.0.0 系を前提としている。
#   両者を満たすよう 1.0.0 に固定する。
#
# ★ Ubuntu の packaging / numpy は dpkg 管理で pip から upgrade できないので、
#   この 2 つだけ先に /usr/local へ shadow する。
#   統合により lekiwi_base_bringup と rplidar_bringup もこの numpy 2.2.6 で
#   動くことになる (以前は dpkg の 1.26 系だった)。削除済み API
#   (np.float_ / np.NaN 等) の使用が無いことは確認済み。
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --break-system-packages --ignore-installed --no-deps \
      "packaging==25.0" "numpy==2.2.6" \
    && pip install --timeout 120 --break-system-packages \
      "lerobot[feetech]==0.5.1" \
    && pip install --timeout 120 --break-system-packages \
      "feetech-servo-sdk==1.0.0" \
    && pip install --timeout 120 --break-system-packages \
      "setuptools<80"

# ソースと colcon の build/install/log は compose.yaml でホストから
# /ros2_ws にマウントする。取得・パッチ適用・ビルドは bootstrap.sh に
# 一本化し、ここでは ROS と Python の実行依存だけを用意する。
#
# ★ この方式なので、パッケージを増やしても Dockerfile に COPY を足す必要はない。
#   lekiwi_description も so_arm101_description もマウントされた ros2_ws/src に
#   揃っており、xacro の $(find) は両方を解決できる。
COPY docker/robot/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ★ docker compose exec は ENTRYPOINT を通らないため、そのままでは setup.bash が
#   source されず `ros2` が PATH に無い ("executable file not found in $PATH")。
#   対話シェル (docker compose exec -it robot bash) 用に bashrc でも source しておく。
#   単発コマンドは /entrypoint.sh を前置すること:
#       docker compose exec robot /entrypoint.sh ros2 topic list
RUN printf '%s\n' \
      'source /opt/ros/jazzy/setup.bash' \
      'if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi' \
      >> /etc/bash.bashrc

ENTRYPOINT ["/entrypoint.sh"]
# ★ 既定は bash。コンテナは待機するだけで、launch は人が手で叩く。
#   compose.yaml の command: ["bash"] と同じだが、素の `docker run` でも
#   いきなり実機を動かさないという意味でここでも bash にしておく。
CMD ["bash"]
