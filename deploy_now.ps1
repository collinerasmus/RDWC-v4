#!/usr/bin/env pwsh
# Quick deploy script for Windows -> Pi
# Pushes code and restarts service

$piHost = "pi@192.168.88.49"
$piPath = "/home/pi/RDWC-v4"

Write-Host "=== Deploying to Pi ===" -ForegroundColor Cyan

# Push if needed
Write-Host "Ensuring commits are pushed..." -ForegroundColor Yellow
git push origin main 2>&1 | Out-Null

# Deploy commands
$deployScript = @"
cd $piPath && \
git pull origin main && \
sudo cp systemd/rdwc.service /etc/systemd/system/ && \
sudo systemctl daemon-reload && \
sudo systemctl restart rdwc.service && \
sleep 2 && \
sudo systemctl status rdwc.service --no-pager -l
"@

Write-Host "Connecting to Pi and deploying..." -ForegroundColor Yellow
ssh $piHost $deployScript

Write-Host "`n=== Deploy Complete ===" -ForegroundColor Green
Write-Host "Next: Hard reload dashboard (Ctrl+F5) and test relay toggle" -ForegroundColor Cyan
