param(
  [string]$Base = 'http://192.168.88.49:8080'
)
$ErrorActionPreference = 'SilentlyContinue'
function J($o){ if($o){ $o | ConvertTo-Json -Depth 8 } else { 'null' } }
'--- before ---'
$s0 = Invoke-RestMethod -Uri ($Base + '/api/sensors') -TimeoutSec 8 -ErrorAction SilentlyContinue
J $s0
try { Invoke-RestMethod -Uri ($Base + '/read_now') -Method Post -TimeoutSec 10 -ErrorAction Stop | Out-Null } catch { 'read_now failed' }
Start-Sleep -Seconds 3
'--- after read_now ---'
$s1 = Invoke-RestMethod -Uri ($Base + '/api/sensors') -TimeoutSec 8 -ErrorAction SilentlyContinue
J $s1
'--- diag once ---'
$s2 = Invoke-RestMethod -Uri ($Base + '/diag/sensors/once') -TimeoutSec 20 -ErrorAction SilentlyContinue
J $s2
Start-Sleep -Seconds 3
'--- after diag ---'
$s3 = Invoke-RestMethod -Uri ($Base + '/api/sensors') -TimeoutSec 8 -ErrorAction SilentlyContinue
J $s3
