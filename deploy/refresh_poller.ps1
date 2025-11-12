param(
    [string]$Host = $env:PI_HOST,
    [string]$User = $env:PI_USER
)

if (-not $Host) { Write-Error "PI_HOST not set. Pass -Host or set env."; exit 1 }
if (-not $User) { $User = "pi" }

$Target = "$User@$Host"

Write-Host "Refreshing RDWC-v4 on $Target..." -ForegroundColor Cyan

$cmd = @(
  'set -e',
  'cd ~/RDWC-v4',
  'git fetch origin',
  'git reset --hard origin/main',
  'sudo rm -f /tmp/rdwc_calib.lock',
  'sudo systemctl restart rdwc.service',
  'sudo systemctl restart rdwc-sensors.service',
  'sleep 2',
  'sudo systemctl status rdwc-sensors.service --no-pager -l | sed -n "1,20p"',
  'sudo journalctl -u rdwc-sensors.service -n 40 --no-pager'
) -join ' && '

ssh $Target $cmd

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Review logs above for errors." -ForegroundColor Green
