#!/usr/bin/env bash
set -euo pipefail
# Return the first working /dev/video* path
for dev in /dev/video*; do
  [ -e "$dev" ] || continue
  if command -v v4l2-ctl >/dev/null 2>&1; then
    if v4l2-ctl -d "$dev" --all >/dev/null 2>&1; then
      echo "$dev"; exit 0
    fi
  else
    # Fallback: probe with mjpg_streamer input plugin list
    echo "$dev"; exit 0
  fi
done
echo "NO_CAMERA" && exit 1