param(
  [string]$PiHost = $env:PI_HOST,
  [string]$PiUser = $env:PI_USER
)

if (-not $PiHost) { Write-Error "PI_HOST not set. Pass -PiHost or set env."; exit 1 }
if (-not $PiUser) { $PiUser = "pi" }

$Target = "$PiUser@$PiHost"

Write-Host "Refreshing RDWC-v4 on $Target..." -ForegroundColor Cyan

$cmd = @(
  'set -euxo pipefail',
  'cd ~/RDWC-v4',
  'echo "[remote] git fetch"',
  'git fetch origin',
  'echo "[remote] git reset"',
  'git reset --hard origin/main',
  'echo "[remote] clearing calib lock"',
  'sudo rm -f /tmp/rdwc_calib.lock || true',
  'echo "[remote] restart rdwc.service"',
  'sudo systemctl restart rdwc.service',
  'echo "[remote] restart rdwc-sensors.service"',
  'sudo systemctl restart rdwc-sensors.service',
  'sleep 2',
  'echo "[remote] rdwc-sensors status (first lines)"',
  'sudo systemctl status rdwc-sensors.service --no-pager -l | sed -n "1,20p"',
  'echo "[remote] recent logs"',
  'sudo journalctl -u rdwc-sensors.service -n 40 --no-pager'
) -join ' ; '

ssh $Target $cmd

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Review logs above for errors." -ForegroundColor Green
