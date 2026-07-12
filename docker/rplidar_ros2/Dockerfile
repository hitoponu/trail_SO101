FROM ros:jazzy-ros-base

ARG SLLIDAR_ROS2_REF=main
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      git \
      python3-colcon-common-extensions \
      ros-jazzy-laser-geometry \
      ros-jazzy-rviz2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ros2_ws
RUN git clone --branch "${SLLIDAR_ROS2_REF}" --depth 1 \
      https://github.com/Slamtec/sllidar_ros2.git src/sllidar_ros2

COPY ros2_ws/src/rplidar_bringup src/rplidar_bringup
RUN . /opt/ros/jazzy/setup.sh && colcon build --symlink-install

COPY docker/rplidar_ros2/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "rplidar_bringup", "a1_points.launch.py"]
