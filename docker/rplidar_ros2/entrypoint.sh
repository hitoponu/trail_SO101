#!/usr/bin/env bash
set -e

source /opt/ros/jazzy/setup.bash
source /ros2_ws/install/setup.bash

if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
  mkdir -p "${XDG_RUNTIME_DIR}"
  chmod 700 "${XDG_RUNTIME_DIR}"
fi

exec "$@"
