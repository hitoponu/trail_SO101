FROM ros:jazzy-ros-base

ENV DEBIAN_FRONTEND=noninteractive

# ros-jazzy-ros2-control はメタパッケージとして入れる。
#   `ros2 control list_controllers` の実体は ros2controlcli にあり、
#   これを引いてくるのはメタパッケージだけ。hardware_interface
#   hardware_interface と joint_limits (enforce_command_limits) も入る。
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
      python3-pynput \
      python3-vcstool \
      python3-yaml \
      ros-jazzy-joint-state-topic-hardware-interface \
      ros-jazzy-joint-state-broadcaster \
      ros-jazzy-joint-state-publisher-gui \
      ros-jazzy-joint-trajectory-controller \
      ros-jazzy-parallel-gripper-controller \
      ros-jazzy-robot-state-publisher \
      ros-jazzy-ros2-control \
      ros-jazzy-rqt-joint-trajectory-controller \
      ros-jazzy-rviz2 \
      ros-jazzy-tf2-ros \
      ros-jazzy-tf2-tools \
      ros-jazzy-xacro \
    && rm -rf /var/lib/apt/lists/*

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

# Hardware communication, calibration and motor configuration all come from
# LeRobot. Do not add a direct Feetech SDK or feetech_ros2_driver dependency.
# Install it after colcon so a transient package-index failure does not discard
# the ROS workspace build layer. Ubuntu's packaging/numpy are dpkg-managed and
# cannot be upgraded by pip, so shadow only those two in /usr/local first.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --break-system-packages --ignore-installed --no-deps \
      "packaging==25.0" "numpy==2.2.6" \
    && pip install --timeout 120 --break-system-packages \
      "lerobot[feetech]==0.5.1"

# Build-time static smoke tests. Physical hardware and ROS runtime tests are
# intentionally deferred to the target Linux host.
RUN . /opt/ros/jazzy/setup.sh && . /ros2_ws/install/setup.sh \
    && ros2 pkg prefix joint_state_topic_hardware_interface > /dev/null \
    && D="$(ros2 pkg prefix so_arm101_description)/share/so_arm101_description" \
    && B="$(ros2 pkg prefix so101_bringup)/share/so101_bringup" \
    && xacro "$D/urdf/so_arm101.urdf.xacro" \
         ros2_control_hardware_type:=real \
         ros2_control_file:="$B/control/so101_follower.ros2_control.xacro" > /tmp/mock.urdf \
    && check_urdf /tmp/mock.urdf > /dev/null \
    && grep -q 'joint_state_topic_hardware_interface/JointStateTopicSystem' /tmp/mock.urdf \
    && ! grep -Eq 'feetech_ros2_driver|p_cofficient|name="offset"' /tmp/mock.urdf \
    && python3 -c "import lerobot; from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig; from so101_bringup import bridge_core, lerobot_backend" \
    && python3 -c "from so101_bringup import cartesian_jog, cartesian_math, keyboard_input, lerobot_bridge" \
    && python3 -c "import yaml,sys; d=yaml.safe_load(open('$B/config/ros2_controllers.yaml')); \
                   j=d['joint_trajectory_controller']['ros__parameters']['joints']; \
                   sys.exit(0 if len(j)==5 and 'gripper_joint' not in j else 1)"

COPY docker/so101_ros2/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ★ docker compose exec は ENTRYPOINT を通らないため、そのままでは setup.bash が
#   source されず `ros2` が PATH に無い ("executable file not found in $PATH")。
#   対話シェル (docker compose exec -it <svc> bash) 用に bashrc でも source しておく。
#   単発コマンドは /entrypoint.sh を前置すること:
#       docker compose exec so101-follower /entrypoint.sh ros2 topic list
RUN printf '%s\n' \
      'source /opt/ros/jazzy/setup.bash' \
      'source /ros2_ws/install/setup.bash' \
      >> /etc/bash.bashrc

ENTRYPOINT ["/entrypoint.sh"]
# 既定はbridgeのmock backend。素の `docker run` では実機に触れない。
CMD ["ros2", "launch", "so101_bringup", "follower.launch.py"]
