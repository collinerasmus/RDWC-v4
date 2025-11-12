#!/usr/bin/env bash
set -euo pipefail
LOGDIR="/home/pi/precommission_logs"
mkdir -p "$LOGDIR"

echo "=== RDWC-v4 PRECOMMISSION 24h RUN START === $(date)" | tee -a "$LOGDIR/session.log"

# Step 1 – Baseline settings (100L reservoir, EC 0.8, pH 5.8-6.2, temp 19°C)
echo "[$(date +%H:%M:%S)] Configuring baseline settings..." | tee -a "$LOGDIR/session.log"
curl -fsS -X PUT http://127.0.0.1:8080/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"general.reservoir_liters":"100","ec.target":"0.8","ec.enabled":"true","ec.maintenance_override":"false","targets.ph_low":"5.8","targets.ph_high":"6.2","temp.target":"19.0"}' \
  >> "$LOGDIR/session.log" 2>&1 || echo "Settings update failed" | tee -a "$LOGDIR/session.log"

# Step 2 – Enable auto controllers (pH and EC; temp auto if endpoint exists)
echo "[$(date +%H:%M:%S)] Enabling auto controllers..." | tee -a "$LOGDIR/session.log"
curl -fsS -X POST http://127.0.0.1:8080/api/ph/auto -H 'Content-Type: application/json' -d '{"enable":true}' >> "$LOGDIR/session.log" 2>&1 || true
curl -fsS -X POST http://127.0.0.1:8080/api/ec/auto -H 'Content-Type: application/json' -d '{"enable":true}' >> "$LOGDIR/session.log" 2>&1 || true

# Step 3 – 24h monitoring loop (every 5 min = 288 samples)
echo "[$(date +%H:%M:%S)] Starting 24h monitoring loop (288 x 5min samples)..." | tee -a "$LOGDIR/session.log"
for i in {1..288}; do
  TS=$(date +%Y%m%d_%H%M%S)
  curl -fsS http://127.0.0.1:8080/sensors/read  -o "$LOGDIR/sensors_$TS.json"  2>/dev/null || true
  curl -fsS http://127.0.0.1:8080/api/ph/status -o "$LOGDIR/ph_$TS.json"       2>/dev/null || true
  curl -fsS http://127.0.0.1:8080/api/ec/status -o "$LOGDIR/ec_$TS.json"       2>/dev/null || true
  curl -fsS http://127.0.0.1:8080/health/db     -o "$LOGDIR/health_$TS.json"   2>/dev/null || true
  
  # Log sample count every hour
  if [ $((i % 12)) -eq 0 ]; then
    echo "[$(date +%H:%M:%S)] Sample $i/288 ($(date))" | tee -a "$LOGDIR/session.log"
  fi
  
  sleep 300
done

# Step 4 – Export summary CSVs
echo "[$(date +%H:%M:%S)] Exporting 24h summary CSVs..." | tee -a "$LOGDIR/session.log"
curl -fsS "http://127.0.0.1:8080/export_csv?hours=24" -o "$LOGDIR/sensors_24h.csv" 2>/dev/null || echo "Sensors CSV export failed" | tee -a "$LOGDIR/session.log"
curl -fsS "http://127.0.0.1:8080/api/ph/dose_log.csv?hours=24" -o "$LOGDIR/ph_24h.csv" 2>/dev/null || echo "pH CSV export failed" | tee -a "$LOGDIR/session.log"
curl -fsS "http://127.0.0.1:8080/api/ec/dose_log.csv?hours=24" -o "$LOGDIR/ec_24h.csv" 2>/dev/null || echo "EC CSV export failed" | tee -a "$LOGDIR/session.log"

# Step 5 – Generate summary stats
echo "[$(date +%H:%M:%S)] Generating summary statistics..." | tee -a "$LOGDIR/session.log"
{
  echo "=== 24H PRE-COMMISSIONING SUMMARY ==="
  echo "Start: $(head -1 "$LOGDIR/session.log" | grep START)"
  echo "End: $(date)"
  echo ""
  echo "Samples collected: $(ls -1 "$LOGDIR"/sensors_*.json 2>/dev/null | wc -l)"
  echo "pH status logs: $(ls -1 "$LOGDIR"/ph_*.json 2>/dev/null | wc -l)"
  echo "EC status logs: $(ls -1 "$LOGDIR"/ec_*.json 2>/dev/null | wc -l)"
  echo ""
  echo "CSV exports:"
  ls -lh "$LOGDIR"/*.csv 2>/dev/null || echo "  (none)"
} | tee -a "$LOGDIR/session.log"

echo "=== RUN COMPLETE $(date) ===" | tee -a "$LOGDIR/session.log"
