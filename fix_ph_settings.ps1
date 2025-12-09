# Fix pH dosing settings for proper stabilization and pump calibration
# Run this script to update settings on the Pi

$piHost = "192.168.88.55"
$apiUrl = "http://localhost:8080/api/settings"

Write-Host "Fixing pH dosing settings on Pi: $piHost" -ForegroundColor Cyan
Write-Host ""

# Settings to fix
$newSettings = @{
    # === CRITICAL FIXES ===
    
    # 1. Increase interval to 15 minutes (900s) to allow pH to stabilize
    "dosing.ph_min_interval_s" = "900"
    
    # 2. Fix observe window - was 7 hours (25200s), should be 10 minutes (600s)
    "dosing.observe_s_after_dose" = "600"
    
    # 3. Fix pH Up pump calibration - 25 ml/s is way too high
    #    If you measured 1ml = 1 pH change, and learned value shows 18.5ml/pH,
    #    then actual delivery is ~1.35 ml/s (25 / 18.5)
    #    Start conservative at 1 ml/s and recalibrate with actual test
    "dosing.ph_up_ml_per_sec" = "1.0"
    
    # === RECOMMENDED TUNING ===
    
    # Stabilization window - 5 minutes should be enough with 15min interval
    "dosing.ph_stabilization_window_s" = "300"
    
    # pH stability threshold - allow 0.02 pH drift during stabilization check
    "dosing.ph_stabilization_delta_threshold" = "0.02"
    
    # Initial learning dose - keep small at 0.01ml (10ms at 1ml/s)
    "dosing.ph_up_initial_ml" = "0.01"
    
    # Step size range for doses
    "dosing.ph_up_step_min_ml" = "0.5"
    "dosing.ph_up_step_max_ml" = "5.0"
    
    # Safety factor - dose 60% of calculated amount to prevent overshoot
    "dosing.ph_up_safety_factor" = "0.6"
    
    # Max predicted delta guard
    "dosing.ph_max_predicted_delta_ph" = "0.5"
    
    # Daily cap - 50ml per day max
    "dosing.ph_up_max_ml_per_day" = "50"
    
    # Single dose cap - 5ml max per dose
    "dosing.ph_up_max_single_ml" = "5"
}

Write-Host "Settings to apply:" -ForegroundColor Yellow
$newSettings.GetEnumerator() | Sort-Object Name | ForEach-Object {
    Write-Host "  $($_.Key): $($_.Value)"
}
Write-Host ""

# Confirm with user
$confirm = Read-Host "Apply these settings to $piHost? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "Aborted." -ForegroundColor Red
    exit 1
}

# Convert to JSON
$json = $newSettings | ConvertTo-Json -Compress

# Apply via SSH + curl
Write-Host ""
Write-Host "Applying settings..." -ForegroundColor Cyan
$cmd = "curl -X PUT -H 'Content-Type: application/json' -d '$json' $apiUrl"
$result = ssh pi@$piHost $cmd 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Settings applied successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "Response: $result" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Check pH chart - doses should now appear with 15min spacing"
    Write-Host "  2. Monitor learned ml/pH value - should converge to ~1.0 if your observation is correct"
    Write-Host "  3. If pump still seems off, run dosing pump calibration:"
    Write-Host "     - Go to Calibration tab"
    Write-Host "     - Run pH Up pump for known duration (e.g., 10 seconds)"
    Write-Host "     - Measure actual ml delivered"
    Write-Host "     - Calculate: ml_per_sec = measured_ml / 10"
    Write-Host "     - Update dosing.ph_up_ml_per_sec with calculated value"
    Write-Host ""
    Write-Host "⚠️  If air bubbles suspected:" -ForegroundColor Yellow
    Write-Host "  - Prime pH Up line thoroughly (30+ seconds)"
    Write-Host "  - Check for leaks/kinks in tubing"
    Write-Host "  - Verify pump head is tight and tubing is properly seated"
} else {
    Write-Host "✗ Failed to apply settings" -ForegroundColor Red
    Write-Host "Error: $result"
    exit 1
}
