param(
  [string]$PiHost = "192.168.88.49",
  [int]$DelayMinutes = 20
)

function Run-Checks {
  param([string]$Label)
  Write-Host "=== SOAK CHECK: $Label ===" -ForegroundColor Cyan
  $ts = Get-Date -Format o
  Write-Host "Timestamp: $ts" -ForegroundColor DarkGray

  Write-Host "[1/3] /health/db" -ForegroundColor Yellow
  ssh pi@$PiHost "curl -s http://127.0.0.1:8080/health/db" | python -m json.tool

  Write-Host "[2/3] hourly (last 3h)" -ForegroundColor Yellow
  ssh pi@$PiHost "curl -s 'http://127.0.0.1:8080/debug/readings/hourly?hours=3'" | python -m json.tool

  Write-Host "[3/3] gaps (last 1h, >180s)" -ForegroundColor Yellow
  ssh pi@$PiHost "curl -s 'http://127.0.0.1:8080/debug/readings/gaps?hours=1&min_gap_sec=180'" | python -m json.tool

  Write-Host "=== END SOAK CHECK: $Label ===`n" -ForegroundColor Cyan
}

Run-Checks -Label "now"

Write-Host "Sleeping for $DelayMinutes minutes before next run..." -ForegroundColor DarkYellow
Start-Sleep -Seconds ($DelayMinutes * 60)

Run-Checks -Label "after ${DelayMinutes}m"