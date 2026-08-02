FROM ros:jazzy-ros-base

ENV DEBIAN_FRONTEND=noninteractive

# ros-jazzy-ros2-control はメタパッケージとして入れる。
#   `ros2 control list_controllers` の実体は ros2controlcli にあり、
#   これを引いてくるのはメタパッケージだけ。hardware_interface
#   (mock_components/GenericSystem) と joint_limits (enforce_command_limits) も入る。
#
# コントローラは ros-jazzy-ros2-controllers をまとめて入れず個別に指定する。
#   まとめると admittance_controller -> kinematics_interface -> KDL まで
#   引きずり込むが、いずれも使わない。
#
# ros-jazzy-parallel-gripper-controller が正しい apt 名。
#   プラグイン名前空間は parallel_gripper_action_controller で、パッケージ名と
#   一致しない (ここが引っかかりやすい)。
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      git \
      liburdfdom-tools \
      python3-colcon-common-extensions \
      python3-numpy \
      python3-pip \
      python3-vcstool \
      python3-yaml \
      ros-jazzy-feetech-ros2-driver \
      ros-jazzy-joint-state-broadcaster \
      ros-jazzy-joint-state-publisher-gui \
      ros-jazzy-joint-trajectory-controller \
      ros-jazzy-parallel-gripper-controller \
      ros-jazzy-position-controllers \
      ros-jazzy-robot-state-publisher \
      ros-jazzy-ros2-control \
      ros-jazzy-rqt-joint-trajectory-controller \
      ros-jazzy-rviz2 \
      ros-jazzy-tf2-ros \
      ros-jazzy-tf2-tools \
      ros-jazzy-xacro \
    && rm -rf /var/lib/apt/lists/*

# Ubuntu 24.04 は PEP 668 で system python を保護しているため、素の pip install は
# externally-managed-environment で失敗する。このイメージは使い捨ての単一用途で、
# feetech-servo-sdk には競合する dpkg パッケージも存在しないため上書きする。
#
# NOTE: feetech-servo-sdk には rosdep キーが無いので package.xml には書けない。
#       このイメージが唯一の導入経路であり、rosdep install だけでは揃わない。
# 使うのは so101_probe (実機のゼロ点実測) だけ。ros2_control 経路では使わない。
RUN pip install --no-cache-dir --break-system-packages "feetech-servo-sdk==1.0.0"

WORKDIR /ros2_ws

# 上流 (ros2_so_arm) はコミット SHA 固定で取り込む。
# git にコミットしない理由は ros2_ws/so101_upstream.repos のコメント参照
# (メッシュが SO101/assets と完全に同一で、二重に履歴へ入れることになる)。
COPY ros2_ws/so101_upstream.repos /tmp/so101_upstream.repos
RUN mkdir -p src && vcs import src < /tmp/so101_upstream.repos

COPY ros2_ws/src/so101_bringup src/so101_bringup

# so_arm100_* は 5-DoF の別機種、so_arm_gz は gz_ros2_control が必要なので外す。
#
# so_arm_utils は上流 launch 専用でこちらでは使わないが、**ビルドは必要**。
#   so_arm101_description が package.xml で exec_depend しており、colcon は
#   同一ワークスペース内の exec_depend について環境設定ファイル
#   (install/so_arm_utils/share/so_arm_utils/package.sh) の存在を要求する。
#   外すと so_arm101_description のビルドが即座に失敗する。
#   依存ゼロの小さな ament_cmake パッケージなのでコストはほぼゼロ。
#
# so_arm101_description は nav2_common にも exec_depend しているが、そちらは
# ワークスペース外なので colcon は underlay にあると仮定して検査しない。
# 上流 launch のための依存であり、こちらは自前の launch を使うので不要。
RUN . /opt/ros/jazzy/setup.sh \
    && colcon build --symlink-install \
         --packages-select so_arm_utils so_arm101_description so101_bringup

# ビルド時スモークテスト。
# 実機に通電してから壊れに気付くのを避けるため、ここで落とす。
RUN . /opt/ros/jazzy/setup.sh && . /ros2_ws/install/setup.sh \
    && ros2 pkg prefix feetech_ros2_driver > /dev/null \
    && D="$(ros2 pkg prefix so_arm101_description)/share/so_arm101_description" \
    && B="$(ros2 pkg prefix so101_bringup)/share/so101_bringup" \
    && xacro "$D/urdf/so_arm101.urdf.xacro" \
         ros2_control_hardware_type:=mock_components \
         ros2_control_file:="$B/control/so101_follower.ros2_control.xacro" > /tmp/mock.urdf \
    && check_urdf /tmp/mock.urdf > /dev/null \
    && grep -q 'mock_components/GenericSystem' /tmp/mock.urdf \
    && xacro "$D/urdf/so_arm101.urdf.xacro" \
         ros2_control_hardware_type:=real usb_port:=/dev/null \
         ros2_control_file:="$B/control/so101_follower.ros2_control.xacro" > /tmp/real.urdf \
    && check_urdf /tmp/real.urdf > /dev/null \
    && grep -q 'feetech_ros2_driver/FeetechHardwareInterface' /tmp/real.urdf \
    && grep -q 'joint_config_file' /tmp/real.urdf \
    && ! grep -q 'p_cofficient' /tmp/real.urdf \
    && ! grep -q 'name="offset"' /tmp/real.urdf \
    && python3 -c "import scservo_sdk, yaml" \
    && python3 -c "from so101_bringup import lerobot_calib, sts_probe" \
    && python3 -c "import yaml,sys; d=yaml.safe_load(open('$B/config/so101_joints.yaml')); \
                   ids=sorted(v['id'] for v in d['joints'].values()); \
                   sys.exit(0 if ids==[1,2,3,4,5,6] else 1)"

COPY docker/so101_ros2/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
# 既定は mock_components。素の `docker run` では実機に触れない。
CMD ["ros2", "launch", "so101_bringup", "follower.launch.py"]
