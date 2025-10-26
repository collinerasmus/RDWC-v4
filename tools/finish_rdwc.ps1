# ====================== tools/finish_rdwc.ps1 ======================
param(
  [string]$PiHost = "192.168.88.49",
  [string]$PiUser = "pi",
  [string]$Repo = "https://github.com/collinerasmus/RDWC-v4.git",
  [int]$Port = 22
)

$ErrorActionPreference = "Stop"
function SSH($cmd){ ssh -p $Port "${PiUser}@${PiHost}" $cmd }
function SCP($src,$dst){ scp -P $Port $src "${PiUser}@${PiHost}:${dst}" }

Write-Host "=== RDWC-v4: finalize & verify ==="

# 0) Ensure we're in repo root and commit any local changes (sensor fix/UI/diag)
if (-not (Test-Path ".\.git")) { git init | Out-Null }
git add -A
git commit -m "chore: finalize sensor I2C fix, diagnostics, webcam, pump circulation" --allow-empty
git branch -M main
git remote remove origin 2>$null
git remote add origin $Repo 2>$null
git push -u origin main

# 1) Install camera service (mjpg-streamer) on the Pi (idempotent)
Write-Host "- Installing/starting mjpg-streamer camera..."
SSH "set -e; sudo apt-get update -y; sudo apt-get install -y mjpg-streamer; sudo tee /etc/systemd/system/mjpg-streamer.service >/dev/null <<'UNIT'
[Unit]
Description=mjpg-streamer camera service
After=network.target

[Service]
ExecStart=/usr/bin/mjpg_streamer -i 'input_uvc.so -d /dev/video0 -n -f 15 -r 1280x720' -o 'output_http.so -p 8081 -w /usr/lib/mjpg-streamer/www'
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload; sudo systemctl enable mjpg-streamer.service; sudo systemctl restart mjpg-streamer.service"

# 2) Fresh deploy RDWC-v4 (pull latest), restart service
Write-Host "- Deploying RDWC-v4 and restarting service..."
SSH "set -e; cd ~; [ -d RDWC-v4 ] || git clone $Repo; cd RDWC-v4; git fetch --all; git reset --hard origin/main; python3 -m venv .venv; source .venv/bin/activate; pip install --upgrade pip; pip install -r requirements.txt; [ -f .env ] || cp .env.example .env; sudo cp systemd/rdwc.service /etc/systemd/system/rdwc.service; sudo systemctl daemon-reload; sudo systemctl enable rdwc.service; sudo systemctl restart rdwc.service"

# 3) Force water circulation ON (main and chiller pumps)
Write-Host "- Forcing main and chiller pumps ON for circulation..."
SSH "curl -s -X POST http://127.0.0.1:8080/actuate/main_pump/1 >/dev/null || true"
SSH "curl -s -X POST http://127.0.0.1:8080/actuate/chiller_pump/1 >/dev/null || true"

# 4) Verify endpoints and stream
Write-Host "- Verifying RDWC service and camera..."
SSH "sudo systemctl status rdwc.service --no-pager -l | tail -n 20"
Write-Host "`n/status:"
SSH "curl -s http://127.0.0.1:8080/status"
Write-Host "`n/diag:"
SSH "curl -s http://127.0.0.1:8080/diag | head -c 2000"
Write-Host "`nCamera check:"
SSH "curl -s -I http://127.0.0.1:8081/?action=stream | head -n 1"

Write-Host "`n=== Done. Open these in your browser:"
Write-Host "  Control Panel:   http://$PiHost:8080/"
Write-Host "  Status JSON:     http://$PiHost:8080/status"
Write-Host "  Diagnostics:     http://$PiHost:8080/diag"
Write-Host "  Camera Stream:   http://$PiHost:8081/?action=stream"
# ====================== end tools/finish_rdwc.ps1 ======================