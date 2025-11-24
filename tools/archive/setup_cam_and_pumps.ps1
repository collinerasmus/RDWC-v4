# RDWC System - Camera Setup and Pump Activation Script
param(
    [string]$PiHost = "pi-rdwc",
    [string]$User = "pi"
)

Write-Host "🎥 Setting up camera stream and activating pumps on $PiHost..." -ForegroundColor Green

# SSH command setup
$sshCmd = "ssh $User@$PiHost"

Write-Host "`n📦 Installing mjpg-streamer dependencies..."
Invoke-Expression "$sshCmd 'sudo apt update && sudo apt install -y cmake libjpeg9-dev'"

Write-Host "`n📥 Downloading and building mjpg-streamer..."
$mjpgCommands = @"
cd /tmp
git clone https://github.com/jacksonliam/mjpg-streamer.git
cd mjpg-streamer/mjpg-streamer-experimental
make
sudo make install
"@

Invoke-Expression "$sshCmd '$mjpgCommands'"

Write-Host "`n🔧 Creating camera startup script..."
$cameraScript = @'
#!/bin/bash
# RDWC Camera Stream Service
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
mjpg_streamer -i "input_uvc.so -d /dev/video0 -r 640x480 -f 15" -o "output_http.so -p 8080 -w /usr/local/share/mjpg-streamer/www"
'@

Invoke-Expression "$sshCmd 'echo ''$cameraScript'' > /tmp/camera_start.sh'"
Invoke-Expression "$sshCmd 'chmod +x /tmp/camera_start.sh'"
Invoke-Expression "$sshCmd 'sudo mv /tmp/camera_start.sh /usr/local/bin/rdwc-camera'"

Write-Host "`n⚙️ Creating camera systemd service..."
$cameraService = @'
[Unit]
Description=RDWC Camera Stream
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
ExecStart=/usr/local/bin/rdwc-camera
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
'@

Invoke-Expression "$sshCmd 'echo ''$cameraService'' | sudo tee /etc/systemd/system/rdwc-camera.service'"
Invoke-Expression "$sshCmd 'sudo systemctl daemon-reload'"
Invoke-Expression "$sshCmd 'sudo systemctl enable rdwc-camera'"
Invoke-Expression "$sshCmd 'sudo systemctl start rdwc-camera'"

Write-Host "`n✅ Camera service status:"
Invoke-Expression "$sshCmd 'sudo systemctl status rdwc-camera --no-pager'"

Write-Host "`n🔄 Activating main circulation pumps..."
# Force main pump and chiller ON for continuous circulation
$pumpCommands = @(
    "curl -X POST http://localhost:8000/actuate/main_pump/1",
    "curl -X POST http://localhost:8000/actuate/chiller_pump/1"
)

foreach ($cmd in $pumpCommands) {
    Write-Host "Executing: $cmd" -ForegroundColor Cyan
    Invoke-Expression "$sshCmd '$cmd'"
    Start-Sleep -Seconds 2
}

Write-Host "`n📊 Checking system status..."
Invoke-Expression "$sshCmd 'curl -s http://localhost:8000/status | jq .'"

Write-Host "`n🎯 Testing camera stream..."
Write-Host "Camera stream should be available at: http://$PiHost:8080" -ForegroundColor Yellow
Write-Host "RDWC Control Panel: http://$PiHost:8000" -ForegroundColor Yellow

Write-Host "`n✨ Setup complete! Main pumps activated, camera streaming." -ForegroundColor Green