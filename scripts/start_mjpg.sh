#!/usr/bin/env bash
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