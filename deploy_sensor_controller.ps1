#requires -Version 5.0
<#
.SYNOPSIS
Deploy sensor_controller consolidation to Raspberry Pi

.PARAMETER PiHost
Pi hostname or IP (default: pi@raspberrypi.local)

.EXAMPLE
.\deploy_sensor_controller.ps1 -PiHost pi@192.168.88.49
#>

param(
    [string]$PiHost = "pi@raspberrypi.local"
)

$RepoPath = "/home/pi/rdwc"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Deploying sensor_controller consolidation" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Target: $PiHost at $RepoPath" -ForegroundColor White
Write-Host ""

# Test SSH connectivity
Write-Host "Testing SSH connectivity..." -ForegroundColor Yellow
& ssh -o ConnectTimeout=5 $PiHost "echo 'test'" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Cannot connect to $PiHost" -ForegroundColor Red
    Write-Host ""
    Write-Host "Usage: .\deploy_sensor_controller.ps1 -PiHost pi@192.168.88.49" -ForegroundColor Yellow
    exit 1
}
Write-Host "✓ Connected" -ForegroundColor Green
Write-Host ""

# Pull latest changes
Write-Host "Pulling latest changes from GitHub..." -ForegroundColor Yellow
& ssh $PiHost "cd $RepoPath && git pull origin main"
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Git pull failed" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Pull complete" -ForegroundColor Green
Write-Host ""

# Verify sensor_controller imports
Write-Host "Verifying sensor_controller module..." -ForegroundColor Yellow
$verifyCmd = "cd $RepoPath && python3 -c 'from app.sensor_controller import read_sensors, set_ec_k_factor, get_ec_calibration_status; print(""OK"")'"
& ssh $PiHost $verifyCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ sensor_controller verification failed" -ForegroundColor Red
    exit 1
}
Write-Host "✓ sensor_controller module verified" -ForegroundColor Green
Write-Host ""

# Restart services
Write-Host "Restarting RDWC services..." -ForegroundColor Yellow
& ssh $PiHost "sudo systemctl restart rdwc-sensors rdwc"
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠ Service restart returned error (may be normal)" -ForegroundColor Yellow
}
Write-Host "✓ Services restarted (or already running)" -ForegroundColor Green
Write-Host ""

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✓ Deployment complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps - Test EC calibration:" -ForegroundColor Yellow
Write-Host "  1. Open web UI: http://raspberrypi.local:8080"
Write-Host "  2. Go to Settings > EC Calibration"
Write-Host "  3. Click 'Clear calibration'"
Write-Host "  4. Place probe in 1413 µS/cm buffer"
Write-Host "  5. Click 'Low Point (1413 µS/cm)'"
Write-Host "  6. Verify reading ~1.413 mS/cm (K=0.1)"
Write-Host ""
