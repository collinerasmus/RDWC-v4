#!/usr/bin/env pwsh
# Live monitoring dashboard for RDWC auto-dosing system

param(
    [string]$PiHost = "192.168.88.49",
    [int]$RefreshSeconds = 10
)

Write-Host "=== RDWC Auto-Dosing Monitor ===" -ForegroundColor Cyan
Write-Host "Pi Host: $PiHost" -ForegroundColor Gray
Write-Host "Refresh: every $RefreshSeconds seconds" -ForegroundColor Gray
Write-Host "Press Ctrl+C to exit" -ForegroundColor Gray
Write-Host ""

while ($true) {
    Clear-Host
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    Write-Host "=== RDWC Auto-Dosing Monitor === $timestamp" -ForegroundColor Cyan
    Write-Host ""
    
    # Get sensor data
    Write-Host "📊 CURRENT READINGS:" -ForegroundColor Yellow
    $sensors = ssh $PiHost "curl -s http://127.0.0.1:8080/api/sensors" | ConvertFrom-Json
    if ($sensors.online) {
        $phColor = if ($sensors.ph -ge 5.8 -and $sensors.ph -le 6.2) { "Green" } else { "Yellow" }
        $ecColor = if ($sensors.ec_mscm -ge 800 -and $sensors.ec_mscm -le 1200) { "Green" } else { "Yellow" }
        
        Write-Host "  pH:          " -NoNewline
        Write-Host ("{0:F3}" -f $sensors.ph) -ForegroundColor $phColor -NoNewline
        Write-Host "  (target: 5.8-6.2)"
        
        Write-Host "  EC:          " -NoNewline
        Write-Host ("{0:F1} µS/cm" -f $sensors.ec_mscm) -ForegroundColor $ecColor -NoNewline
        Write-Host "  (target: 800-1200)"
        
        Write-Host "  Temperature: {0:F2}°C" -f $sensors.temperature_c
        Write-Host "  Data Age:    $($sensors.age_seconds)s" -ForegroundColor $(if ($sensors.age_seconds -lt 60) { "Green" } else { "Red" })
    } else {
        Write-Host "  SENSORS OFFLINE" -ForegroundColor Red
    }
    
    Write-Host ""
    
    # Get recent pH doses
    Write-Host "💧 RECENT pH DOSES:" -ForegroundColor Yellow
    $phDoses = ssh $PiHost "sqlite3 /home/pi/RDWC-v4/data/rdwc.db 'SELECT ts_utc, action, volume_ml, pre_ph, post_ph, reason FROM ph_dose_log ORDER BY rowid DESC LIMIT 5'" 2>$null
    if ($phDoses) {
        $phDoses | ForEach-Object {
            $parts = $_ -split '\|'
            if ($parts.Count -ge 6) {
                Write-Host ("  {0} | {1:F2}ml | {2} -> {3} | {4}" -f $parts[0].Substring(0,19), [double]$parts[2], $parts[3], $parts[4], $parts[5])
            }
        }
    } else {
        Write-Host "  No doses yet" -ForegroundColor Gray
    }
    
    Write-Host ""
    
    # Get recent EC doses  
    Write-Host "🌱 RECENT EC DOSES:" -ForegroundColor Yellow
    $ecDoses = ssh $PiHost "sqlite3 /home/pi/RDWC-v4/data/rdwc.db 'SELECT ts_utc, pump, volume_ml, pre_ec, post_ec, reason FROM ec_dose_log ORDER BY rowid DESC LIMIT 5'" 2>$null
    if ($ecDoses) {
        $ecDoses | ForEach-Object {
            $parts = $_ -split '\|'
            if ($parts.Count -ge 6) {
                Write-Host ("  {0} | {1} | {2:F2}ml | EC: {3} -> {4} | {5}" -f $parts[0].Substring(0,19), $parts[1], [double]$parts[2], $parts[3], $parts[4], $parts[5])
            }
        }
    } else {
        Write-Host "  No doses yet" -ForegroundColor Gray
    }
    
    Write-Host ""
    Write-Host "Next update in $RefreshSeconds seconds..." -ForegroundColor Gray
    Start-Sleep -Seconds $RefreshSeconds
}
