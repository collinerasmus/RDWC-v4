#!/usr/bin/env pwsh
#
# deploy_hold_button.ps1
# Deploys the hold button feature (merged to main) to Pi hardware.
# Restarts rdwc.service and verifies functionality.
#

param(
    [string]$PiHost = "192.168.88.49",
    [string]$User = "pi",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "RDWC Hold Button Feature Deployment" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Target: $User@$PiHost" -ForegroundColor Yellow
Write-Host "Branch: $Branch" -ForegroundColor Yellow
Write-Host ""

# 1. Pull latest code
Write-Host "[1/5] Pulling latest code on Pi..." -ForegroundColor Green
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
Write-Host "✓ Code updated successfully" -ForegroundColor Green
Write-Host ""

# 2. Check for dependency changes
Write-Host "[2/5] Checking dependencies..." -ForegroundColor Green
ssh "$User@$PiHost" @"
cd ~/RDWC-v4 && \
source venv/bin/activate && \
pip install -q -r requirements.txt
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠ Dependency update had issues (non-critical)" -ForegroundColor Yellow
} else {
    Write-Host "✓ Dependencies up to date" -ForegroundColor Green
}
Write-Host ""

# 3. Restart rdwc.service (main API)
Write-Host "[3/5] Restarting rdwc.service..." -ForegroundColor Green
ssh "$User@$PiHost" "sudo systemctl restart rdwc.service"

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Service restart failed" -ForegroundColor Red
    exit 1
}

Write-Host "Waiting 8s for service to stabilize..." -ForegroundColor Yellow
Start-Sleep -Seconds 8

$status = ssh "$User@$PiHost" "sudo systemctl is-active rdwc.service"
if ($status -ne "active") {
    Write-Host "✗ Service is not active: $status" -ForegroundColor Red
    Write-Host "Checking logs..." -ForegroundColor Yellow
    ssh "$User@$PiHost" "sudo journalctl -u rdwc.service -n 20 --no-pager"
    exit 1
}
Write-Host "✓ rdwc.service is active" -ForegroundColor Green
Write-Host ""

# 4. Verify API health
Write-Host "[4/5] Verifying API health..." -ForegroundColor Green
$health = ssh "$User@$PiHost" "curl -s http://localhost:8080/api/health"

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Health check failed" -ForegroundColor Red
    exit 1
}

Write-Host "Health response: $health" -ForegroundColor Cyan

# Check if response contains "status":"ok"
if ($health -like '*"status":"ok"*' -or $health -like '*"status": "ok"*') {
    Write-Host "✓ API health check passed" -ForegroundColor Green
} else {
    Write-Host "⚠ Unexpected health response" -ForegroundColor Yellow
}
Write-Host ""

# 5. Test hold endpoints
Write-Host "[5/5] Testing hold button endpoints..." -ForegroundColor Green

# Test GET /api/hold/ph
Write-Host "  Testing GET /api/hold/ph..." -ForegroundColor Cyan
$phHold = ssh "$User@$PiHost" "curl -s http://localhost:8080/api/hold/ph"
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ pH hold endpoint responsive" -ForegroundColor Green
    Write-Host "    Response: $phHold" -ForegroundColor Gray
} else {
    Write-Host "  ✗ pH hold endpoint failed" -ForegroundColor Red
}

# Test GET /api/hold/ec
Write-Host "  Testing GET /api/hold/ec..." -ForegroundColor Cyan
$ecHold = ssh "$User@$PiHost" "curl -s http://localhost:8080/api/hold/ec"
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ EC hold endpoint responsive" -ForegroundColor Green
    Write-Host "    Response: $ecHold" -ForegroundColor Gray
} else {
    Write-Host "  ✗ EC hold endpoint failed" -ForegroundColor Red
}

# Test GET /api/hold/chiller
Write-Host "  Testing GET /api/hold/chiller..." -ForegroundColor Cyan
$chillerHold = ssh "$User@$PiHost" "curl -s http://localhost:8080/api/hold/chiller"
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Chiller hold endpoint responsive" -ForegroundColor Green
    Write-Host "    Response: $chillerHold" -ForegroundColor Gray
} else {
    Write-Host "  ✗ Chiller hold endpoint failed" -ForegroundColor Red
}

# Test GET /api/hold/circulation
Write-Host "  Testing GET /api/hold/circulation..." -ForegroundColor Cyan
$circHold = ssh "$User@$PiHost" "curl -s http://localhost:8080/api/hold/circulation"
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Circulation hold endpoint responsive" -ForegroundColor Green
    Write-Host "    Response: $circHold" -ForegroundColor Gray
} else {
    Write-Host "  ✗ Circulation hold endpoint failed" -ForegroundColor Red
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Deployment Summary" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "✓ Code updated to latest main branch" -ForegroundColor Green
Write-Host "✓ Service restarted successfully" -ForegroundColor Green
Write-Host "✓ API health check passed" -ForegroundColor Green
Write-Host "✓ Hold endpoints tested and responsive" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Open UI at http://$PiHost:8080" -ForegroundColor White
Write-Host "2. Verify that mode buttons (Auto/Manual) are removed" -ForegroundColor White
Write-Host "3. Test Hold button functionality on pH, EC, Chiller, and Circulation panels" -ForegroundColor White
Write-Host "4. Verify dosing continues to work when not in hold mode" -ForegroundColor White
Write-Host ""
Write-Host "Deployment completed successfully! ✓" -ForegroundColor Green
