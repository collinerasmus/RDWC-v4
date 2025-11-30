<#
Benchmark pH Automation State
Captures controllers status, health, settings subset, dose events, and trends into timestamped folder.

Usage:
  pwsh ./tools/benchmark_ph.ps1 -Host 192.168.88.49 -OutDir benchmarks

Parameters:
  -Host    Pi hostname/IP
  -Port    API port (default 8080)
  -OutDir  Root output directory (default 'benchmarks')
#>
param(
  [string]$Host,
  [int]$Port = 8080,
  [string]$OutDir = "benchmarks"
)

if (-not $Host) {
  Write-Error "-Host is required (Pi hostname/IP)"; exit 1
}

$base = "http://$Host:$Port"
$ts = (Get-Date).ToString('yyyyMMdd-HHmmss')
$targetDir = Join-Path $OutDir "ph-$ts"
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

function SaveJson($url, $file, $depth=6) {
  try {
    $resp = Invoke-RestMethod -Uri $url -TimeoutSec 10
    $resp | ConvertTo-Json -Depth $depth | Out-File -FilePath (Join-Path $targetDir $file) -Encoding UTF8
    Write-Host "Saved $file" -ForegroundColor Green
  }
  catch {
    Write-Warning "Failed $url : $($_.Exception.Message)"
  }
}

Write-Host "[Benchmark] Capturing pH automation snapshot to $targetDir" -ForegroundColor Cyan

# Core endpoints
SaveJson "$base/api/version" "version.json" 4
SaveJson "$base/api/controllers/status" "controllers_status.json" 6
SaveJson "$base/api/health" "health.json" 4
SaveJson "$base/api/sensors/status" "sensors_status.json" 4

# Settings export (full + subset)
try {
  $settings = Invoke-RestMethod "$base/api/settings/export" -TimeoutSec 10
  $settings | ConvertTo-Json -Depth 6 | Out-File (Join-Path $targetDir 'settings_full.json') -Encoding UTF8
  $subset = [PSCustomObject]@{
    targets_ph_low = $settings.'targets.ph_low'
    targets_ph_high = $settings.'targets.ph_high'
    dosing_ph_up_initial_ml = $settings.'dosing.ph_up_initial_ml'
    dosing_ph_min_interval_s = $settings.'dosing.ph_min_interval_s'
    dosing_ph_max_predicted_delta_ph = $settings.'dosing.ph_max_predicted_delta_ph'
    dosing_ph_stabilization_window_s = $settings.'dosing.ph_stabilization_window_s'
    dosing_ph_stabilization_delta = $settings.'dosing.ph_stabilization_delta'
    dosing_ph_stabilization_samples = $settings.'dosing.ph_stabilization_samples'
  }
  $subset | ConvertTo-Json -Depth 4 | Out-File (Join-Path $targetDir 'settings_ph_subset.json') -Encoding UTF8
  Write-Host "Saved settings subset" -ForegroundColor Green
} catch {
  Write-Warning "Failed to export settings: $($_.Exception.Message)"
}

# Dose events (last 6 hours) & trends
SaveJson "$base/api/dose/recent?hours=6" "doses_6h.json" 6
SaveJson "$base/api/trends?gran=300&max=500" "trends.json" 6

Write-Host "[Benchmark] Complete." -ForegroundColor Cyan
