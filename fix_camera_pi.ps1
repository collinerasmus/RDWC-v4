#!/usr/bin/env pwsh
# Fix camera conflicts on the Pi

$piHost = "192.168.88.49"
$piUser = "pi"

Write-Host "=== Fixing Camera Conflicts on Pi ===" -ForegroundColor Cyan

# 1. Stop and disable mjpg-streamer
Write-Host "`n[1/5] Stopping and disabling mjpg-streamer..." -ForegroundColor Yellow
ssh ${piUser}@${piHost} "sudo systemctl stop mjpg-streamer.service 2>/dev/null || true; sudo systemctl disable mjpg-streamer.service 2>/dev/null || true"

# 2. Check for other processes using the camera
Write-Host "`n[2/5] Checking for processes using the camera..." -ForegroundColor Yellow
ssh ${piUser}@${piHost} "sudo lsof /dev/video* 2>/dev/null || echo 'No processes found using camera devices'"

# 3. Kill any stray camera processes
Write-Host "`n[3/5] Killing stray camera processes..." -ForegroundColor Yellow
ssh ${piUser}@${piHost} "sudo pkill -f mjpg_streamer 2>/dev/null || true; sudo pkill -f raspistill 2>/dev/null || true; sudo pkill -f libcamera 2>/dev/null || true"

# 4. Restart the RDWC service
Write-Host "`n[4/5] Restarting RDWC service..." -ForegroundColor Yellow
ssh ${piUser}@${piHost} "sudo systemctl restart rdwc.service"

# Wait a moment for service to start
Start-Sleep -Seconds 3

# 5. Verify camera is working
Write-Host "`n[5/5] Verifying camera status..." -ForegroundColor Yellow
ssh ${piUser}@${piHost} "curl -s http://localhost:8080/camera/status"

Write-Host "`n=== Camera Fix Complete ===" -ForegroundColor Green
Write-Host "Check the output above to confirm camera is working." -ForegroundColor Cyan
