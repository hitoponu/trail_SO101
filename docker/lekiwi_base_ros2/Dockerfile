FROM ros:jazzy-ros-base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      python3-colcon-common-extensions \
      python3-numpy \
      python3-pip \
      ros-jazzy-joint-state-publisher \
      ros-jazzy-robot-state-publisher \
      ros-jazzy-rviz2 \
      ros-jazzy-teleop-twist-keyboard \
      ros-jazzy-tf2-ros \
      ros-jazzy-tf2-tools \
      ros-jazzy-xacro \
    && rm -rf /var/lib/apt/lists/*

# ナビゲーション。実機なしの検証 (fake_scan + dry_run) でも実機でも同じものを使う。
# ★ 実機を動かすだけなら不要な追加。イメージが約 500MB 増えるが、
#   ドライバと Nav2 でイメージを分けると TF/トピックの疎通を
#   コンテナ跨ぎで検証することになり、切り分けが難しくなるため同居させる。
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-jazzy-navigation2 \
      ros-jazzy-nav2-bringup \
      ros-jazzy-slam-toolbox \
      ros-jazzy-twist-mux \
    && rm -rf /var/lib/apt/lists/*

# Ubuntu 24.04 は PEP 668 で system python を保護しているため、素の pip install は
# externally-managed-environment で失敗する。このイメージは使い捨ての単一用途で、
# feetech-servo-sdk には競合する dpkg パッケージも存在しないため上書きする。
#
# NOTE: feetech-servo-sdk には rosdep キーが無いので package.xml には書けない。
#       このイメージが唯一の導入経路であり、rosdep install だけでは揃わない。
# バージョンを固定する: PyPI 版は非公式ミラーで、sts_bus.py が当てている
# setPacketTimeout のモンキーパッチは実装バージョンに依存する。
RUN pip install --no-cache-dir --break-system-packages "feetech-servo-sdk==1.0.0"

WORKDIR /ros2_ws
COPY ros2_ws/src/lekiwi_description  src/lekiwi_description
COPY ros2_ws/src/lekiwi_base_bringup src/lekiwi_base_bringup
RUN . /opt/ros/jazzy/setup.sh && colcon build --symlink-install

# 依存の壊れをビルド時に検出する (12V 通電後に気付くのを避ける)
RUN . /opt/ros/jazzy/setup.sh && . /ros2_ws/install/setup.sh \
    && python3 -c "import scservo_sdk, serial, numpy" \
    && python3 -c "from lekiwi_base_bringup import base_driver, kinematics, sts_bus" \
    && xacro src/lekiwi_description/urdf/lekiwi_base.urdf.xacro > /dev/null

COPY docker/lekiwi_base_ros2/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "lekiwi_base_bringup", "base.launch.py"]
