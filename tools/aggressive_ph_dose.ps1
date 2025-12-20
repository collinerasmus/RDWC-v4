param(
    [string]$ServerUrl = "http://127.0.0.1:8080",
    [double]$TargetMl = 5.0,
    [int]$StabilizeWaitSeconds = 360
)

function Invoke-Api {
    param(
        [ValidateSet('GET','POST')][string]$Method,
        [string]$Path,
        [object]$Body = $null
    )
    $uri = "$ServerUrl$Path"
    try {
        if ($Method -eq 'GET') {
            return Invoke-RestMethod -Method Get -Uri $uri -Headers @{ 'Accept' = 'application/json' } -TimeoutSec 60
        } else {
            $json = if ($Body) { ConvertTo-Json $Body -Depth 6 } else { '{}' }
            return Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $json -TimeoutSec 60
        }
    } catch {
        Write-Error "API call failed: $Method $uri - $_"
        throw
    }
}

Write-Host "Fetching settings and pH status..."
$settings = Invoke-Api -Method 'GET' -Path '/api/settings/export'
$phStatusBefore = Invoke-Api -Method 'GET' -Path '/api/ph/status'
$prePh = $phStatusBefore.ph

# Parse pump rate and max duration
$rateStr = $settings.'dosing.ph_up_ml_per_sec'
$maxMsStr = $settings.'dosing.ph_up_max_ms'
if (-not $rateStr) { throw "Missing dosing.ph_up_ml_per_sec in settings/export" }
$rate = [double]$rateStr
$msToDose = [int][math]::Round(($TargetMl / [math]::Max(0.0001, $rate)) * 1000.0)
$maxMs = if ($maxMsStr) { [int]$maxMsStr } else { 5000 }

Write-Host "Computed $msToDose ms for $TargetMl ml at rate $rate ml/s (current max_ms=$maxMs)"

if ($msToDose -gt $maxMs) {
    $newMax = $msToDose + 500
    Write-Host "Increasing dosing.ph_up_max_ms to $newMax via settings/import..."
    $importRes = Invoke-Api -Method 'POST' -Path '/api/settings/import' -Body @{ 'dosing.ph_up_max_ms' = "$newMax" }
    if (-not $importRes.ok) { throw "settings/import failed: $($importRes | ConvertTo-Json -Depth 6)" }
    Write-Host "Updated. Proceeding to dose."
}

$body = @{ ms = $msToDose; reason = "manual_aggressive_${TargetMl}ml" }
Write-Host "Posting dose: $($body | ConvertTo-Json -Compress)"
$doseRes = Invoke-Api -Method 'POST' -Path '/api/ph/dose' -Body $body
if ($doseRes.http_status -and (-not $doseRes.ok)) {
    throw "Dose blocked: $($doseRes | ConvertTo-Json -Depth 6)"
}
Write-Host "Dose accepted: rowid=$($doseRes.rowid), duration_ms=$($doseRes.duration_ms), clamped_ms=$($doseRes.clamped_ms)"

Write-Host "Waiting $StabilizeWaitSeconds s for stabilization..."
Start-Sleep -Seconds $StabilizeWaitSeconds

$phStatusAfter = Invoke-Api -Method 'GET' -Path '/api/ph/status'
$postPh = $phStatusAfter.ph
$delta = if ($prePh -and $postPh) { [math]::Round(($postPh - $prePh), 4) } else { 0 }

Write-Host "Pre pH=$prePh, Post pH=$postPh, ΔpH=$delta"

# Output concise JSON summary for acceptance criteria
$summary = [ordered]@{
    ok = $true
    target_ml = $TargetMl
    ms = $msToDose
    pre_ph = $prePh
    post_ph = $postPh
    delta_ph = $delta
    settings = [ordered]@{
        ph_up_ml_per_sec = $rate
        ph_up_max_ms = if ($settings.'dosing.ph_up_max_ms') { [int]$settings.'dosing.ph_up_max_ms' } else { $maxMs }
    }
}
$summary | ConvertTo-Json -Depth 6
