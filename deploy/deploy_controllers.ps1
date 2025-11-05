#!/usr/bin/env pwsh
#
# deploy_controllers.ps1
# Deploys feat/manual-dosing-safe-caps branch to Pi, restarts rdwc.service,
# and verifies health endpoints + I²C ownership.
#

param(
    [string]$PiHost = "raspberrypi.local",
    [string]$User = "pi",
    [string]$Branch = "feat/manual-dosing-safe-caps"
)

$ErrorActionPreference = "Stop"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "RDWC Controllers Deployment" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

Write-Host "Target: $User@$PiHost" -ForegroundColor Yellow
Write-Host "Branch: $Branch" -ForegroundColor Yellow
Write-Host ""

# 1. Pull branch
Write-Host "[1/5] Pulling branch on Pi..." -ForegroundColor Green
ssh "$User@$PiHost" @"
cd ~/RDWC-v4 && \
git fetch origin && \
git checkout $Branch && \
git pull origin $Branch
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Git pull failed" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Branch pulled" -ForegroundColor Green
Write-Host ""

# 2. Restart rdwc.service
Write-Host "[2/5] Restarting rdwc.service..." -ForegroundColor Green
ssh "$User@$PiHost" "sudo systemctl restart rdwc.service"

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Service restart failed" -ForegroundColor Red
    exit 1
}

Write-Host "Waiting 5s for service to stabilize..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

$status = ssh "$User@$PiHost" "sudo systemctl is-active rdwc.service"
if ($status -ne "active") {
    Write-Host "✗ Service not active: $status" -ForegroundColor Red
    exit 1
}

Write-Host "✓ rdwc.service active" -ForegroundColor Green
Write-Host ""

# 3. Check health endpoints
Write-Host "[3/5] Health endpoints check..." -ForegroundColor Green
Write-Host ""

Write-Host "→ /api/health" -ForegroundColor Cyan
ssh "$User@$PiHost" "curl -s http://localhost:5000/api/health | jq"
Write-Host ""

Write-Host "→ /api/sensors/last" -ForegroundColor Cyan
ssh "$User@$PiHost" "curl -s http://localhost:5000/api/sensors/last | jq"
Write-Host ""

Write-Host "→ /api/settings (safety caps)" -ForegroundColor Cyan
ssh "$User@$PiHost" "curl -s http://localhost:5000/api/settings | jq '.safety | {max_seconds_per_press, max_total_seconds_per_24h, min_off_window_sec}'"
Write-Host ""

Write-Host "→ /api/dose/recent?limit=5" -ForegroundColor Cyan
ssh "$User@$PiHost" "curl -s 'http://localhost:5000/api/dose/recent?limit=5' | jq"
Write-Host ""

# 4. Verify I²C ownership
Write-Host "[4/5] I²C ownership check..." -ForegroundColor Green
Write-Host ""

$i2cOwner = ssh "$User@$PiHost" "sudo lsof /dev/i2c-1 2>&1"
Write-Host $i2cOwner

if ($i2cOwner -match "rdwc-sensors") {
    Write-Host "✓ I²C owned by rdwc-sensors.service (expected)" -ForegroundColor Green
} else {
    Write-Host "✗ Unexpected I²C owner (should be rdwc-sensors.service only)" -ForegroundColor Yellow
}
Write-Host ""

# 5. Service status summary
Write-Host "[5/5] Service status..." -ForegroundColor Green
Write-Host ""

Write-Host "→ rdwc.service" -ForegroundColor Cyan
ssh "$User@$PiHost" "sudo systemctl status rdwc.service --no-pager -l | head -20"
Write-Host ""

Write-Host "→ rdwc-sensors.service" -ForegroundColor Cyan
ssh "$User@$PiHost" "sudo systemctl status rdwc-sensors.service --no-pager -l | head -20"
Write-Host ""

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "Deployment complete!" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Run happy path test: curl -X POST http://localhost:5000/api/dose/grow -H 'Content-Type: application/json' -d '{\"seconds\":0.5,\"reason\":\"happy path\",\"actor\":\"ops\"}'" -ForegroundColor Gray
Write-Host "2. Run press cap test: curl -X POST http://localhost:5000/api/dose/grow -H 'Content-Type: application/json' -d '{\"seconds\":9.0,\"reason\":\"press cap test\",\"actor\":\"ops\"}'" -ForegroundColor Gray
Write-Host "3. Run min-off test: repeat dose immediately after successful dose" -ForegroundColor Gray
Write-Host "4. Check UI: dose buttons, logs, trend markers" -ForegroundColor Gray
Write-Host "5. Inspect logs: sudo journalctl -u rdwc.service -n 50 --no-pager" -ForegroundColor Gray
Write-Host ""
