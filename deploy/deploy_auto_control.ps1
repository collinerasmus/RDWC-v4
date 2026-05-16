# Deploy Unified Auto-Enable System
# Run from: C:\Users\USER-PC\OneDrive\Documents\GitHub\RDWC-v4

Write-Host "=== Deploying Unified Auto-Enable System ===" -ForegroundColor Cyan
Write-Host ""

# Check git status
Write-Host "1. Checking git status..." -ForegroundColor Yellow
git status --short

Write-Host ""
Write-Host "2. Adding files..." -ForegroundColor Yellow
git add app/auto_control.py
git add app/main.py  
git add app/ph_control.py
git add app/ec_control.py
git add MODE_REFACTOR_STATUS.md

Write-Host ""
Write-Host "3. Committing..." -ForegroundColor Yellow
git commit -m "feat: unified auto-enable system (backend)

- Created app/auto_control.py: Single source of truth for automation
  - controls.global_auto (master switch)
  - controls.ph_auto, controls.ec_auto, controls.chiller_auto (per-controller)
  - should_automate(controller) = global AND controller
  - migrate_from_legacy() to port old settings

- Added new API endpoints (app/main.py):
  - GET /api/auto/status
  - POST /api/auto/global {enabled: true/false}
  - POST /api/auto/{controller} {enabled: true/false}

- Updated pH controller (app/ph_control.py):
  - Replaced ph.auto_enabled with should_automate('ph')
  - Changed holding_reason='held' to 'auto_disabled'

- Updated EC controller (app/ec_control.py):
  - Replaced ec.auto_enabled with should_automate('ec')
  - Updated all auto checks in status, preview, control loop, debug
  - Deprecated old /api/ec/auto endpoints (kept for compatibility)

- Added migration hook:
  - Runs on startup to port old settings
  - Safe defaults (all false) for new installations

Replaces fragmented mode systems:
- unified_mode.py MODE_AUTO/MANUAL/MAINTENANCE
- Scattered ph.auto_enabled, ec.auto_enabled settings
- controller.{name}.held hold states

Benefits:
- Clear control: Global + per-controller enable
- Simple logic: automation runs = global AND controller
- Better UX: No confusing mode hierarchies
- Flexible: Disable individual controllers while others run

Frontend changes pending (documented in MODE_REFACTOR_STATUS.md)"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Commit failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "4. Pushing to GitHub..." -ForegroundColor Yellow
git push

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Push failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "5. Deploying to Pi..." -ForegroundColor Yellow
Write-Host "   SSH: pi@rdwc.local" -ForegroundColor Gray

ssh pi@rdwc.local @"
cd ~/rdwc
echo '=== Pulling latest code ==='
git pull
echo ''
echo '=== Restarting API service ==='
sudo systemctl restart rdwc
echo ''
echo '=== Checking service status ==='
sleep 2
sudo systemctl status rdwc --no-pager -l
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Deployment failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "6. Testing new endpoints..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

Write-Host "   Testing /api/auto/status..." -ForegroundColor Gray
$status = Invoke-RestMethod -Uri "http://rdwc.local:8080/api/auto/status" -Method Get
Write-Host "   Response:" -ForegroundColor Gray
$status | ConvertTo-Json -Depth 3

Write-Host ""
Write-Host "   Testing /api/ph/status (should use new system)..." -ForegroundColor Gray
$ph = Invoke-RestMethod -Uri "http://rdwc.local:8080/api/ph/status" -Method Get
Write-Host "   pH auto enabled: $($ph.auto.enabled)" -ForegroundColor Gray
Write-Host "   pH holding reason: $($ph.auto.holding_reason)" -ForegroundColor Gray

Write-Host ""
Write-Host "   Testing /api/ec/status (should use new system)..." -ForegroundColor Gray
$ec = Invoke-RestMethod -Uri "http://rdwc.local:8080/api/ec/status" -Method Get
Write-Host "   EC auto enabled: $($ec.auto.enabled)" -ForegroundColor Gray
Write-Host "   EC holding reason: $($ec.auto.holding_reason)" -ForegroundColor Gray

Write-Host ""
Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Check HMI - controllers should respect new auto state"
Write-Host "  2. Review MODE_REFACTOR_STATUS.md for frontend changes"
Write-Host "  3. Test global auto toggle: POST /api/auto/global {enabled: true}"
Write-Host "  4. Test pH auto toggle: POST /api/auto/ph {enabled: true}"
Write-Host ""
Write-Host "Old endpoints still work (deprecated):" -ForegroundColor Yellow
Write-Host "  - /api/controller/ph/hold (now redundant)"
Write-Host "  - /api/ec/auto (redirects to new system)"
Write-Host ""
