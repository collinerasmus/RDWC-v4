#!/bin/bash
set -euo pipefail

echo "=== Post-Reboot: Active states ==="
systemctl is-active rdwc-sensors.service || true
systemctl is-active rdwc-sensors-watchdog.timer || true
systemctl is-active rdwc.service || true

echo ""
echo "=== Fresh rows in last 120s (should be >20 for 5s interval) ==="
sqlite3 /home/pi/RDWC-v4/data/rdwc.db "SELECT COUNT(*) FROM readings WHERE ts > strftime('%s','now')-120;"

echo ""
echo "=== Last 5 readings ==="
sqlite3 /home/pi/RDWC-v4/data/rdwc.db << 'SQL'
.headers on
.mode column
SELECT datetime(ts,'unixepoch','localtime') as time, temp_c, ph, ec_ms_cm
FROM readings
ORDER BY ts DESC
LIMIT 5;
SQL

echo ""
echo "=== sensors/status ==="
curl -fsS http://127.0.0.1:8080/api/sensors/status || true

echo ""
echo "=== I2C ownership (expect rdwc-sensors only) ==="
sudo lsof /dev/i2c-1 | head -n 5 || true
