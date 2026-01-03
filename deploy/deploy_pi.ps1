param(
  [string]$PiHost = "192.168.88.55",
  [string]$User = "pi",
  [string]$Branch = "main",
  [string]$KeyPath = ""
)

$ErrorActionPreference = "Stop"
Write-Host "[Deploy] Target: $User@$PiHost Branch: $Branch" -ForegroundColor Cyan

# Resolve SSH key automatically if not provided
function Resolve-KeyPath {
  param([string]$Provided)
  if ($Provided -and (Test-Path -LiteralPath $Provided)) { return (Resolve-Path -LiteralPath $Provided).Path }
  $userHome = $env:USERPROFILE
  $candidates = @(
    "$userHome\\.ssh\\id_ed25519",
    "$userHome\\.ssh\\id_rsa",
    "C:\\Users\\$($env:USERNAME)\\.ssh\\id_ed25519",
    "C:\\Users\\$($env:USERNAME)\\.ssh\\id_rsa"
  )
  foreach ($c in $candidates) { if (Test-Path -LiteralPath $c) { return (Resolve-Path -LiteralPath $c).Path } }
  return ""
}

$resolvedKey = Resolve-KeyPath -Provided $KeyPath
if (-not $resolvedKey) {
  Write-Error "[Deploy] No SSH key found. Provide -KeyPath or place id_ed25519/id_rsa in %USERPROFILE%\.ssh"
  exit 1
}
Write-Host "[Deploy] Using SSH key: $resolvedKey" -ForegroundColor Yellow

# Build remote command: pull latest + restart services + version check
$remoteCmd = @(
  'set -e',
  'cd ~/RDWC-v4',
  "git fetch origin $Branch",
  "git reset --hard origin/$Branch",
  'sudo systemctl restart rdwc',
  'sudo systemctl restart rdwc-sensors',
  'sleep 2',
  'systemctl is-active rdwc || true',
  'systemctl is-active rdwc-sensors || true',
  'curl -s http://localhost:8080/api/version || true'
) -join '; '

Write-Host "[Deploy] Executing remote commands via SSH..." -ForegroundColor Cyan

# Use OpenSSH client on Windows; no password prompts (BatchMode)
$sshArgs = @(
  '-i', "`"$resolvedKey`"",
  '-o', 'BatchMode=yes',
  '-o', 'StrictHostKeyChecking=no',
  "$User@$PiHost",
  "`"$remoteCmd`""
)

& ssh @sshArgs
$code = $LASTEXITCODE
if ($code -ne 0) {
  Write-Error "[Deploy] Remote deploy failed with exit code $code"
  exit $code
}

Write-Host "[Deploy] ✓ Deployment complete" -ForegroundColor Green

# Quick remote API version check from Windows (optional)
try {
  $ver = Invoke-RestMethod -Method Get -Uri "http://$PiHost:8080/api/version" -TimeoutSec 5
  Write-Host "[Deploy] API version: $($ver.version)" -ForegroundColor Green
} catch {
  Write-Warning "[Deploy] Could not fetch API version from Windows. HMI should still load; hard-refresh (Ctrl+Shift+R)."
}

Write-Host "[Deploy] Next: Hard-refresh HMI to load new JS (Ctrl+Shift+R)" -ForegroundColor Cyan
