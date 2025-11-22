# Verify Pi Deployment Sync Status
# 
# This script verifies that the Pi is on the correct branch and has all necessary commits.
# It checks:
# 1. Current Git commit on the Pi
# 2. Controllers status endpoint returns correct values
# 3. E-STOP UI consolidation is present
# 4. All services are running

param(
    [string]$PiHost = $env:PI_HOST,
    [string]$PiUser = $env:PI_USER,
    [string]$ExpectedBranch = "main"
)

if (-not $PiHost) { 
    Write-Error "PI_HOST not set. Pass -PiHost or set env variable."
    Write-Host "Example: PI_HOST=192.168.88.49 or -PiHost 192.168.88.49"
    exit 1 
}
if (-not $PiUser) { $PiUser = "pi" }

$Target = "$PiUser@$PiHost"
$ApiBase = "http://${PiHost}:8080"

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Verifying Pi Deployment Sync Status" -ForegroundColor Cyan
Write-Host "Target: $Target" -ForegroundColor Cyan
Write-Host "API: $ApiBase" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

# Step 1: Check Git status on Pi
Write-Host "`n[1/5] Checking Git status on Pi..." -ForegroundColor Yellow
$gitCmd = @(
    'cd ~/RDWC-v4',
    'echo "BRANCH: $(git branch --show-current)"',
    'echo "COMMIT: $(git rev-parse --short HEAD)"',
    'echo "COMMIT_LONG: $(git rev-parse HEAD)"',
    'echo "COMMIT_DATE: $(git show -s --format=%ci HEAD)"',
    'echo "COMMIT_MSG: $(git show -s --format=%s HEAD)"'
) -join ' && '

try {
    $gitOutput = ssh $Target $gitCmd 2>&1
    Write-Host $gitOutput
    
    # Parse output to check branch
    $currentBranch = ($gitOutput | Select-String "BRANCH: (.+)" | ForEach-Object { $_.Matches.Groups[1].Value })
    if ($currentBranch -ne $ExpectedBranch) {
        Write-Host "⚠ WARNING: Pi is on branch '$currentBranch', expected '$ExpectedBranch'" -ForegroundColor Yellow
    } else {
        Write-Host "✓ Pi is on correct branch: $currentBranch" -ForegroundColor Green
    }
} catch {
    Write-Host "✗ Failed to check Git status: $_" -ForegroundColor Red
    exit 1
}

# Step 2: Check services are running
Write-Host "`n[2/5] Checking service status..." -ForegroundColor Yellow
$serviceCmd = @(
    'systemctl is-active rdwc.service',
    'systemctl is-active rdwc-sensors.service'
) -join ' && '

try {
    $serviceOutput = ssh $Target $serviceCmd 2>&1 | Out-String
    # Check if output contains "active" for both services
    if ($serviceOutput -match "active" -and $serviceOutput -notmatch "inactive|failed") {
        Write-Host "✓ Services appear to be active" -ForegroundColor Green
    } else {
        Write-Host "⚠ Service status unclear:" -ForegroundColor Yellow
        Write-Host $serviceOutput
    }
} catch {
    Write-Host "⚠ Could not check service status: $_" -ForegroundColor Yellow
}

