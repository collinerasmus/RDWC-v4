set -e
echo "[1/6] Update APT & install tools..."
sudo apt-get update -y
sudo apt-get install -y python3-smbus i2c-tools jq curl
if ! dpkg -s mjpg-streamer >/dev/null 2>&1; then
  echo "[1/6a] mjpg-streamer not in distro, building..."
  sudo apt-get install -y git build-essential cmake libjpeg-dev
  cd /tmp
  git clone https://github.com/jacksonliam/mjpg-streamer.git
  cd mjpg-streamer/mjpg-streamer-experimental
  make
  sudo make install
  if [ ! -d /usr/local/www ]; then
    sudo mkdir -p /usr/local/www
    sudo cp -r www/* /usr/local/www/
  fi
else
  echo "[1/6b] Using distro mjpg-streamer."
  if [ -d /usr/lib/mjpg-streamer/www ] && [ ! -d /usr/local/www ]; then
    sudo ln -s /usr/lib/mjpg-streamer/www /usr/local/www
  fi
fi

echo "[2/6] Enable I2C and verify devices..."
sudo raspi-config nonint do_i2c 0 || true
sleep 1
i2cdetect -y 1 || true

echo "[3/6] Create camera start script..."
sudo tee /usr/local/bin/start_mjpg.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
set -e
DEV="${1:-/dev/video0}"
RES="${RES:-1280x720}"
FPS="${FPS:-15}"
exec mjpg_streamer -i "input_uvc.so -d $DEV -r $RES -f $FPS" -o "output_http.so -p 8081 -w /usr/local/www"
EOF
sudo chmod +x /usr/local/bin/start_mjpg.sh

echo "[4/6] Create/refresh systemd service for camera..."
sudo tee /etc/systemd/system/mjpg-streamer.service >/dev/null <<'EOF'
[Unit]
Description=MJPG-Streamer Service
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/start_mjpg.sh
Restart=always
RestartSec=3
User=www-data
Group=www-data
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
EOF

echo "[5/6] Reload/enable/start services..."
sudo systemctl daemon-reload
sudo systemctl enable mjpg-streamer.service
sudo systemctl restart mjpg-streamer.service

if systemctl list-units --type=service | grep -q 'rdwc.service'; then
  echo "[5a/6] Restarting rdwc.service..."
  sudo systemctl restart rdwc.service
fi

echo "[6/6] Quick sensor sanity read via API..."
sleep 2
curl -s -X POST http://127.0.0.1:8080/read_now | jq .
echo "Camera: http://192.168.88.49:8081/?action=stream"
echo "Status: http://192.168.88.49:8080/status"