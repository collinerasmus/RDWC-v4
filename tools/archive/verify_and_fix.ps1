# ===================== tools/verify_and_fix.ps1 =====================
param(
  [string]$PiHost = "192.168.88.49",
  [string]$PiUser = "pi",
  [int]$Port = 22
)
$ErrorActionPreference = "Stop"
function RunSSH($c){ & ssh -p $Port "$PiUser@$PiHost" $c }

Write-Host "=== RDWC-v4: Verify & Fix (Sensors + Camera) ==="

# 1) Show key .env bits (no secrets, just behavior)
Write-Host "`n[.env check]"
RunSSH "grep -E '^(ENV|FORCE_MOCK_SENSORS|I2C_BUS|PH_ADDR|EC_ADDR|RTD_ADDR)=' ~/RDWC-v4/.env || true"

# 2) I2C sanity + addresses
Write-Host "`n[I2C bus scan]"
RunSSH "ls -l /dev/i2c-1 || true"
RunSSH "i2cdetect -y 1 | sed -n '1,20p'"

# 3) Force sampler restart to clear any stale state
RunSSH "sudo systemctl restart rdwc.service && sleep 2"

# 4) Hit diagnostics and fixer endpoints to force a real read
Write-Host "`n[/diag snapshot]"
RunSSH "curl -s http://127.0.0.1:8080/diag | head -c 1200"

Write-Host "`n[/fix_ezo run]"
RunSSH "curl -s -X POST http://127.0.0.1:8080/fix_ezo | head -c 1200"

Write-Host "`n[/status after fixer]"
$stat = RunSSH "curl -s http://127.0.0.1:8080/status"
$stat | Out-Host

# quick PASS/FAIL for sensors
if ($stat -match '"temperature_c":\s*([0-9])' -and $stat -match '"ec":\s*([0-9])' -and $stat -match '"pH":\s*([0-9])') {
  Write-Host "`n[RESULT] ✅ Sensors: LIVE numeric readings detected." -ForegroundColor Green
} else {
  Write-Host "`n[RESULT] ❌ Sensors: No numeric readings yet. See /diag output above. If probes are dry/unsubmerged you will see blanks." -ForegroundColor Yellow
}

# 5) CAMERA: detect device and (re)start service reliably
Write-Host "`n[Camera check]"
RunSSH "id -nG $PiUser | tr ' ' '\n' | grep -qx video || sudo adduser $PiUser video || true"
RunSSH "sudo apt-get update -y && sudo apt-get install -y mjpg-streamer v4l-utils >/dev/null 2>&1 || true"
$camInfo = RunSSH "ls /dev/video* 2>/dev/null || echo 'NO_CAMERA'"
$svc = RunSSH "systemctl is-active mjpg-streamer.service || true"

Write-Host "Devices: $camInfo"
Write-Host "Service: $svc"

# ensure wrapper exists (robust autodetect)
RunSSH @"
set -e
sudo tee /usr/local/bin/start_mjpg.sh >/dev/null <<'SH'
#!/usr/bin/env bash
set -e
BIN=\$(command -v mjpg_streamer)
PLUG=""
for P in /usr/lib/mjpg-streamer /usr/lib/arm-linux-gnueabihf/mjpg-streamer /usr/lib/mjpg-streamer-experimental; do
  [ -d "\$P" ] && PLUG="\$P"
done
[ -z "\$PLUG" ] && { echo "plugins not found"; exit 1; }
DEV=/dev/video0; [ -e "\$DEV" ] || DEV=\$(ls /dev/video* 2>/dev/null | head -n1)
[ -z "\$DEV" ] && { echo "no /dev/video* device"; exit 2; }
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
"@

# start/repair only if a camera exists
if ($camInfo -match "/dev/video") {
  RunSSH "sudo systemctl enable mjpg-streamer.service >/dev/null 2>&1 || true"
  RunSSH "sudo systemctl restart mjpg-streamer.service && sleep 2"
  $head = RunSSH "curl -s -I http://127.0.0.1:8081/?action=stream | head -n 1 || true"
  Write-Host "Stream HEAD: $head"
  if ($head -match "200 OK") {
    Write-Host "[RESULT] ✅ Camera: Streaming on :8081." -ForegroundColor Green
  } else {
    Write-Host "[RESULT] ❌ Camera: Not streaming yet. Check that the USB camera is fully plugged in and seen as /dev/video*." -ForegroundColor Yellow
  }
} else {
  Write-Host "[RESULT] ❌ Camera: No /dev/video* found. Plug the USB camera into the Pi and re-run this script." -ForegroundColor Yellow
}

Write-Host "`nOpen:"
Write-Host "  UI       http://$PiHost:8080/"
Write-Host "  Status   http://$PiHost:8080/status"
Write-Host "  Diag     http://$PiHost:8080/diag"
Write-Host "  Camera   http://$PiHost:8081/?action=stream"
Write-Host "=== Verify & Fix complete ==="
# =================== end tools/verify_and_fix.ps1 ===================