#!/bin/bash
echo "=== DB rows since epoch 1762369540 (test start) ==="
sqlite3 /home/pi/RDWC-v4/data/rdwc.db "SELECT COUNT(*) FROM readings WHERE ts > 1762369540"

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
echo "=== Current sensor status ==="
curl -fsS http://127.0.0.1:8080/api/sensors/status

echo ""
echo "=== Service logs (last 20 lines) ==="
journalctl -u rdwc-sensors.service -n 20 --no-pager | grep -E '(INFO|ERROR|WARNING)' || echo "No errors found"
