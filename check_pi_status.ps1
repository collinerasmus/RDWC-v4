# Quick Pi Status Checker
# Run this from Windows to see what's happening on the Pi

$PI = "192.168.88.49"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "   RDWC Pi Status Check" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Test network connectivity
Write-Host "1. Network Connection..." -ForegroundColor Yellow
$ping = Test-Connection -ComputerName $PI -Count 1 -Quiet
if ($ping) {
    Write-Host "   ✓ Pi is reachable" -ForegroundColor Green
} else {
    Write-Host "   ✗ Pi is NOT reachable" -ForegroundColor Red
    exit
}

# Test API
Write-Host "`n2. API Status..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://${PI}:8080/api/relays/status" -TimeoutSec 5
    Write-Host "   ✓ API is responding" -ForegroundColor Green
    Write-Host "   Mode: $($response.mode)" -ForegroundColor White
    Write-Host "   E-STOP: $($response.estop)" -ForegroundColor White
} catch {
    Write-Host "   ✗ API is NOT responding" -ForegroundColor Red
}

# Check sensors
Write-Host "`n3. Sensors..." -ForegroundColor Yellow
try {
    $sensors = Invoke-RestMethod -Uri "http://${PI}:8080/api/sensors" -TimeoutSec 5
    if ($sensors.online) {
        Write-Host "   ✓ Sensors online" -ForegroundColor Green
        Write-Host "   Temperature: $($sensors.temperature_c)°C" -ForegroundColor White
        Write-Host "   pH: $($sensors.ph)" -ForegroundColor White
        Write-Host "   EC: $($sensors.ec_mscm) mS/cm" -ForegroundColor White
        Write-Host "   Age: $($sensors.age_seconds)s" -ForegroundColor White
    } else {
        Write-Host "   ✗ Sensors offline" -ForegroundColor Red
    }
} catch {
    Write-Host "   ✗ Cannot read sensors" -ForegroundColor Red
}

# Check relays
Write-Host "`n4. Relay Status..." -ForegroundColor Yellow
try {
    $relays = Invoke-RestMethod -Uri "http://${PI}:8080/api/relays/status" -TimeoutSec 5
    Write-Host "   Main Pump: $($relays.relays.main_pump.is_on)" -ForegroundColor White
    Write-Host "   Chiller Pump: $($relays.relays.chiller_pump.is_on)" -ForegroundColor White
    Write-Host "   Chiller Power: $($relays.relays.chiller_power.is_on)" -ForegroundColor White
    Write-Host "   Lights: $($relays.relays.lights.is_on)" -ForegroundColor White
} catch {
    Write-Host "   ✗ Cannot read relays" -ForegroundColor Red
}

# Check controller modes
Write-Host "`n5. Controller Modes..." -ForegroundColor Yellow
try {
    $modes = Invoke-RestMethod -Uri "http://${PI}:8080/api/controller/modes" -TimeoutSec 5
    Write-Host "   System: $($modes.system_mode)" -ForegroundColor White
    Write-Host "   pH: $($modes.modes.ph)" -ForegroundColor White
    Write-Host "   EC: $($modes.modes.ec)" -ForegroundColor White
    Write-Host "   Chiller: $($modes.modes.chiller)" -ForegroundColor White
    Write-Host "   Lights: $($modes.modes.lights)" -ForegroundColor White
} catch {
    Write-Host "   ✗ Cannot read modes" -ForegroundColor Red
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "If everything shows ✓, the Pi is healthy." -ForegroundColor Cyan
Write-Host "The browser 'offline' is just stale JS." -ForegroundColor Cyan
Write-Host "`nClose browser, reopen, and press Ctrl+Shift+F5" -ForegroundColor Yellow
Write-Host "========================================`n" -ForegroundColor Cyan
