# pH Controller Comprehensive Test Script
# Tests all pH HMI endpoints and validates functionality

$base = "http://sensor-node:8080"
$ErrorActionPreference = "Stop"

Write-Host "`n╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  pH CONTROLLER COMPREHENSIVE VALIDATION & TEST SUITE  ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════╝`n" -ForegroundColor Cyan

$testsPassed = 0
$testsFailed = 0

# TEST 1: System Health
Write-Host "TEST 1: System Health Check" -ForegroundColor Yellow
try {
    $relay = Invoke-RestMethod "$base/api/relays/status" -Method Get
    $ph = Invoke-RestMethod "$base/api/ph/status" -Method Get
    $settings = Invoke-RestMethod "$base/api/settings/export" -Method Get
    
    Write-Host "  ✓ Mode: $($relay.mode) | E-STOP: $($relay.estop)" -ForegroundColor Green
    Write-Host "  ✓ pH: $($ph.ph) | Auto: $($ph.auto.enabled) | Holding: $($ph.auto.holding_reason)" -ForegroundColor Green
    Write-Host "  ✓ Reservoir: $($settings.'general.reservoir_liters')L | Targets: $($settings.'targets.ph_low')-$($settings.'targets.ph_high')" -ForegroundColor Green
    $testsPassed++
} catch {
    Write-Host "  ✗ FAILED: $_" -ForegroundColor Red
    $testsFailed++
}

# TEST 2: Hold Button
Write-Host "`nTEST 2: Hold/Resume Button Functionality" -ForegroundColor Yellow
try {
    # Get initial state
    $initialMode = Invoke-RestMethod "$base/api/controller/ph/mode" -Method Get
    Write-Host "  Initial mode: $($initialMode.mode)" -ForegroundColor Gray
    
    # Toggle to hold
    $holdResult = Invoke-RestMethod "$base/api/controller/ph/hold" -Method Post -Body "{}" -ContentType "application/json"
    if ($holdResult.ok -and $holdResult.held -eq $true) {
        Write-Host "  ✓ Hold activated: held=$($holdResult.held)" -ForegroundColor Green
    } else {
        throw "Hold activation failed"
    }
    
    Start-Sleep -Milliseconds 500
    
    # Verify held state
    $phHeld = Invoke-RestMethod "$base/api/ph/status" -Method Get
    if ($phHeld.auto.holding_reason -eq "held") {
        Write-Host "  ✓ Holding reason confirmed: $($phHeld.auto.holding_reason)" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Holding reason unexpected: $($phHeld.auto.holding_reason)" -ForegroundColor Yellow
    }
    
    # Toggle to resume
    $resumeResult = Invoke-RestMethod "$base/api/controller/ph/hold" -Method Post -Body "{}" -ContentType "application/json"
    if ($resumeResult.ok -and $resumeResult.held -eq $false) {
        Write-Host "  ✓ Resume activated: held=$($resumeResult.held)" -ForegroundColor Green
    } else {
        throw "Resume activation failed"
    }
    
    $testsPassed++
} catch {
    Write-Host "  ✗ FAILED: $_" -ForegroundColor Red
    $testsFailed++
}

# TEST 3: Guards Status
Write-Host "`nTEST 3: Guards Validation" -ForegroundColor Yellow
try {
    $ph = Invoke-RestMethod "$base/api/ph/status" -Method Get
    $guards = $ph.guards
    $guardKeys = @('estop', 'safe_off', 'sensor_stale', 'reservoir', 'interval', 'daily_cap', 'ec_baseline_low')
    $active = $guardKeys | Where-Object { $guards.$_ -eq $true }
    
    if ($active) {
        Write-Host "  ⚠ Active guards: $($active -join ', ')" -ForegroundColor Yellow
    } else {
        Write-Host "  ✓ All guards clear" -ForegroundColor Green
    }
    
    # Check critical blockers
    $criticalBlocked = ($guards.estop -or $guards.safe_off -or $guards.sensor_stale -or $guards.reservoir)
    if ($criticalBlocked) {
        Write-Host "  ⚠ CRITICAL guards blocking dosing" -ForegroundColor Yellow
    } else {
        Write-Host "  ✓ No critical guards blocking" -ForegroundColor Green
    }
    
    $testsPassed++
} catch {
    Write-Host "  ✗ FAILED: $_" -ForegroundColor Red
    $testsFailed++
}

# TEST 4: Dose Endpoint Validation
Write-Host "`nTEST 4: Dose Endpoint Validation (no actual dosing)" -ForegroundColor Yellow
try {
    # Test with invalid payload to check endpoint exists
    try {
        $doseTest = Invoke-RestMethod "$base/api/dose/ph_up" -Method Post -Body '{"seconds":0,"reason":"test"}' -ContentType "application/json"
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 400 -or $statusCode -eq 422 -or $statusCode -eq 403) {
            Write-Host "  ✓ Dose endpoint exists and validates input" -ForegroundColor Green
        } else {
            throw "Unexpected status code: $statusCode"
        }
    }
    $testsPassed++
} catch {
    Write-Host "  ✗ FAILED: $_" -ForegroundColor Red
    $testsFailed++
}

# TEST 5: Pump Relay Status
Write-Host "`nTEST 5: Pump Relay Status Check" -ForegroundColor Yellow
try {
    $relays = Invoke-RestMethod "$base/api/relays/status" -Method Get
    $phPump = $relays.relays | Where-Object { $_.name -eq 'dosing_ph_up' }
    
    if ($phPump) {
        Write-Host "  ✓ pH pump relay found: state=$($phPump.state)" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ pH pump relay not found in relay list" -ForegroundColor Yellow
    }
    $testsPassed++
} catch {
    Write-Host "  ✗ FAILED: $_" -ForegroundColor Red
    $testsFailed++
}

# SUMMARY
Write-Host "`n╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                    TEST SUMMARY                       ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host "  Passed: $testsPassed" -ForegroundColor Green
Write-Host "  Failed: $testsFailed" -ForegroundColor $(if ($testsFailed -gt 0) { "Red" } else { "Green" })
Write-Host "  Total:  $($testsPassed + $testsFailed)`n"

if ($testsFailed -eq 0) {
    Write-Host "✓ ALL TESTS PASSED - Ready for manual testing!`n" -ForegroundColor Green
    
    Write-Host "═══ MANUAL TESTING PROCEDURE ═══" -ForegroundColor Cyan
    Write-Host "1. Open http://sensor-node:8080 → pH tab"
    Write-Host "2. Click 'Hold' button (should change to 'Resume')"
    Write-Host "3. Maintenance section appears - test these buttons:"
    Write-Host "   • Prime   → Pump KPI: ON for ~200ms"
    Write-Host "   • +1 ml   → Pump KPI: ON, Recent log updates"
    Write-Host "   • +5 ml   → Pump KPI: ON, Recent log updates"
    Write-Host "4. After dosing:"
    Write-Host "   • Status KPI shows 'Cooldown Xs'"
    Write-Host "   • Guards shows 'interval' while cooling"
    Write-Host "5. Click 'Resume' → Auto mode re-enabled"
    Write-Host "6. If pH 6.50 > target 6.2: auto doses (if no guards)"
    Write-Host ""
} else {
    Write-Host "✗ TESTS FAILED - Fix issues before manual testing`n" -ForegroundColor Red
}
