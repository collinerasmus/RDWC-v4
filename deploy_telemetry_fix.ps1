# Telemetry Stabilization Hotfix Deployment Script
# Deploys fix/telemetry-stabilization branch to Pi and verifies

$PI_HOST = "192.168.88.49"
$PI_USER = "pi"
$PI_PASS = "DrowPas$"

Write-Host "=== TELEMETRY STABILIZATION HOTFIX DEPLOYMENT ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Stop service
Write-Host "[1/6] Stopping rdwc.service..." -ForegroundColor Yellow
ssh ${PI_USER}@${PI_HOST} "echo ${PI_PASS} | sudo -S systemctl stop rdwc.service"
Start-Sleep -Seconds 2

# Step 2: Pull latest code
Write-Host "[2/6] Pulling fix/telemetry-stabilization branch..." -ForegroundColor Yellow
ssh ${PI_USER}@${PI_HOST} "cd RDWC-v4 && git fetch origin && git checkout fix/telemetry-stabilization && git pull origin fix/telemetry-stabilization"

# Step 3: Restart service
Write-Host "[3/6] Starting rdwc.service..." -ForegroundColor Yellow
ssh ${PI_USER}@${PI_HOST} "echo ${PI_PASS} | sudo -S systemctl start rdwc.service"
Start-Sleep -Seconds 5

# Step 4: Check service health
Write-Host "[4/6] Checking service status..." -ForegroundColor Yellow
$service_status = ssh ${PI_USER}@${PI_HOST} "systemctl is-active rdwc.service"
Write-Host "Service status: $service_status" -ForegroundColor $(if ($service_status -eq "active") { "Green" } else { "Red" })

# Step 5: Test new /health/db endpoint
Write-Host "[5/6] Testing /health/db endpoint..." -ForegroundColor Yellow
Start-Sleep -Seconds 5  # Give sensors time to collect first reading
$health_db = ssh ${PI_USER}@${PI_HOST} "curl -s http://127.0.0.1:8080/health/db"
Write-Host $health_db
$health_obj = $health_db | ConvertFrom-Json
if ($health_obj.ok) {
    Write-Host "✅ /health/db is healthy! Age: $($health_obj.age_seconds)s, Recent rows: $($health_obj.recent_rows_5min)" -ForegroundColor Green
} else {
    Write-Host "⚠️  /health/db not yet healthy (expected initially)" -ForegroundColor Yellow
}

# Step 6: Test debug endpoints
Write-Host "[6/6] Testing new debug endpoints..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Hourly counts (last 48h):" -ForegroundColor Cyan
ssh ${PI_USER}@${PI_HOST} "curl -s http://127.0.0.1:8080/debug/readings/hourly?hours=48" | ConvertFrom-Json | ConvertTo-Json -Depth 10

Write-Host ""
Write-Host "Gaps detected (last 72h, >180s):" -ForegroundColor Cyan
ssh ${PI_USER}@${PI_HOST} "curl -s http://127.0.0.1:8080/debug/readings/gaps?hours=72&min_gap_sec=180" | ConvertFrom-Json | ConvertTo-Json -Depth 10

Write-Host ""
Write-Host "=== DEPLOYMENT COMPLETE ===" -ForegroundColor Green
Write-Host ""
Write-Host "VERIFICATION STEPS:" -ForegroundColor Yellow
Write-Host "1. Wait 30-60 minutes for data to accumulate"
Write-Host "2. Re-run gap detection: curl http://192.168.88.49:8080/debug/readings/gaps?hours=1&min_gap_sec=30"
Write-Host "3. Check hourly counts are steady: curl http://192.168.88.49:8080/debug/readings/hourly?hours=2"
Write-Host "4. Verify /health/db stays healthy: curl http://192.168.88.49:8080/health/db"
Write-Host "5. Check logs for 'reading_ok': journalctl -u rdwc.service -n 50 --no-pager"
Write-Host ""
Write-Host "Expected outcome: No gaps, steady ~360 rows/hour (10s polling)"
