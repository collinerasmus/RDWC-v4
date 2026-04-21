#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Verify API state consistency fixes for RDWC-v4.
#>
param(
    [string]$TargetIp = "192.168.88.55",
    [int]$Port = 8080
)

$base = "http://${TargetIp}:${Port}"
$errors = @()
$warnings = @()

Write-Host "`n=== RDWC API Consistency Verification ===" -ForegroundColor Cyan
Write-Host "Target: $base`n" -ForegroundColor Gray

function Get-JsonValue {
    param($obj, $path)
    $parts = $path -split '\.'
    $current = $obj
    foreach ($part in $parts) {
        if ($null -eq $current) { return $null }
        $current = $current.$part
    }
    return $current
}

Write-Host "[1/4] Checking calibration flags consistency..." -ForegroundColor Yellow
try {
    $sensors = Invoke-RestMethod -Uri "$base/api/sensors" -TimeoutSec 5
    $phStatus = Invoke-RestMethod -Uri "$base/calib/ph/status" -TimeoutSec 5
    $ecStatus = Invoke-RestMethod -Uri "$base/api/ec/cal/status" -TimeoutSec 5

    $phCalSensors = Get-JsonValue $sensors "cal.ph.is_calibrated"
    $ecCalSensors = Get-JsonValue $sensors "cal.ec.is_calibrated"
    $phHasPoints = ($phStatus.flags -and $phStatus.flags.Count -gt 0)
    $ecHasPoints = ($ecStatus.low -eq $true)

    Write-Host "  pH: /api/sensors=$phCalSensors, /calib/ph/status has points=$phHasPoints" -ForegroundColor Gray
    Write-Host "  EC: /api/sensors=$ecCalSensors, /api/ec/cal/status low=$ecHasPoints" -ForegroundColor Gray

    if ($phHasPoints -and -not $phCalSensors) {
        $errors += "pH calibration mismatch: /api/sensors false while /calib/ph/status has flags"
    }
    if ($ecHasPoints -and -not $ecCalSensors) {
        $errors += "EC calibration mismatch: /api/sensors false while /api/ec/cal/status low=true"
    }
    if (($phCalSensors -eq $phHasPoints) -and ($ecCalSensors -eq $ecHasPoints)) {
        Write-Host "  OK calibration flags are consistent" -ForegroundColor Green
    }
} catch {
    $errors += "Failed calibration check: $($_.Exception.Message)"
}

Write-Host "`n[2/4] Checking sensors/health cache freshness..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "$base/api/sensors/health" -TimeoutSec 5
    $cacheAge = $health.cache_age_s
    $dbAge = $health.db_age_s

    Write-Host ("  Cache age: {0}, DB age: {1}" -f $cacheAge, $dbAge) -ForegroundColor Gray

    if (($null -ne $cacheAge) -and ($cacheAge -gt 86400)) {
        $errors += "Cache age too large ($cacheAge seconds), expected null or recent value"
    } elseif (($null -eq $cacheAge) -and ($dbAge -le 60)) {
        Write-Host "  OK cache age null is expected for sensor_poller mode with fresh DB" -ForegroundColor Green
    } elseif (($null -ne $cacheAge) -and ($cacheAge -le 300)) {
        Write-Host "  OK cache age is reasonable" -ForegroundColor Green
    } else {
        $warnings += "Cache age not ideal: cache_age_s=$cacheAge db_age_s=$dbAge"
    }
} catch {
    $errors += "Failed health check: $($_.Exception.Message)"
}

Write-Host "`n[3/4] Checking scheduler lights window..." -ForegroundColor Yellow
try {
    $scheduler = Invoke-RestMethod -Uri "$base/api/scheduler/status" -TimeoutSec 5
    $lightsOn = $scheduler.lights_on_time
    $lightsOff = $scheduler.lights_off_time

    Write-Host ("  lights_on_time: {0}, lights_off_time: {1}" -f $lightsOn, $lightsOff) -ForegroundColor Gray

    if (($null -eq $lightsOn) -or ($null -eq $lightsOff)) {
        $errors += "Scheduler lights window is null; expected computed fallback values"
    } else {
        Write-Host "  OK lights window is populated" -ForegroundColor Green
    }
} catch {
    $errors += "Failed scheduler check: $($_.Exception.Message)"
}

Write-Host "`n[4/4] Checking mode key synchronization..." -ForegroundColor Yellow
try {
    $systemMode = Invoke-RestMethod -Uri "$base/api/system_mode" -TimeoutSec 5
    $settings = Invoke-RestMethod -Uri "$base/api/settings" -TimeoutSec 5

    $apiMode = $systemMode.mode
    $unifiedMode = Get-JsonValue $settings "root.unified_mode"
    $legacyMode = Get-JsonValue $settings "system.mode"

    Write-Host "  /api/system_mode: $apiMode" -ForegroundColor Gray
    Write-Host "  root.unified_mode: $unifiedMode" -ForegroundColor Gray
    Write-Host "  system.mode: $legacyMode" -ForegroundColor Gray

    if ($apiMode -ne $unifiedMode) {
        $errors += "Mode drift: /api/system_mode=$apiMode but unified_mode=$unifiedMode"
    }
    if ($legacyMode -and ($legacyMode -ne $apiMode)) {
        $warnings += "Legacy system.mode differs from current mode (will sync on /api/system_mode GET)"
    } else {
        Write-Host "  OK mode keys are synchronized" -ForegroundColor Green
    }
} catch {
    $errors += "Failed mode check: $($_.Exception.Message)"
}

Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
if (($errors.Count -eq 0) -and ($warnings.Count -eq 0)) {
    Write-Host "PASS: all checks passed" -ForegroundColor Green
    exit 0
}

if ($errors.Count -gt 0) {
    Write-Host ("FAIL: errors ({0})" -f $errors.Count) -ForegroundColor Red
    foreach ($e in $errors) {
        Write-Host "  - $e" -ForegroundColor Red
    }
}
if ($warnings.Count -gt 0) {
    Write-Host ("WARN: warnings ({0})" -f $warnings.Count) -ForegroundColor Yellow
    foreach ($w in $warnings) {
        Write-Host "  - $w" -ForegroundColor Yellow
    }
}

exit $errors.Count
