# RDWC-v4 Full System Deployment with Camera and Diagnostics
param(
    [string]$PiHost = "pi-rdwc",
    [string]$User = "pi",
    [switch]$SetupCamera,
    [switch]$ActivatePumps,
    [switch]$SkipCamera,
    [switch]$SkipPumps
)

# Default to true unless explicitly skipped
if (-not $SkipCamera) { $SetupCamera = $true }
if (-not $SkipPumps) { $ActivatePumps = $true }

$ErrorActionPreference = "Stop"

Write-Host "🚀 Deploying RDWC-v4 System to $PiHost..." -ForegroundColor Green

# SSH command setup
$sshCmd = "ssh $User@$PiHost"

Write-Host "`n📁 Creating project directory and uploading code..."
try {
    # Create directories
    Invoke-Expression "$sshCmd 'mkdir -p ~/rdwc-v4/{src,tools,systemd}'"
    
    # Upload all source files
    scp -r src/* "$User@$PiHost`:~/rdwc-v4/src/"
    scp requirements.txt "$User@$PiHost`:~/rdwc-v4/"
    scp systemd/rdwc.service "$User@$PiHost`:~/rdwc-v4/systemd/"
    scp .env.example "$User@$PiHost`:~/rdwc-v4/"
    
    Write-Host "✅ Code upload complete" -ForegroundColor Green
} catch {
    Write-Error "Failed to upload code: $_"
}

Write-Host "`n🐍 Setting up Python environment..."
$pythonSetup = @"
cd ~/rdwc-v4
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
"@

try {
    Invoke-Expression "$sshCmd '$pythonSetup'"
    Write-Host "✅ Python environment ready" -ForegroundColor Green
} catch {
    Write-Error "Failed to setup Python environment: $_"
}

Write-Host "`n⚙️ Installing system service..."
try {
    Invoke-Expression "$sshCmd 'sudo cp ~/rdwc-v4/systemd/rdwc.service /etc/systemd/system/'"
    Invoke-Expression "$sshCmd 'sudo systemctl daemon-reload'"
    Invoke-Expression "$sshCmd 'sudo systemctl enable rdwc'"
    Write-Host "✅ System service installed" -ForegroundColor Green
} catch {
    Write-Error "Failed to install service: $_"
}

Write-Host "`n🔧 Setting up environment configuration..."
$envSetup = @"
cd ~/rdwc-v4
cp .env.example .env
# Update .env with production settings
sed -i 's/RDWC_ENV=dev/RDWC_ENV=production/' .env
sed -i 's/FORCE_MOCK_SENSORS=true/FORCE_MOCK_SENSORS=false/' .env
echo 'EC_TARGET_US=1200' >> .env
echo 'EC_TOL_US=50' >> .env
echo 'EC_STEP_ML_PER_10L=5' >> .env
echo 'EC_MAX_ML_PER_10L=80' >> .env
echo 'EC_STABILIZE_WAIT_SEC=45' >> .env
"@

try {
    Invoke-Expression "$sshCmd '$envSetup'"
    Write-Host "✅ Environment configured for production" -ForegroundColor Green
} catch {
    Write-Error "Failed to setup environment: $_"
}

if ($SetupCamera) {
    Write-Host "`n🎥 Setting up camera streaming..."
    try {
        # Install mjpg-streamer dependencies
        Invoke-Expression "$sshCmd 'sudo apt update && sudo apt install -y cmake libjpeg9-dev git'"
        
        # Build mjpg-streamer
        $mjpgBuild = @"
cd /tmp
rm -rf mjpg-streamer
git clone https://github.com/jacksonliam/mjpg-streamer.git
cd mjpg-streamer/mjpg-streamer-experimental
make clean
make
sudo make install
"@
        Invoke-Expression "$sshCmd '$mjpgBuild'"
        
        # Create camera service
        $cameraService = @'
[Unit]
Description=RDWC Camera Stream
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
ExecStart=/usr/local/bin/mjpg_streamer -i "input_uvc.so -d /dev/video0 -r 640x480 -f 15" -o "output_http.so -p 8080 -w /usr/local/share/mjpg-streamer/www"
Environment=LD_LIBRARY_PATH=/usr/local/lib
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
'@
        
        Invoke-Expression "$sshCmd 'echo ''$cameraService'' | sudo tee /etc/systemd/system/rdwc-camera.service'"
        Invoke-Expression "$sshCmd 'sudo systemctl daemon-reload'"
        Invoke-Expression "$sshCmd 'sudo systemctl enable rdwc-camera'"
        
        Write-Host "✅ Camera service installed" -ForegroundColor Green
    } catch {
        Write-Warning "Camera setup failed: $_"
    }
}

Write-Host "`n🔄 Starting services..."
try {
    # Start RDWC service
    Invoke-Expression "$sshCmd 'sudo systemctl restart rdwc'"
    Start-Sleep -Seconds 5
    
    # Start camera service if enabled
    if ($SetupCamera) {
        Invoke-Expression "$sshCmd 'sudo systemctl restart rdwc-camera'"
        Start-Sleep -Seconds 3
    }
    
    Write-Host "✅ Services started" -ForegroundColor Green
} catch {
    Write-Error "Failed to start services: $_"
}

Write-Host "`n📊 Checking service status..."
Invoke-Expression "$sshCmd 'sudo systemctl status rdwc --no-pager -l'"

if ($SetupCamera) {
    Write-Host "`n📹 Camera service status:"
    Invoke-Expression "$sshCmd 'sudo systemctl status rdwc-camera --no-pager -l'"
}

if ($ActivatePumps) {
    Write-Host "`n🔄 Activating circulation pumps..."
    Start-Sleep -Seconds 5  # Wait for API to be ready
    
    try {
        # Activate main pump and chiller for continuous circulation
        Invoke-Expression "$sshCmd 'curl -f -X POST http://localhost:8000/actuate/main_pump/1'"
        Start-Sleep -Seconds 2
        Invoke-Expression "$sshCmd 'curl -f -X POST http://localhost:8000/actuate/chiller_pump/1'"
        Start-Sleep -Seconds 2
        
        Write-Host "✅ Main circulation pumps activated" -ForegroundColor Green
    } catch {
        Write-Warning "Pump activation failed: $_"
    }
}

Write-Host "`n🧪 Testing system endpoints..."
try {
    Write-Host "System Status:"
    Invoke-Expression "$sshCmd 'curl -s http://localhost:8000/status | jq .data'"
    
    Write-Host "`nDiagnostics:"
    Invoke-Expression "$sshCmd 'curl -s http://localhost:8000/diag | jq .'"
    
    Write-Host "✅ API endpoints responding" -ForegroundColor Green
} catch {
    Write-Warning "Some endpoints may not be ready yet"
}

Write-Host "`n🎯 Deployment Summary" -ForegroundColor Cyan
Write-Host "===================="
Write-Host "RDWC Control Panel: http://$PiHost:8000" -ForegroundColor Yellow
if ($SetupCamera) {
    Write-Host "Camera Stream: http://$PiHost:8080" -ForegroundColor Yellow
}
Write-Host "SSH Access: ssh $User@$PiHost" -ForegroundColor Yellow
Write-Host ""
Write-Host "Service Commands:" -ForegroundColor White
Write-Host "  sudo systemctl status rdwc"
Write-Host "  sudo systemctl restart rdwc"
Write-Host "  sudo journalctl -u rdwc -f"
if ($SetupCamera) {
    Write-Host "  sudo systemctl status rdwc-camera"
}

Write-Host "`n✨ RDWC-v4 deployment complete!" -ForegroundColor Green