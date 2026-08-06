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
      ros-jazzy-moveit \
      ros-jazzy-moveit-setup-assistant \
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

# ソースと colcon の build/install/log は compose.yaml でホストから
# /ros2_ws にマウントする。取得・パッチ適用・ビルドは bootstrap.sh に
# 一本化し、ここでは ROS と Python の実行依存だけを用意する。

# Hardware communication, calibration and motor configuration all come from
# LeRobot. Do not add a direct Feetech SDK or feetech_ros2_driver dependency.
# Ubuntu's packaging/numpy are dpkg-managed and cannot be upgraded by pip, so
# shadow only those two in /usr/local first.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --break-system-packages --ignore-installed --no-deps \
      "packaging==25.0" "numpy==2.2.6" \
    && pip install --timeout 120 --break-system-packages \
      "lerobot[feetech]==0.5.1" \
    && pip install --timeout 120 --break-system-packages \
      "setuptools<80"

COPY docker/so101_ros2/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ★ docker compose exec は ENTRYPOINT を通らないため、そのままでは setup.bash が
#   source されず `ros2` が PATH に無い ("executable file not found in $PATH")。
#   対話シェル (docker compose exec -it <svc> bash) 用に bashrc でも source しておく。
#   単発コマンドは /entrypoint.sh を前置すること:
#       docker compose exec so101-follower /entrypoint.sh ros2 topic list
RUN printf '%s\n' \
      'source /opt/ros/jazzy/setup.bash' \
      'if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi' \
      >> /etc/bash.bashrc

ENTRYPOINT ["/entrypoint.sh"]
# 既定はbridgeのmock backend。素の `docker run` では実機に触れない。
CMD ["ros2", "launch", "so101_bringup", "follower.launch.py"]
