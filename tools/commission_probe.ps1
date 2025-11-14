param(
  [string[]]$Bases = @('http://192.168.88.49:8080','http://192.168.88.49','http://rdwc.local:8080','http://rdwc.local')
)
$ErrorActionPreference = 'SilentlyContinue'
function Try-Health($u) {
  try { Invoke-RestMethod -Uri ($u + '/health') -TimeoutSec 4 -ErrorAction Stop } catch { $null }
}
$base = $null
foreach ($b in $Bases) { $h = Try-Health $b; if ($h) { $base = $b; break } }
if (-not $base) { Write-Host 'API not reachable on common bases'; exit 2 }
Write-Host ('Using API base: ' + $base)
function SafeGet($path, $method='GET', $body=$null) {
  try { Invoke-RestMethod -Uri ($base + $path) -Method $method -Body $body -TimeoutSec 8 -ErrorAction Stop } catch { $null }
}
$relays = SafeGet '/api/relays/status'
$sensorsStatus = SafeGet '/api/sensors/status'
$sensors = SafeGet '/api/sensors'
$chiller = SafeGet '/api/chiller/status'
$systemHealth = SafeGet '/health'
$ecCal = SafeGet '/api/ec/cal/status'
$phCal = SafeGet '/calib/ph/status'
$now = [DateTimeOffset]::UtcNow
function AgeSec($ts){
  if($null -eq $ts){ return $null }
  if($ts -is [int] -or $ts -is [long] -or $ts -is [double]){
    try { $dt = [DateTimeOffset]::FromUnixTimeSeconds([int64]$ts) } catch { return $null }
    return [int][Math]::Round(($now - $dt).TotalSeconds)
  }
  try { $dt = [DateTimeOffset]::Parse($ts) } catch { return $null }
  return [int][Math]::Round(($now - $dt).TotalSeconds)
}
$age = $null; if($sensors -and ($sensors.PSObject.Properties.Name -contains 'ts')){ $age = AgeSec $sensors.ts }
$accept = [pscustomobject]@{
  base = $base
  estop = if($relays -and ($relays.PSObject.Properties.Name -contains 'estop')){ [bool]$relays.estop } else { $null }
  sensors_online = if($sensors -and ($sensors.PSObject.Properties.Name -contains 'online')){ [bool]$sensors.online } else { $null }
  sensors_age_s = $age
  chiller_state = if($chiller -and ($chiller.PSObject.Properties.Name -contains 'state')){ $chiller.state } else { $null }
  ec_cal_status = $ecCal
  ph_cal_status = $phCal
  health = $systemHealth
}
'=== ACCEPTANCE SUMMARY ==='
$accept | ConvertTo-Json -Depth 8
'--- relays ---'
if($relays){ $relays | ConvertTo-Json -Depth 6 } else { 'null' }
'--- sensors ---'
if($sensors){ $sensors | ConvertTo-Json -Depth 6 } else { 'null' }
'--- sensors/status ---'
if($sensorsStatus){ $sensorsStatus | ConvertTo-Json -Depth 6 } else { 'null' }
'--- chiller ---'
if($chiller){ $chiller | ConvertTo-Json -Depth 6 } else { 'null' }
'--- health ---'
if($systemHealth){ $systemHealth | ConvertTo-Json -Depth 6 } else { 'null' }
exit 0
