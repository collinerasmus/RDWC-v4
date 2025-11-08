param(
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [ValidateSet(4,7,10)][int]$ExpectedPhBuffer = 7,
  [switch]$DoEcCalibration,
  [double]$EcLowUsCm = 1413,
  [switch]$DoDoseCalibration
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Out-Obj($o){ $o | ConvertTo-Json -Depth 12 }
function JPost($path, $body=$null){
  $uri = "$BaseUrl$path"
  if($null -ne $body){ return Invoke-RestMethod -Method Post -Uri $uri -Body ($body | ConvertTo-Json) -ContentType 'application/json' }
  else { return Invoke-RestMethod -Method Post -Uri $uri }
}
function JGet($path){ Invoke-RestMethod -Method Get -Uri "$BaseUrl$path" }
function SleepMs($ms){ Start-Sleep -Milliseconds $ms }

Write-Host "===== A) Revalidate hardware online =====" -ForegroundColor Cyan
$relays = JGet "/api/relays/status"
Write-Host "Relays status:"; Out-Obj $relays
if($relays.estop){ Write-Warning "E-STOP is active. Disable it from UI or POST /api/relays/estop/toggle to proceed with actuation tests." }

$poller = JGet "/api/sensors/status"
Write-Host "Sensor poller status:"; Out-Obj $poller

$null = JGet "/diag/sensors/leds?on=1"
$fix = JPost "/fix_ezo"
Write-Host "fix_ezo result:"; Out-Obj $fix

# Helper to test pH single read and status
function Test-PhSingle {
  $r = JGet "/calib/ph/read"; Write-Host "pH single:"; Out-Obj $r
  $s = JGet "/calib/ph/status"; Write-Host "pH status:"; Out-Obj $s
  return @{ read = $r; status = $s }
}

Write-Host "===== B) Recover pH if blank/bad =====" -ForegroundColor Cyan
$phCheck = Test-PhSingle
$phVal = [double]($phCheck.read.value)
$bad = $false
if([double]::IsNaN($phVal) -or $phVal -le 0 -or $phVal -gt 14){ $bad = $true }
$delta = [double]::PositiveInfinity
if(-not $bad -and $ExpectedPhBuffer -in 4,7,10){ $delta = [math]::Abs($phVal - $ExpectedPhBuffer) }
if($bad -or ($delta -gt 0.4)){
  Write-Warning "pH appears unhealthy (val=$phVal, expected ~$ExpectedPhBuffer). Attempting recovery."
  $hasSensorPower = $false
  if($relays.relays.ContainsKey('sensor_power')){ $hasSensorPower = $true }
  if($hasSensorPower){
    Write-Host "Power-cycling sensor rail via /api/sensors/power_cycle" -ForegroundColor Yellow
    $pc = JPost "/api/sensors/power_cycle?off_ms=3000&post_wait_ms=6000&validate=1"
    Out-Obj $pc | Out-Null
    SleepMs 2000
  } else {
    Write-Host "Flashing LEDs to wake bus" -ForegroundColor Yellow
    $null = JGet "/diag/sensors/flash?count=6&period_ms=250"
    SleepMs 2000
  }
  $fix = JPost "/fix_ezo"
  Write-Host "fix_ezo after recovery:"; Out-Obj $fix
  $phCheck = Test-PhSingle
  $phVal = [double]($phCheck.read.value)
}

Write-Host "===== C) pH stabilization =====" -ForegroundColor Cyan
$stable = JGet "/calib/ph/read_stable?timeout_s=25&delta=0.03&min_samples=4&poll_s=2"
Write-Host "pH stable result:"; Out-Obj $stable

# Simple acceptance check
$finalPh = [double]($stable.value)
$phOk = $true
if([double]::IsNaN($finalPh) -or $finalPh -le 0 -or $finalPh -gt 14){ $phOk = $false }
elseif($ExpectedPhBuffer -in 4,7,10){ if([math]::Abs($finalPh - $ExpectedPhBuffer) -gt 0.05){ $phOk = $false } }

if(-not $phOk){ Write-Warning "pH not within expected tolerance. Consider reapplying mid/low with CALIB_ENABLE=1." }

if($DoEcCalibration){
  Write-Host "===== D) EC calibration (low) =====" -ForegroundColor Cyan
  Write-Host "Ensure probe is in $EcLowUsCm µS/cm solution before proceeding." -ForegroundColor Yellow
  $null = JPost "/api/ec/cal/clear"
  SleepMs 800
  $null = JPost "/api/ec/cal/low" @{ us_cm = [double]$EcLowUsCm }
  SleepMs 800
  $ecstat = JGet "/api/ec/cal/status"; Write-Host "EC status:"; Out-Obj $ecstat
}

if($DoDoseCalibration){
  Write-Host "===== E) Dosing pumps calibration (pH Up) =====" -ForegroundColor Cyan
  $pumps = JGet "/calib/dose/pumps"; Write-Host "Current pump rates:"; Out-Obj $pumps
  Write-Host "Priming pH Up for 0.5s" -ForegroundColor Yellow
  $null = JPost "/calib/dose/prime?pump=ph_up&seconds=0.5"
  SleepMs 1500
  Write-Host "Run pH Up for 5s, measure output in cylinder." -ForegroundColor Yellow
  $null = JPost "/calib/dose/run?pump=ph_up&seconds=5"
  $ml = Read-Host "Enter measured milliliters for 5s run"
  if(-not [double]::TryParse($ml, [ref]([double]0))){ Write-Warning "Invalid ml reading, skipping commit." }
  else {
    $null = JPost "/calib/dose/commit?pump=ph_up&seconds=5&measured_ml=$ml"
    $after = JGet "/calib/dose/pumps"; Write-Host "Updated pump rates:"; Out-Obj $after
  }
}

Write-Host "===== F) Finalization =====" -ForegroundColor Cyan
# Set reservoir volume to 100L via settings import (namespaced model)
$payload = @{ "general.reservoir_liters" = "100" }
try { $r = JPost "/api/settings/import" $payload; Write-Host "Settings update:"; Out-Obj $r } catch { Write-Warning "Settings import failed: $($_.Exception.Message)" }

# Verify live sensors freshness
$sensors = JGet "/api/sensors"; Write-Host "Live sensors:"; Out-Obj $sensors

Write-Host "===== SUMMARY =====" -ForegroundColor Green
$summary = [ordered]@{
  relays_estop = $relays.estop
  poller_running = $poller.running
  ph_value = $finalPh
  ph_expected_buffer = $ExpectedPhBuffer
  ph_ok = $phOk
}
Out-Obj $summary
