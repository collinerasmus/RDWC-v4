param(
  [string]$PiHost = $env:PI_HOST,
  [string]$PiUser = $env:PI_USER
)

if (-not $PiHost) { Write-Error "PI_HOST not set. Pass -PiHost or set env."; exit 1 }
if (-not $PiUser) { $PiUser = "pi" }

$Target = "$PiUser@$PiHost"
Write-Host "Refreshing RDWC-v4 API + Sensors on $Target..." -ForegroundColor Cyan

$cmd = @(
  'set -e',
  'cd ~/RDWC-v4',
  'echo REMOTE git_fetch',
  'git fetch origin',
  'echo REMOTE git_reset',
  'git reset --hard origin/main',
  'echo REMOTE clear_calib_lock',
  'sudo rm -f /tmp/rdwc_calib.lock || true',
  'echo REMOTE restart_api',
  'sudo systemctl restart rdwc.service',  # FastAPI app (serves index.html)
  'echo REMOTE restart_poller',
  'sudo systemctl restart rdwc-sensors.service',
  'sleep 2',
  'echo REMOTE api_status_head',
  'sudo systemctl status rdwc.service --no-pager -l | head -n 20',
  'echo REMOTE sensors_status_head',
  'sudo systemctl status rdwc-sensors.service --no-pager -l | head -n 20',
  'echo REMOTE recent_api_logs',
  'sudo journalctl -u rdwc.service -n 40 --no-pager',
  'echo REMOTE recent_sensors_logs',
  'sudo journalctl -u rdwc-sensors.service -n 40 --no-pager'
) -join ' ; '

ssh $Target $cmd

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Done. Verify BUILD_COMMIT in / output matches local HEAD." -ForegroundColor Green
