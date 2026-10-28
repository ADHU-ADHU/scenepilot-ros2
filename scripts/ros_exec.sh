#!/usr/bin/env bash
# Run a command inside the coordinator container with ROS and its workspace sourced.
set -euo pipefail
if [ "$#" -eq 0 ]; then
  echo 'Usage: bash scripts/ros_exec.sh COMMAND [ARG ...]' >&2
  exit 2
fi
exec docker compose exec system bash -c \
  'source /opt/ros/jazzy/setup.bash && source /ws/install/setup.bash && exec "$@"' \
  scenepilot-ros "$@"
