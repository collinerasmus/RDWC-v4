@echo off
echo === RDWC-v4: Start deploy to pi@192.168.88.49 ===

echo — Testing SSH connection...
ssh pi@192.168.88.49 "echo 'SSH connection successful'"
if %errorlevel% neq 0 (
    echo ERROR: Cannot connect to Pi via SSH
    pause
    exit /b 1
)

echo — Stopping any rdwc*.service and backing up RDWC folders...
ssh pi@192.168.88.49 "set -e; cd ~; for s in $(systemctl list-unit-files | awk '/^rdwc.*\.service/ {print $1}'); do sudo systemctl stop \"$s\" 2>/dev/null || true; done; STAMP=$(date +%%Y%%m%%d_%%H%%M%%S); RDWC_DIRS=$(ls -d RDWC* rdwc* 2>/dev/null || true); if [ -n \"$RDWC_DIRS\" ]; then tar -czf \"RDWC-backup_${STAMP}.tar.gz\" $RDWC_DIRS; echo Backup created: RDWC-backup_${STAMP}.tar.gz; fi"

echo — Cleaning old RDWC installations...
ssh pi@192.168.88.49 "set -e; cd ~; rm -rf ~/RDWC-v3 ~/RDWC-v2 ~/RDWC-v1 ~/RDWC ~/rdwc ~/RDWC.v3 2>/dev/null || true; for f in /etc/systemd/system/rdwc*.service; do [ -e \"$f\" ] && sudo rm \"$f\"; done; sudo systemctl daemon-reload"

echo — Installing dependencies and enabling I2C...
ssh pi@192.168.88.49 "sudo apt-get update -y && sudo apt-get install -y i2c-tools python3-venv python3-pip && sudo raspi-config nonint do_i2c 0"

echo — Rebooting Pi...
ssh pi@192.168.88.49 "sudo reboot" 2>nul

echo — Waiting for Pi to reboot (30 seconds)...
timeout /t 30 /nobreak

echo — Waiting for SSH to come back online...
:wait_ssh
ssh pi@192.168.88.49 "echo OK" >nul 2>&1
if %errorlevel% neq 0 (
    timeout /t 2 /nobreak >nul
    goto wait_ssh
)
echo SSH is back online.

echo — Verifying I2C devices...
ssh pi@192.168.88.49 "i2cdetect -y 1"

echo — Deploying RDWC-v4...
ssh pi@192.168.88.49 "set -e; cd ~; rm -rf RDWC-v4; git clone https://github.com/collinerasmus/RDWC-v4.git; cd RDWC-v4; python3 -m venv .venv; source .venv/bin/activate; pip install --upgrade pip; pip install -r requirements.txt; cp .env.example .env; sed -i 's/^ENV=.*/ENV=prod/' .env; sudo cp systemd/rdwc.service /etc/systemd/system/rdwc.service; sudo systemctl daemon-reload; sudo systemctl enable rdwc.service; sudo systemctl start rdwc.service"

echo — Checking service status...
ssh pi@192.168.88.49 "sudo systemctl status rdwc.service --no-pager -l"

echo — Testing API...
ssh pi@192.168.88.49 "curl -s http://localhost:8080/status || echo 'API test failed'"

echo === RDWC-v4: Deploy complete. Open http://192.168.88.49:8080/status in your browser. ===
pause