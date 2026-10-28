#!/bin/bash
set -u
fail=0
if command -v docker >/dev/null; then
  docker version || fail=1
  docker compose version || fail=1
else
  echo 'BLOCKED: Docker CLI is unavailable.'
  fail=1
fi
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv || fail=1
else
  echo 'BLOCKED: NVIDIA driver utilities unavailable.'
  fail=1
fi
df -h .
for device in "${FRONT_DEVICE:-/dev/video0}" "${REAR_DEVICE:-/dev/video2}"; do
  if [ -e "$device" ]; then ls -l "$device"; else echo "Optional camera missing: $device (use external topics or bags)"; fi
done
exit "$fail"
