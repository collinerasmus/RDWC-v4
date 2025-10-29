# Test script for new RDWC-v4 features
# Tests both chiller override system and temperature compensation

$PI_IP = "192.168.88.49"
$API_BASE = "http://${PI_IP}:8000"

Write-Host "=== Testing RDWC-v4 New Features ===" -ForegroundColor Green

# Test 1: Check current overrides status
Write-Host "`n[Test 1] Checking current overrides status..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_BASE/overrides" -Method GET
    Write-Host "Current overrides: $($response | ConvertTo-Json -Depth 2)" -ForegroundColor Cyan
} catch {
    Write-Host "ERROR: Could not get overrides status - $($_.Exception.Message)" -ForegroundColor Red
}

# Test 2: Set chiller to force_on for 30 minutes
Write-Host "`n[Test 2] Setting chiller to force_on for 30 minutes..." -ForegroundColor Yellow
try {
    $body = @{
        chiller_mode = "force_on"
        hold_minutes = 30
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "$API_BASE/overrides" -Method PUT -Body $body -ContentType "application/json"
    Write-Host "Override set: $($response | ConvertTo-Json -Depth 2)" -ForegroundColor Cyan
} catch {
    Write-Host "ERROR: Could not set override - $($_.Exception.Message)" -ForegroundColor Red
}

# Test 3: Check sensor readings (should show temperature compensation)
Write-Host "`n[Test 3] Checking sensor readings with temperature compensation..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_BASE/sensors" -Method GET
    Write-Host "Sensor readings: $($response | ConvertTo-Json -Depth 2)" -ForegroundColor Cyan
} catch {
    Write-Host "ERROR: Could not get sensor readings - $($_.Exception.Message)" -ForegroundColor Red
}

# Test 4: Wait a moment then clear the override
Start-Sleep -Seconds 5
Write-Host "`n[Test 4] Clearing chiller override..." -ForegroundColor Yellow
try {
    $body = @{
        chiller_mode = "auto"
        hold_minutes = 0
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "$API_BASE/overrides" -Method PUT -Body $body -ContentType "application/json"
    Write-Host "Override cleared: $($response | ConvertTo-Json -Depth 2)" -ForegroundColor Cyan
} catch {
    Write-Host "ERROR: Could not clear override - $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Test Complete ===" -ForegroundColor Green