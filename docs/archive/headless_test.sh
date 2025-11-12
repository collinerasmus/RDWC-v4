#!/bin/bash
set -euo pipefail

echo '=== Close all dashboard browsers now. Starting 10-min headless proof ==='
echo 'Baseline status:'
curl -fsS http://127.0.0.1:8080/api/sensors/status || true
echo ''

# Start marker
t0=$(date +%s)
echo "Start epoch: $t0"
echo "Sleeping 600s..."
sleep 600

echo ''
echo '=== DB rows in last 600s ==='
sqlite3 /home/pi/RDWC-v4/data/rdwc.db "SELECT COUNT(*) FROM readings WHERE ts > strftime('%s','now')-600;"

echo ''
echo '=== Last 5 readings ==='
sqlite3 /home/pi/RDWC-v4/data/rdwc.db << 'SQL'
.headers on
.mode column
SELECT datetime(ts,'unixepoch','localtime') as time, temp_c, ph, ec_ms_cm
FROM readings
ORDER BY ts DESC
LIMIT 5;
SQL

echo ''
echo '=== sensors/status (should be running:true; heartbeat <10s) ==='
curl -fsS http://127.0.0.1:8080/api/sensors/status || true

echo ''
echo '=== rdwc-sensors logs (tail 50, should be clean) ==='
journalctl -u rdwc-sensors.service -n 50 --no-pager
