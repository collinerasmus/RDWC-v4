# Monitor pH auto-dosing recovery after learner reset
# Run this to watch for the next dose and confirm system is working

$pi = "192.168.88.55:8080"
$count = 0
$maxChecks = 20  # 10 minutes

Write-Host "`n=== pH Recovery Monitor ===" -ForegroundColor Cyan
Write-Host "Watching for next auto dose (checking every 30s for 10min)...`n" -ForegroundColor Yellow

while ($count -lt $maxChecks) {
    $count++
    $now = Get-Date -Format "HH:mm:ss"
    
    try {
        # Get current status
        $status = curl -s "http://$pi/api/ph/status" | ConvertFrom-Json
        $ph = $status.ph
        $cooldown = $status.remaining_cooldown_s
        $holding = $status.auto.holding_reason
        $learned = $status.auto.learned_ml_per_pH
        
        # Get recent doses (last entry)
        $recent = $status.recent | Select-Object -First 1
        
        Write-Host "[$now] pH=$ph | Cooldown=${cooldown}s | Holding=$holding | Learned=${learned}ml/pH" -ForegroundColor Gray
        
        # Check if new dose appeared (compare timestamp)
        if ($recent -and $recent.ts_utc) {
            $doseTime = [DateTime]::Parse($recent.ts_utc)
            $ageSeconds = ([DateTime]::UtcNow - $doseTime).TotalSeconds
            
            if ($ageSeconds -lt 60) {
                Write-Host "`n✓ NEW DOSE DETECTED!" -ForegroundColor Green
                Write-Host "  Time: $($recent.ts_utc)" -ForegroundColor Green
                Write-Host "  Volume: $($recent.volume_ml) ml" -ForegroundColor Green
                Write-Host "  Pre-pH: $($recent.pre_ph)" -ForegroundColor Green
                Write-Host "  Reason: $($recent.reason)" -ForegroundColor Green
                Write-Host "`nSystem is dosing again. Monitor UI for pH rise.`n" -ForegroundColor Cyan
                break
            }
        }
        
    } catch {
        Write-Host "[$now] Error: $_" -ForegroundColor Red
    }
    
    if ($count -lt $maxChecks) {
        Start-Sleep -Seconds 30
    }
}

if ($count -eq $maxChecks) {
    Write-Host "`n⚠ No new dose detected after 10 minutes" -ForegroundColor Yellow
    Write-Host "Check /api/ph/auto/debug for holding reason`n" -ForegroundColor Yellow
}
