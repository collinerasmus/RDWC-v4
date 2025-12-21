param(
  [string]$Host = "192.168.88.55",
  [string]$User = "pi",
  [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
Write-Host "[Deploy] Target: $User@$Host Branch: $Branch"

# Build remote command: pull latest + restart services + version check
$remoteCmd = @(
  'cd ~/RDWC-v4',
  "git fetch origin $Branch",
  "git reset --hard origin/$Branch",
  'sudo systemctl restart rdwc',
  'sudo systemctl restart rdwc-sensors',
  'sleep 2',
  'systemctl is-active rdwc',
  'systemctl is-active rdwc-sensors',
  'curl -s http://localhost:8080/api/version || true'
) -join '; '

Write-Host "[Deploy] Executing remote commands..." -ForegroundColor Cyan

# Requires OpenSSH client installed on Windows
$sshCmd = "ssh $User@$Host \"$remoteCmd\""
Write-Host "[Deploy] ssh command: $sshCmd"

try {
  $proc = Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-Command", $sshCmd -NoNewWindow -PassThru -Wait
  if ($proc.ExitCode -ne 0) {
    throw "Remote deploy failed with exit code $($proc.ExitCode)"
  }
  Write-Host "[Deploy] ✓ Deployment complete" -ForegroundColor Green
  Write-Host "[Deploy] Next: Hard-refresh HMI (Ctrl+Shift+R) to load new JS"
}
catch {
  Write-Error "[Deploy] Error: $_"
  Write-Host "Tip: Ensure SSH access to the Pi and correct user/password or keys are set."
}
