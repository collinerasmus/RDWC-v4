# RDWC-v4 Lights Whitelist System Deployment Script (PowerShell)
# Deploys the anti-flap whitelist protection system to eliminate "off dips"

param(
    [string]$PiHost = "192.168.88.49",
    [string]$PiUser = "pi",
    [string]$RemoteDir = "/home/pi/RDWC-v4"
)

Write-Host "🚀 RDWC-v4 Lights Whitelist System Deployment" -ForegroundColor Green
Write-Host "=" * 50 -ForegroundColor Green
Write-Host ""

Write-Host "📋 Deployment Summary:" -ForegroundColor Cyan
Write-Host "   Target: $PiUser@$PiHost"
Write-Host "   Directory: $RemoteDir"
Write-Host "   Purpose: Deploy lights whitelist protection system"
Write-Host ""

# Function to run commands on Pi via SSH
function Invoke-SshCommand {
    param([string]$Command)
    
    try {
        $result = ssh "$PiUser@$PiHost" $Command 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "⚠️  Command returned exit code $LASTEXITCODE" -ForegroundColor Yellow
        }
        return $result
    }
    catch {
        Write-Host "❌ SSH command failed: $_" -ForegroundColor Red
        throw
    }
}

try {
    Write-Host "🔄 Step 1: Update code on Pi..." -ForegroundColor Cyan
    Invoke-SshCommand "cd $RemoteDir; git fetch --all; git reset --hard origin/main"

    Write-Host "📦 Step 2: Install/update dependencies..." -ForegroundColor Cyan
    Invoke-SshCommand "cd $RemoteDir; source .venv/bin/activate; pip install --upgrade pip; pip install -r requirements.txt"

    Write-Host "🔧 Step 3: Restart RDWC service..." -ForegroundColor Cyan
    Invoke-SshCommand "sudo systemctl restart rdwc.service"

    Write-Host "⏳ Step 4: Wait for service to start..." -ForegroundColor Cyan
    Start-Sleep -Seconds 5

    Write-Host "🔍 Step 5: Check service status..." -ForegroundColor Cyan
    Invoke-SshCommand "sudo systemctl status rdwc.service --no-pager -l"

    Write-Host ""
    Write-Host "🧪 Step 6: Test debug endpoints..." -ForegroundColor Cyan
    Write-Host "   Testing whitelist endpoint..." -ForegroundColor Yellow
    Invoke-SshCommand "curl -s http://localhost:8080/debug/lights_allowed | python3 -m json.tool"

    Write-Host ""
    Write-Host "   Testing event log endpoint..." -ForegroundColor Yellow
    Invoke-SshCommand 'curl -s "http://localhost:8080/debug/lights_log?last=5" | python3 -m json.tool'

    Write-Host ""
    Write-Host "✅ Deployment completed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "🔍 Monitoring Instructions:" -ForegroundColor Cyan
    Write-Host "   1. Watch event log: curl 'http://$PiHost`:8080/debug/lights_log?last=20'"
    Write-Host "   2. Check for blocked attempts: Look for 'blocked: true' in logs"
    Write-Host "   3. Monitor for 'off dips': Should be eliminated with edge-only scheduling"
    Write-Host "   4. View allowed reasons: curl 'http://$PiHost`:8080/debug/lights_allowed'"
    Write-Host ""
    Write-Host "🎯 Success Criteria:" -ForegroundColor Green
    Write-Host "   - ✅ No more periodic 'off dips' every ~minute"
    Write-Host "   - ✅ All light changes logged with caller identification"
    Write-Host "   - ✅ Unauthorized attempts blocked and logged"
    Write-Host "   - ✅ Scheduled on/off times work correctly at exact edges"
    Write-Host ""
    Write-Host "📊 Key Changes Deployed:" -ForegroundColor Cyan
    Write-Host "   - WHITELIST_LIGHTS with 8 approved reasons"
    Write-Host "   - Event tracing with caller detection (200-event history)"
    Write-Host "   - Pure edge-only scheduling (no periodic guards)"
    Write-Host "   - Anti-flap protection with cooldowns"
    Write-Host "   - Debug endpoints for monitoring"
    Write-Host ""
    
    Write-Host "🎉 Ready to monitor! Use the monitoring commands above." -ForegroundColor Green
}
catch {
    Write-Host "❌ Deployment failed: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 Troubleshooting:" -ForegroundColor Yellow
    Write-Host "   1. Check SSH connection: ssh $PiUser@$PiHost"
    Write-Host "   2. Verify Pi IP address: $PiHost"
    Write-Host "   3. Ensure SSH key authentication is set up"
    Write-Host "   4. Check if Git repository exists on Pi"
    exit 1
}