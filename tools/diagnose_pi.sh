#!/bin/bash
# Pi Diagnostic Script - Run this on the Raspberry Pi
# Usage: ssh pi@192.168.88.49 'bash -s' < tools/diagnose_pi.sh

echo "=== RDWC Pi System Diagnostic ==="
echo "Date: $(date)"
echo ""

echo "=== 1. Git Status ==="
cd ~/RDWC-v4 2>/dev/null || cd /home/pi/RDWC-v4 2>/dev/null || echo "ERROR: RDWC-v4 directory not found"
pwd
git branch --show-current
git log --oneline -3
echo ""

echo "=== 2. Service Status ==="
systemctl status rdwc --no-pager -l | head -20
echo ""
systemctl status rdwc-sensors --no-pager -l | head -20
echo ""

echo "=== 3. Recent Logs (last 50 lines) ==="
journalctl -u rdwc -n 50 --no-pager
echo ""

echo "=== 4. Process Check ==="
ps aux | grep -E 'uvicorn|python.*main.py|rdwc' | grep -v grep
echo ""

echo "=== 5. Port Check ==="
netstat -tuln | grep -E ':8080|:8000'
echo ""

echo "=== 6. Quick API Test ==="
curl -s http://localhost:8080/health | head -20
echo ""
curl -s http://localhost:8080/api/system_mode
echo ""
curl -s http://localhost:8080/api/relays/status | head -50
echo ""

echo "=== 7. Database Check ==="
ls -lh ~/RDWC-v4/data/rdwc.db 2>/dev/null || ls -lh /home/pi/RDWC-v4/data/rdwc.db 2>/dev/null
echo ""

echo "=== 8. E-Stop Status ==="
curl -s http://localhost:8080/api/estop
echo ""

echo "=== 9. Disk Space ==="
df -h | grep -E 'Filesystem|/$|/home'
echo ""

echo "=== Diagnostic Complete ==="
