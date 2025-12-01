#!/usr/bin/env bash
# DEPRECATED: This script is no longer used.
# The RDWC application now uses built-in OpenCV camera handling via /camera/* endpoints.
# Using mjpg_streamer alongside the built-in camera causes device conflicts.
# 
# If you need to run mjpg_streamer separately, make sure to:
# 1. Stop the rdwc.service first
# 2. Or configure the app to not use the camera (no built-in camera init)
#
# Recommended: Use only the built-in /camera/stream endpoint on port 8080

echo "WARNING: mjpg_streamer is deprecated. Use /camera/stream endpoint instead."
echo "The RDWC app now handles camera via OpenCV on port 8080."
exit 1

# Original script below (disabled):
: <<'DISABLED'
set -euo pipefail
RES="${RES:-1280x720}"
FPS="${FPS:-15}"
PORT="${PORT:-8081}"
WWW="${WWW:-/usr/local/www}"

CAM="$(bash /usr/local/bin/mjpg_probe.sh || true)"
if [[ "$CAM" == "NO_CAMERA" || -z "$CAM" ]]; then
  echo "No camera device found"; exit 1
fi

# Ensure web root for output_http.so
[ -d "$WWW" ] || mkdir -p "$WWW"

exec mjpg_streamer \
  -i "input_uvc.so -d ${CAM} -r ${RES} -f ${FPS}" \
  -o "output_http.so -p ${PORT} -w ${WWW}"
DISABLED