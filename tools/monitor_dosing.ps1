# PowerShell helper to monitor dosing events in real time
param(
    [int]$IntervalSeconds = 5
)

Write-Host "Monitoring dosing events every $IntervalSeconds seconds. CTRL+C to stop." -ForegroundColor Cyan

function Get-DosingEvents {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8080/history?limit=20" -TimeoutSec 4
        if ($resp -and $resp.readings) {
            $doses = $resp.readings | Where-Object { $_.event -like 'dose*' }
            foreach ($d in $doses) {
                [PSCustomObject]@{
                    ts = $d.ts
                    event = $d.event
                    ml = $d.ml
                    ph = $d.ph
                    ec_mscm = $d.ec_mscm
                    temp_c = $d.temperature_c
                }
            }
        }
    } catch {
        Write-Warning "Failed to fetch dosing events: $_"
    }
}

while ($true) {
    Get-DosingEvents | Format-Table -AutoSize
    Start-Sleep -Seconds $IntervalSeconds
}
