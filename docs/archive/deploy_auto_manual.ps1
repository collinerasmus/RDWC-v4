#!/usr/bin/env pwsh
# Quick deployment script for auto/manual mode feature
# Run from project root: .\deploy_auto_manual.ps1

param(
    [string]$PiHost = "192.168.88.49",
    [string]$PiUser = "pi"
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 Deploying Auto/Manual Mode Feature to $PiUser@$PiHost" -ForegroundColor Green

# Deploy backend files
Write-Host "`n📦 Deploying backend..." -ForegroundColor Cyan
scp app/main.py "${PiUser}@${PiHost}:/home/pi/RDWC-v4/app/"
scp app/system_mode.py "${PiUser}@${PiHost}:/home/pi/RDWC-v4/app/"
scp app/relays_core.py "${PiUser}@${PiHost}:/home/pi/RDWC-v4/app/"

# Deploy frontend files
Write-Host "`n🎨 Deploying frontend..." -ForegroundColor Cyan
scp app/static/js/relays_v2.js "${PiUser}@${PiHost}:/home/pi/RDWC-v4/app/static/js/"
scp app/static/index.html "${PiUser}@${PiHost}:/home/pi/RDWC-v4/app/static/"

# Initialize database
Write-Host "`n💾 Initializing database tables..." -ForegroundColor Cyan
ssh "${PiUser}@${PiHost}" "cd /home/pi/RDWC-v4 && python3 -c 'from app.system_mode import _init_tables; _init_tables(); print(\"Tables initialized\")'"

# Restart service
Write-Host "`n🔄 Restarting rdwc service..." -ForegroundColor Cyan
ssh "${PiUser}@${PiHost}" "sudo systemctl restart rdwc"

# Wait for service to start
Write-Host "`n⏳ Waiting for service to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Check service status
Write-Host "`n✅ Checking service status..." -ForegroundColor Cyan
ssh "${PiUser}@${PiHost}" "sudo systemctl status rdwc --no-pager -n 10"

# Test endpoints
Write-Host "`n🧪 Testing endpoints..." -ForegroundColor Cyan

Write-Host "  System mode:" -ForegroundColor Gray
ssh "${PiUser}@${PiHost}" "curl -s http://localhost:8080/api/system_mode"

Write-Host "`n  Relay status sample:" -ForegroundColor Gray
ssh "${PiUser}@${PiHost}" "curl -s http://localhost:8080/relay/status | head -c 500"

Write-Host "`n`n🎉 Deployment complete!" -ForegroundColor Green
Write-Host "📊 Dashboard: http://${PiHost}:8080" -ForegroundColor Yellow
Write-Host "📖 Documentation: FEATURE_AUTO_MANUAL_COMPLETE.md" -ForegroundColor Yellow