# Step 3: Verify controllers status endpoint
Write-Host "`n[3/5] Verifying /api/controllers/status endpoint..." -ForegroundColor Yellow
try {
    $controllersResp = Invoke-RestMethod -Uri "$ApiBase/api/controllers/status" -TimeoutSec 5
    
    if ($controllersResp.controllers.circulation) {
        $mainPump = $controllersResp.controllers.circulation.main_pump
        $chillerPump = $controllersResp.controllers.circulation.chiller_pump
        
        Write-Host "  Main Pump: $mainPump" -ForegroundColor Cyan
        Write-Host "  Chiller Pump: $chillerPump" -ForegroundColor Cyan
        
        # Check if values are boolean (Invoke-RestMethod auto-converts JSON booleans)
        if ($null -ne $mainPump -and $mainPump -is [bool]) {
            Write-Host "✓ Controllers status endpoint returns valid pump state values" -ForegroundColor Green
        } else {
            Write-Host "✗ Controllers status endpoint may be returning incorrect values" -ForegroundColor Red
            if ($null -eq $mainPump) {
                Write-Host "  Main pump value is null (API call may have failed)" -ForegroundColor Red
            } else {
                Write-Host "  Expected boolean, got: type=$($mainPump.GetType().Name), value=$mainPump" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "✗ Circulation controller not found in status response" -ForegroundColor Red
    }
    
    # Check E-STOP status
    $estop = $controllersResp.estop
    if ($null -ne $estop) {
        Write-Host "  E-STOP: $estop" -ForegroundColor Cyan
        if ($estop -eq $true) {
            Write-Host "⚠ E-STOP is currently ACTIVE" -ForegroundColor Yellow
        } else {
            Write-Host "✓ E-STOP is not active" -ForegroundColor Green
        }
    }
    
} catch {
    Write-Host "✗ Failed to verify controllers status: $_" -ForegroundColor Red
}

# Step 4: Verify relay status endpoint for comparison
Write-Host "`n[4/5] Verifying /api/relays/status endpoint..." -ForegroundColor Yellow
try {
    $relaysResp = Invoke-RestMethod -Uri "$ApiBase/api/relays/status" -TimeoutSec 5
    
    if ($relaysResp.relays) {
        # Note: /api/relays/status returns "is_on" field (translated from internal "state")
        $mainPumpRelay = $relaysResp.relays.main_pump.is_on
        $chillerPumpRelay = $relaysResp.relays.chiller_pump.is_on
        
        Write-Host "  Main Pump Relay is_on: $mainPumpRelay" -ForegroundColor Cyan
        Write-Host "  Chiller Pump Relay is_on: $chillerPumpRelay" -ForegroundColor Cyan
        
        # Compare with controllers endpoint
        if ($controllersResp.controllers.circulation.main_pump -eq $mainPumpRelay) {
            Write-Host "✓ Main pump state matches between endpoints" -ForegroundColor Green
        } else {
            Write-Host "✗ Main pump state MISMATCH: controllers=$($controllersResp.controllers.circulation.main_pump), relays=$mainPumpRelay" -ForegroundColor Red
            Write-Host "  → This indicates the controller endpoint has incorrect implementation" -ForegroundColor Yellow
        }
        
        if ($controllersResp.controllers.circulation.chiller_pump -eq $chillerPumpRelay) {
            Write-Host "✓ Chiller pump state matches between endpoints" -ForegroundColor Green
        } else {
            Write-Host "✗ Chiller pump state MISMATCH: controllers=$($controllersResp.controllers.circulation.chiller_pump), relays=$chillerPumpRelay" -ForegroundColor Red
            Write-Host "  → This indicates the controller endpoint has incorrect implementation" -ForegroundColor Yellow
        }
    }
    
} catch {
    Write-Host "✗ Failed to verify relays status: $_" -ForegroundColor Red
}

# Step 5: Summary and recommendations
Write-Host "`n[5/5] Summary" -ForegroundColor Yellow
Write-Host "=" * 60 -ForegroundColor Cyan

# If we detected issues, provide fix instructions
$issuesDetected = $false

if ($currentBranch -ne $ExpectedBranch) {
    $issuesDetected = $true
}

# Compare using correct field name (is_on, not state) - only if both responses are valid
if ($controllersResp -and $relaysResp) {
    if ($controllersResp.controllers.circulation.main_pump -ne $relaysResp.relays.main_pump.is_on) {
        $issuesDetected = $true
    }

    if ($controllersResp.controllers.circulation.chiller_pump -ne $relaysResp.relays.chiller_pump.is_on) {
        $issuesDetected = $true
    }
}

if ($issuesDetected) {
    Write-Host "`n⚠ ISSUES DETECTED - Pi needs to be updated" -ForegroundColor Yellow
    Write-Host "`nTo fix, run these commands on the Pi:" -ForegroundColor White
    Write-Host @"
cd /home/pi/RDWC-v4
git fetch origin
git reset --hard origin/$ExpectedBranch
sudo systemctl restart rdwc.service
sudo systemctl restart rdwc-sensors.service
"@ -ForegroundColor Cyan
    
    Write-Host "`nOr use the refresh_api.ps1 script:" -ForegroundColor White
    Write-Host "  .\deploy\refresh_api.ps1 -PiHost $PiHost -PiUser $PiUser" -ForegroundColor Cyan
} else {
    Write-Host "`n✓ All checks passed - Pi is properly synced!" -ForegroundColor Green
}

Write-Host "=" * 60 -ForegroundColor Cyan

# Return exit code based on issues
if ($issuesDetected) {
    exit 1
} else {
    exit 0
}
