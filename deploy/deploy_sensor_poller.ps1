#!/usr/bin/env pwsh
# Deploy headless sensor poller to Raspberry Pi
# Usage: .\deploy_sensor_poller.ps1

$PI_HOST = "pi@192.168.88.49"
$PI_PASS = "DrowPas$"
$REPO_DIR = "/home/pi/RDWC-v4"

Write-Host "=== RDWC Sensor Poller Deployment ===" -ForegroundColor Cyan
Write-Host ""

# 1. Run audit script first (dry-run)
Write-Host ">>> Running pre-deployment audit..." -ForegroundColor Yellow
ssh $PI_HOST "cd $REPO_DIR && bash deploy/audit_sensor_readers.sh"
Write-Host ""

# 2. Pull latest code
Write-Host ">>> Pulling latest code on Pi..." -ForegroundColor Yellow
ssh $PI_HOST "cd $REPO_DIR && git fetch && git pull"
Write-Host ""

# 3. Deploy systemd units (sensors + watchdog + db maintenance)
Write-Host ">>> Deploying systemd units..." -ForegroundColor Yellow
scp deploy/systemd/rdwc-sensors.service ${PI_HOST}:/tmp/
scp deploy/systemd/rdwc-sensors-watchdog.service ${PI_HOST}:/tmp/
scp deploy/systemd/rdwc-sensors-watchdog.timer ${PI_HOST}:/tmp/
scp deploy/systemd/rdwc-db-maint.service ${PI_HOST}:/tmp/
scp deploy/systemd/rdwc-db-maint.timer ${PI_HOST}:/tmp/
scp deploy/db_maint.sh ${PI_HOST}:/tmp/rdwc_db_maint.sh

ssh $PI_HOST "echo 'DrowPas$' | sudo -S mv /tmp/rdwc-sensors.service /etc/systemd/system/ && \
              echo 'DrowPas$' | sudo -S mv /tmp/rdwc-sensors-watchdog.service /etc/systemd/system/ && \
              echo 'DrowPas$' | sudo -S mv /tmp/rdwc-sensors-watchdog.timer /etc/systemd/system/ && \
              echo 'DrowPas$' | sudo -S mv /tmp/rdwc-db-maint.service /etc/systemd/system/ && \
              echo 'DrowPas$' | sudo -S mv /tmp/rdwc-db-maint.timer /etc/systemd/system/ && \
              echo 'DrowPas$' | sudo -S mv /tmp/rdwc_db_maint.sh /usr/local/bin/rdwc_db_maint.sh && \
              echo 'DrowPas$' | sudo -S chmod +x /usr/local/bin/rdwc_db_maint.sh && \
              echo 'DrowPas$' | sudo -S systemctl daemon-reload"
Write-Host ""

# 4. Enable and start services
Write-Host ">>> Enabling and starting sensor poller..." -ForegroundColor Yellow
ssh $PI_HOST "echo 'DrowPas$' | sudo -S systemctl enable rdwc-sensors.service && \
              echo 'DrowPas$' | sudo -S systemctl restart rdwc-sensors.service"
Write-Host ""

# 4b. Enable and start DB maintenance weekly timer
Write-Host ">>> Enabling weekly DB maintenance timer..." -ForegroundColor Yellow
ssh $PI_HOST "echo 'DrowPas$' | sudo -S systemctl enable rdwc-db-maint.timer && \
              echo 'DrowPas$' | sudo -S systemctl start rdwc-db-maint.timer"
Write-Host ""

Write-Host ">>> Enabling and starting watchdog timer..." -ForegroundColor Yellow
ssh $PI_HOST "echo 'DrowPas$' | sudo -S systemctl enable rdwc-sensors-watchdog.timer && \
              echo 'DrowPas$' | sudo -S systemctl start rdwc-sensors-watchdog.timer"
Write-Host ""

# 5. Show status
Write-Host ">>> Checking sensor poller status..." -ForegroundColor Yellow
ssh $PI_HOST "systemctl status rdwc-sensors.service --no-pager -l" 2>&1 | Write-Host
Write-Host ""

Write-Host ">>> Checking watchdog timer status..." -ForegroundColor Yellow
ssh $PI_HOST "systemctl list-timers rdwc-sensors-watchdog.timer --no-pager" 2>&1 | Write-Host
Write-Host ""

Write-Host ">>> Checking DB maintenance timer status..." -ForegroundColor Yellow
ssh $PI_HOST "systemctl list-timers rdwc-db-maint.timer --no-pager" 2>&1 | Write-Host
Write-Host "" 

# 6. Show recent logs
Write-Host ">>> Recent sensor poller logs (last 50 lines)..." -ForegroundColor Yellow
ssh $PI_HOST "journalctl -u rdwc-sensors.service -n 50 --no-pager" 2>&1 | Write-Host
Write-Host ""

# 7. Test API endpoint
Write-Host ">>> Testing /api/sensors/status endpoint..." -ForegroundColor Yellow
Start-Sleep -Seconds 3
$status = ssh $PI_HOST "curl -s http://localhost:8000/api/sensors/status" | ConvertFrom-Json
Write-Host "  Running: $($status.running)" -ForegroundColor $(if($status.running){"Green"}else{"Red"})
Write-Host "  Poll Count: $($status.poll_count)"
Write-Host "  Interval: $($status.interval_sec)s"
Write-Host "  Lock File: $($status.lock_file)"
Write-Host "  Lock PID: $($status.lock_pid)"
Write-Host ""

Write-Host ">>> Testing /api/health endpoint..." -ForegroundColor Yellow
$health = ssh $PI_HOST "curl -s http://localhost:8000/api/health" | ConvertFrom-Json
Write-Host "  OK: $($health.ok)" -ForegroundColor $(if($health.ok){"Green"}else{"Red"})
Write-Host "  Version: $($health.app_version)"
Write-Host "  Git Commit: $($health.git_commit)"
Write-Host "  Uptime: $([math]::Round($health.uptime_seconds, 1))s"
Write-Host ""

# 8. I2C bus ownership check
Write-Host ">>> I2C bus ownership (expect rdwc-sensors only)..." -ForegroundColor Yellow
ssh $PI_HOST "sudo lsof /dev/i2c-1 || true" 2>&1 | Write-Host
Write-Host "" 

Write-Host "=== Deployment Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Close all browsers and wait 10 minutes"
Write-Host "2. Run: Invoke-RestMethod http://192.168.88.49:8000/api/sensors/status"
Write-Host "3. Check database has new samples: ssh pi@192.168.88.49 'sqlite3 /home/pi/RDWC-v4/data/rdwc.db `"SELECT datetime(ts, 'unixepoch', 'localtime'), temp_c, ph, ec_ms_cm FROM readings ORDER BY ts DESC LIMIT 10`"'"
Write-Host ""
Write-Host "To disable sensor poller:" -ForegroundColor Yellow
Write-Host "  ssh $PI_HOST 'sudo systemctl stop rdwc-sensors.service && sudo systemctl disable rdwc-sensors.service'"
