FROM ros:jazzy-ros-base

ENV DEBIAN_FRONTEND=noninteractive

# Intel librealsense2 apt repository
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      gnupg \
      lsb-release \
    && mkdir -p /etc/apt/keyrings \
    && curl -sSf https://librealsense.intel.com/Debian/librealsense.pgp \
         | tee /etc/apt/keyrings/librealsense.pgp > /dev/null \
    && echo "deb [signed-by=/etc/apt/keyrings/librealsense.pgp] \
         https://librealsense.intel.com/Debian/apt-repo $(lsb_release -cs) main" \
         | tee /etc/apt/sources.list.d/librealsense.list \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      python3-colcon-common-extensions \
      librealsense2-utils \
      librealsense2-dev \
      ros-jazzy-realsense2-camera \
      ros-jazzy-realsense2-description \
      ros-jazzy-rviz2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ros2_ws
COPY ros2_ws/src/realsense_bringup src/realsense_bringup
RUN . /opt/ros/jazzy/setup.sh && colcon build --symlink-install

COPY docker/realsense_ros2/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "realsense_bringup", "d435i.launch.py"]
