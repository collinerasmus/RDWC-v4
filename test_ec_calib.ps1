#!/usr/bin/env pwsh

# EC Calibration Test Workflow

$host_ip = "192.168.88.49"

Write-Host "====== EC Calibration Test ======" -ForegroundColor Cyan

Write-Host "1. Getting baseline reading..."
$before = ssh $host_ip 'curl -s http://localhost:8080/api/sensors | jq .ec_mscm'
Write-Host "  Before: $before mS/cm"

Write-Host ""
Write-Host "2. Clearing calibration..."
ssh $host_ip 'curl -s -X POST http://localhost:8080/api/ec/cal/clear | jq .ok'

Start-Sleep -Seconds 2
$after_clear = ssh $host_ip 'curl -s http://localhost:8080/api/sensors | jq .ec_mscm'
Write-Host "  After clear: $after_clear mS/cm"

Write-Host ""
Write-Host "3. Setting K=1.0..."
ssh $host_ip 'curl -s -X POST http://localhost:8080/api/ec/k -H "Content-Type: application/json" -d "{`\"k`\": 1.0}" | jq .ok'

Start-Sleep -Seconds 2
$after_k = ssh $host_ip 'curl -s http://localhost:8080/api/sensors | jq .ec_mscm'
Write-Host "  After K=1.0: $after_k mS/cm"

Write-Host ""
Write-Host "4. Applying low-point calibration @ 1413 µS/cm..."
ssh $host_ip 'curl -s -X POST http://localhost:8080/api/ec/cal/low -H "Content-Type: application/json" -d "{`\"us_cm`\": 1413}" | jq .ok'

Start-Sleep -Seconds 3
$after_calib = ssh $host_ip 'curl -s http://localhost:8080/api/sensors | jq .ec_mscm'
Write-Host "  After calibration: $after_calib mS/cm"

Write-Host ""
Write-Host "====== Summary =====" -ForegroundColor Yellow
Write-Host "Initial: $before mS/cm"
Write-Host "After clear: $after_clear mS/cm"
Write-Host "After K=1.0: $after_k mS/cm"
Write-Host "After calib: $after_calib mS/cm"
Write-Host ""
Write-Host "Expected in 1413 µS/cm solution: ~1.413 mS/cm"
Write-Host "Actual after calibration: $after_calib mS/cm"
