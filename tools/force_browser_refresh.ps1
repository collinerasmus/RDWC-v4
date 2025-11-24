# Force Browser Cache Refresh on HMI
# This ensures the latest JavaScript is loaded

$piIP = "192.168.88.49"

Write-Host "=== Force Browser Cache Refresh ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "The JavaScript files have changed but your browser is loading old cached versions."
Write-Host ""
Write-Host "On your HMI laptop (192.168.88.33), do this in Chrome:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Open DevTools: Press F12" -ForegroundColor Green
Write-Host "2. Right-click the Refresh button (next to address bar)" -ForegroundColor Green
Write-Host "3. Select 'Empty Cache and Hard Reload'" -ForegroundColor Green
Write-Host ""
Write-Host "OR use keyboard shortcut:" -ForegroundColor Yellow
Write-Host "  Ctrl + Shift + R  (Windows/ChromeOS)" -ForegroundColor Green
Write-Host "  Cmd + Shift + R   (Mac)" -ForegroundColor Green
Write-Host ""
Write-Host "This will force Chrome to re-download all JavaScript files." -ForegroundColor Cyan
Write-Host ""
Write-Host "After refresh, check browser console (F12 → Console tab) for:" -ForegroundColor Yellow
Write-Host "  - Should see: [System] Notifying controllers with sync functions..." -ForegroundColor Green
Write-Host "  - Should see: [System] - Other controllers will self-update within 5 seconds" -ForegroundColor Green
Write-Host ""

# Touch a file on Pi to change timestamp (cache busting)
Write-Host "Updating asset version on Pi to force cache refresh..." -ForegroundColor Cyan
try {
    # This would require SSH access, so just show the command
    Write-Host ""
    Write-Host "If hard refresh doesn't work, SSH to Pi and run:" -ForegroundColor Yellow
    Write-Host "  ssh pi@$piIP" -ForegroundColor Green
    Write-Host "  cd ~/RDWC-v4" -ForegroundColor Green
    Write-Host "  touch app/static/js/relays_v2.js" -ForegroundColor Green
    Write-Host "  sudo systemctl restart rdwc" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "Note: You'll need to SSH manually" -ForegroundColor Yellow
}

Write-Host "After doing the hard refresh, try:" -ForegroundColor Cyan
Write-Host "1. Click Manual button in header" -ForegroundColor Green
Write-Host "2. Wait 5 seconds" -ForegroundColor Green
Write-Host "3. Check if Hold buttons activate in pH/EC/Circulation tabs" -ForegroundColor Green
Write-Host ""
