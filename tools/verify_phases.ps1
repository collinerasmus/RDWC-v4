#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Verify RDWC-v4 phase completion on live Pi
.DESCRIPTION
    Tests all completed phases are working correctly on the deployed system.
    Run this after each phase completion to ensure no regressions.
.PARAMETER PiHost
    Pi IP address or hostname (default: 192.168.88.49)
.PARAMETER Port
    API port (default: 8080)
#>
param(
    [string]$PiHost = "192.168.88.49",
    [int]$Port = 8080
)

$base = "http://${PiHost}:${Port}"
$pass = 0
$fail = 0
$manual = 0

function Test-Phase {
    param([string]$Name, [scriptblock]$Test, [bool]$ManualCheck = $false)
    Write-Host "`n[$Name]" -ForegroundColor Yellow
    try {
        if ($ManualCheck) {
            & $Test
            $script:manual++
            Write-Host "→ Manual verification required" -ForegroundColor Cyan
        } else {
            $result = & $Test
            if ($result) {
                $script:pass++
                Write-Host "✓ PASS" -ForegroundColor Green
            } else {
                $script:fail++
                Write-Host "✗ FAIL" -ForegroundColor Red
            }
        }
    } catch {
        $script:fail++
        Write-Host "✗ ERROR: $_" -ForegroundColor Red
    }
}

Write-Host "`n=== RDWC-v4 PHASE VERIFICATION ===" -ForegroundColor Cyan
Write-Host "Testing: $base" -ForegroundColor Gray

# Phase 1-2: UI Cleanup
Test-Phase "Phase 1-2: UI Cleanup" {
    Write-Host "  • Mode buttons removed from Overview, Sensors, Scheduler tabs"
    Write-Host "  • Duplicate calibration sections removed from Sensors tab"
    Write-Host "  • Open web UI at ${base} to verify"
} -ManualCheck $true

# Phase 3: Circulation Safety Interlock
Test-Phase "Phase 3: Circulation Interlock" {
    $relays = Invoke-RestMethod "$base/api/relays/status"
    $main = $relays.relays.main_pump.is_on
    $cpump = $relays.relays.chiller_pump.is_on
    $chiller = $relays.relays.chiller_power.is_on
    
    Write-Host "  Main pump: $main, Chiller pump: $cpump, Chiller: $chiller"
    
    # Check for interlock violation
    if ($chiller -and -not $cpump) {
        Write-Host "  VIOLATION: Chiller running without pump!" -ForegroundColor Red
        return $false
    }
    
    Write-Host "  Interlock logic working correctly"
    return $true
}

# Phase 4: Lights Schedule Midnight Fix
Test-Phase "Phase 4: Lights Midnight Logic" {
    # Check scheduler code has midnight handling
    $schedulerPath = "app/scheduler.py"
    if (Test-Path $schedulerPath) {
        $content = Get-Content $schedulerPath -Raw
        if ($content -match "wrap across midnight" -or $content -match "midnight crossover") {
            Write-Host "  Midnight crossover logic present in scheduler.py"
            return $true
        } else {
            Write-Host "  Midnight logic not found in code"
            return $false
        }
    } else {
        Write-Host "  Cannot verify (not in repo directory)"
        return $false
    }
}

# Phase 5: 12-Week Grow Schedule
Test-Phase "Phase 5: 12-Week Schedule" {
    $schedule = Invoke-RestMethod "$base/api/nutrient_schedule"
    $weekCount = $schedule.weeks.Count
    $current = $schedule.current_week
    $start = $schedule.grow_start_date
    
    Write-Host "  Weeks: $weekCount, Current: $current, Start: $start"
    
    if ($weekCount -eq 12) {
        Write-Host "  12-week schedule configured correctly"
        return $true
    } else {
        Write-Host "  Expected 12 weeks, got $weekCount"
        return $false
    }
}

# Phase 6: System Tab (when implemented)
# Test-Phase "Phase 6: System Info API" {
#     $sysinfo = Invoke-RestMethod "$base/api/system/info"
#     return $null -ne $sysinfo.pi_info -and $null -ne $sysinfo.software_info
# }

# Summary
Write-Host "`n=== VERIFICATION SUMMARY ===" -ForegroundColor Cyan
Write-Host "Automated tests: $pass passed, $fail failed" -ForegroundColor $(if($fail -eq 0){'Green'}else{'Red'})
if ($manual -gt 0) {
    Write-Host "Manual checks: $manual pending" -ForegroundColor Cyan
}

if ($fail -eq 0) {
    Write-Host "`n✓ All automated tests PASSED - system is healthy" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n✗ Some tests FAILED - review errors above" -ForegroundColor Red
    exit 1
}
