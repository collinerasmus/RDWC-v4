# RDWC-v4 Production Demo Script
param(
    [string]$PiHost = "pi-rdwc",
    [string]$User = "pi"
)

Write-Host "🌿 RDWC-v4 Production System Demo" -ForegroundColor Green
Write-Host "================================="

$baseUrl = "http://$PiHost:8000"
$sshCmd = "ssh $User@$PiHost"

Write-Host "`n📊 System Status Check..."
try {
    $status = Invoke-Expression "$sshCmd 'curl -s $baseUrl/status'" | ConvertFrom-Json
    Write-Host "Environment: $($status.env)" -ForegroundColor Cyan
    Write-Host "Sample Interval: $($status.sample_interval_sec)s" -ForegroundColor Cyan
    Write-Host "Current Readings:" -ForegroundColor Yellow
    Write-Host "  Temperature: $($status.data.temperature_c)°C"
    Write-Host "  pH: $($status.data.pH)"
    Write-Host "  EC: $($status.data.ec) µS/cm"
} catch {
    Write-Warning "Status check failed: $_"
}

Write-Host "`n🔍 I2C Diagnostics..."
try {
    $diag = Invoke-Expression "$sshCmd 'curl -s $baseUrl/diag'" | ConvertFrom-Json
    Write-Host "Force Mock Sensors: $($diag.force_mock)" -ForegroundColor Cyan
    Write-Host "I2C Devices Found:" -ForegroundColor Yellow
    foreach ($device in $diag.i2c) {
        Write-Host "  $device" -ForegroundColor White
    }
    Write-Host "Real-time Probe Results:" -ForegroundColor Yellow
    Write-Host "  pH: $($diag.now.pH)"
    Write-Host "  EC: $($diag.now.ec) µS/cm"
    Write-Host "  Temp: $($diag.now.temperature_c)°C"
} catch {
    Write-Warning "Diagnostics failed: $_"
}

Write-Host "`n🧪 Testing Atlas Sensor Commands..."
$atlasTests = @(
    @{addr="0x63"; cmd="I"; desc="pH Sensor Info"},
    @{addr="0x64"; cmd="I"; desc="EC Sensor Info"},
    @{addr="0x66"; cmd="I"; desc="RTD Sensor Info"}
)

foreach ($test in $atlasTests) {
    try {
        Write-Host "Testing $($test.desc)..." -ForegroundColor Cyan
        $result = Invoke-Expression "$sshCmd 'curl -s -X POST `"$baseUrl/atlas?addr=$($test.addr)`&cmd=$($test.cmd)`"'"
        Write-Host "  Response: $result" -ForegroundColor White
    } catch {
        Write-Warning "Atlas test failed for $($test.addr): $_"
    }
    Start-Sleep -Seconds 1
}

Write-Host "`n🔄 Testing Relay Controls..."
$relayTests = @("main_pump", "chiller_pump")
foreach ($relay in $relayTests) {
    try {
        Write-Host "Activating $relay..." -ForegroundColor Cyan
        Invoke-Expression "$sshCmd 'curl -s -X POST $baseUrl/actuate/$relay/1'" | Out-Null
        Start-Sleep -Seconds 2
        Write-Host "  ✅ $relay activated" -ForegroundColor Green
    } catch {
        Write-Warning "Relay test failed for $relay"
    }
}

Write-Host "`n💊 Testing Nutrient Planning..."
try {
    Write-Host "Planning Week 4 nutrients for 20L system..." -ForegroundColor Cyan
    $plan = Invoke-Expression "$sshCmd 'curl -s `"$baseUrl/dose/plan?week=4`&volume_l=20`"'" | ConvertFrom-Json
    Write-Host "Nutrient Plan:" -ForegroundColor Yellow
    foreach ($nutrient in $plan.doses.PSObject.Properties) {
        Write-Host "  $($nutrient.Name): $($nutrient.Value) ml" -ForegroundColor White
    }
    Write-Host "Total Volume: $($plan.total_ml) ml" -ForegroundColor Green
} catch {
    Write-Warning "Nutrient planning failed: $_"
}

Write-Host "`n📹 Checking Camera Stream..."
try {
    $cameraStatus = Invoke-Expression "$sshCmd 'curl -I -s http://localhost:8080 | head -n1'"
    if ($cameraStatus -match "200") {
        Write-Host "✅ Camera stream active at http://$PiHost:8080" -ForegroundColor Green
    } else {
        Write-Warning "Camera stream not responding"
    }
} catch {
    Write-Warning "Camera check failed: $_"
}

Write-Host "`n🔧 Service Status Check..."
try {
    Write-Host "RDWC Service:" -ForegroundColor Cyan
    Invoke-Expression "$sshCmd 'sudo systemctl is-active rdwc'"
    
    Write-Host "Camera Service:" -ForegroundColor Cyan  
    Invoke-Expression "$sshCmd 'sudo systemctl is-active rdwc-camera 2>/dev/null || echo inactive'"
} catch {
    Write-Warning "Service status check failed: $_"
}

Write-Host "`n📈 Recent Data Sample..."
try {
    $history = Invoke-Expression "$sshCmd 'curl -s $baseUrl/history'" | ConvertFrom-Json
    $recent = $history.samples | Select-Object -First 3
    Write-Host "Last 3 readings:" -ForegroundColor Yellow
    foreach ($sample in $recent) {
        Write-Host "  $($sample.timestamp): pH=$($sample.pH), EC=$($sample.ec), T=$($sample.temperature_c)°C" -ForegroundColor White
    }
} catch {
    Write-Warning "History check failed: $_"
}

Write-Host "`n🎯 Demo Complete!" -ForegroundColor Green
Write-Host "=================="
Write-Host ""
Write-Host "🌐 Access Points:" -ForegroundColor Cyan
Write-Host "  Control Panel: http://$PiHost:8000"
Write-Host "  Camera Stream: http://$PiHost:8080"
Write-Host "  SSH Access: ssh $User@$PiHost"
Write-Host ""
Write-Host "🔧 Useful Commands:" -ForegroundColor Cyan
Write-Host "  sudo systemctl status rdwc"
Write-Host "  sudo journalctl -u rdwc -f"
Write-Host "  curl $baseUrl/status | jq"
Write-Host ""
Write-Host "✨ RDWC-v4 Production System Ready!" -ForegroundColor Green