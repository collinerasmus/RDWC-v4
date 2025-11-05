#!/bin/bash
set -euo pipefail
DB="/home/pi/RDWC-v4/data/rdwc.db"
BACKUP_DIR="/home/pi/backups"
mkdir -p "$BACKUP_DIR"
STAMP=$(date +%Y%m%d_%H%M)
CSV="$BACKUP_DIR/rdwc_${STAMP}.csv"

# Export last 24h to CSV
sqlite3 "$DB" <<'SQL'
.headers on
.mode csv
.output TEMP_EXPORT.csv
WITH recent AS (
  SELECT ts, temp_c, ph, ec_ms_cm FROM readings WHERE ts > strftime('%s','now')-86400 ORDER BY ts
)
SELECT ts, temp_c, ph, ec_ms_cm FROM recent;
SQL
mv TEMP_EXPORT.csv "$CSV" || true

# Checkpoint and vacuum
sqlite3 "$DB" 'PRAGMA wal_checkpoint; VACUUM;'

echo "DB maintenance complete: $(date). CSV: $CSV"