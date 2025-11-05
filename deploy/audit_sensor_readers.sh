#!/bin/bash
# Ghost/duplicate sensor reader audit and cleanup script
# Usage: ./audit_sensor_readers.sh [--kill]

set -euo pipefail

KILL_MODE=false
if [[ "${1:-}" == "--kill" ]]; then
    KILL_MODE=true
fi

echo "=== RDWC Sensor Reader Audit ==="
echo "Date: $(date)"
echo ""

# 1. Check systemd units
echo ">>> Checking systemd units for rdwc/hydro/sensor/atlas/ezo/app..."
systemctl list-units --all --no-pager | grep -Ei 'rdwc|hydro|sensor|atlas|ezo|app' || echo "  (no matches)"
echo ""

# 2. Check for legacy cron jobs
echo ">>> Checking crontab for legacy sensor readers..."
crontab -l 2>/dev/null | grep -Ei 'rdwc|sensor|atlas|ezo' || echo "  (no matches)"
echo ""

# 3. Check for stray Python processes
echo ">>> Checking for stray Python sensor processes..."
ps aux | head -n 1  # header
STRAY_PIDS=$(ps aux | grep -E 'python.*(rdwc|ezo|atlas|sensor)' | grep -v grep | grep -v "audit_sensor_readers" | awk '{print $2}' || true)

if [[ -z "$STRAY_PIDS" ]]; then
    echo "  (no stray processes found)"
else
    echo "Found stray PIDs: $STRAY_PIDS"
    ps aux | grep -E 'python.*(rdwc|ezo|atlas|sensor)' | grep -v grep | grep -v "audit_sensor_readers"
    
    if [[ "$KILL_MODE" == true ]]; then
        echo ""
        echo ">>> KILL MODE: Terminating stray processes..."
        for pid in $STRAY_PIDS; do
            echo "  Killing PID $pid"
            kill -TERM "$pid" || true
        done
        sleep 2
        # Force kill any survivors
        for pid in $STRAY_PIDS; do
            if ps -p "$pid" > /dev/null 2>&1; then
                echo "  Force killing PID $pid"
                kill -9 "$pid" || true
            fi
        done
    fi
fi
echo ""

# 4. Check I2C bus ownership
echo ">>> Checking I2C bus (/dev/i2c-1) ownership..."
if command -v lsof > /dev/null; then
    sudo lsof /dev/i2c-1 2>/dev/null || echo "  (no processes have /dev/i2c-1 open)"
else
    echo "  (lsof not installed, skipping)"
fi
echo ""

# 5. Check sensor poller lock file
echo ">>> Checking sensor poller lock file..."
LOCK_FILE="/run/rdwc_sensors.lock"
if [[ ! -f "$LOCK_FILE" ]]; then
    LOCK_FILE="/tmp/rdwc_sensors.lock"
fi

if [[ -f "$LOCK_FILE" ]]; then
    LOCK_PID=$(cat "$LOCK_FILE")
    echo "  Lock file: $LOCK_FILE"
    echo "  Lock PID: $LOCK_PID"
    if ps -p "$LOCK_PID" > /dev/null 2>&1; then
        echo "  Status: PID $LOCK_PID is running"
        ps -p "$LOCK_PID" -o pid,cmd
    else
        echo "  Status: PID $LOCK_PID is STALE (not running)"
        if [[ "$KILL_MODE" == true ]]; then
            echo "  Removing stale lock file..."
            rm -f "$LOCK_FILE"
        fi
    fi
else
    echo "  (no lock file found)"
fi
echo ""

# 6. Summary
echo "=== Audit Complete ==="
if [[ "$KILL_MODE" == true ]]; then
    echo "Cleanup actions were performed."
else
    echo "No cleanup performed (dry-run mode)."
    echo "Run with --kill to clean up stray processes and stale locks."
fi
