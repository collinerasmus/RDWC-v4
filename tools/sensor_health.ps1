param(
  [string]$Host = $env:PI_HOST
)

if (-not $Host) { Write-Error "PI_HOST not set. Pass -Host or set env."; exit 1 }

$base = "http://$Host:8080"
Write-Host "Checking $base/api/sensors ..." -ForegroundColor Cyan

try {
  $resp = Invoke-RestMethod -Uri "$base/api/sensors" -Method GET -TimeoutSec 8
} catch {
  Write-Error "Request failed: $_"; exit 2
}

if (-not $resp.ts) { Write-Error "No ts in response"; exit 3 }

# Compute age seconds if server provides age; otherwise derive from ts if epoch
if ($resp.age_seconds) {
  $age = [int]$resp.age_seconds
} else {
  try {
    $epoch = [double]$resp.ts
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $age = [int]($now - $epoch)
  } catch { $age = -1 }
}

$status = [ordered]@{
  online = $resp.online
  age_seconds = $age
  temperature_c = $resp.temperature_c
  ph = $resp.ph
  ec_mscm = $resp.ec_mscm
  errors = $resp.errors
}

$status | ConvertTo-Json -Depth 3 | Write-Output

if ($age -ge 0 -and $age -gt 60) { exit 10 }
