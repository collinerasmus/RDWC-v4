param([string]$PiHost="192.168.88.49",[string]$PiUser="pi",[int]$Port=22)
function SSH($c){ ssh -p $Port "$PiUser@$PiHost" $c }
Write-Host "Installing mjpg-streamer and creating robust service..."
SSH @"
set -e
sudo apt-get update -y
sudo apt-get install -y mjpg-streamer
# Wrapper that auto-detects paths
sudo tee /usr/local/bin/start_mjpg.sh >/dev/null <<'SH'
#!/usr/bin/env bash
set -e
BIN=$(command -v mjpg_streamer)
# Common plugin locations
for P in /usr/lib/mjpg-streamer /usr/lib/arm-linux-gnueabihf/mjpg-streamer /usr/lib/mjpg-streamer-experimental; do
  [ -d "\$P" ] && PLUG=\$P
done
if [ -z "\$PLUG" ]; then echo "mjpg-streamer plugins not found"; exit 1; fi
# Prefer video0; fall back to any /dev/video*
DEV=/dev/video0; [ -e "\$DEV" ] || DEV=\$(ls /dev/video* | head -n1)
exec "\$BIN" -i "input_uvc.so -d \$DEV -n -f 15 -r 1280x720" -o "output_http.so -p 8081 -w \$PLUG/www"
SH
sudo chmod +x /usr/local/bin/start_mjpg.sh

sudo tee /etc/systemd/system/mjpg-streamer.service >/dev/null <<'UNIT'
[Unit]
Description=USB camera mjpg-streamer
After=network.target

[Service]
ExecStart=/usr/local/bin/start_mjpg.sh
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable mjpg-streamer.service
sudo systemctl restart mjpg-streamer.service
"@
Write-Host "Camera service started at http://$PiHost:8081/?action=stream"