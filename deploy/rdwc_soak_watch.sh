#!/usr/bin/env bash
set -euo pipefail
LOGDIR="/home/pi/soak_logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/soak_watch.log"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
DB_JSON="$(curl -fsS http://127.0.0.1:8080/health/db || echo '{}')"
GAP_JSON="$(curl -fsS 'http://127.0.0.1:8080/debug/readings/gaps?hours=1&min_gap_sec=180' || echo '[]')"
echo "=== $TS ===" >>"$LOG"
echo "$DB_JSON" >>"$LOG"
echo "$GAP_JSON" >>"$LOG"
echo >>"$LOG"
