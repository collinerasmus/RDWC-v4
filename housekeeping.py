#!/usr/bin/env python3
"""
RDWC-v4 Housekeeping & System Health Check
Monitors system during overnight auto operation and logs health metrics.
"""
import sqlite3
import time
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import subprocess
import sys

DB_PATH = Path("data/rdwc.db")
LOG_PATH = Path("data/housekeeping.log")

def get_setting(key, default=None):
    """Get a setting value."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = cur.fetchone()
            return row[0] if row else default
    except:
        return default

def log_health_entry(entry):
    """Append health check to housekeeping log."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(str(LOG_PATH), "a") as f:
        f.write(json.dumps(entry) + "\n")

def check_system_health():
    """Perform comprehensive system health check."""
    now = datetime.now(timezone.utc)
    health = {
        "ts": now.isoformat(),
        "checks": {}
    }
    
    if not DB_PATH.exists():
        health["status"] = "error"
        health["checks"]["database"] = "not_found"
        return health
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # 1. Sensor freshness
        try:
            cur.execute("SELECT ts FROM readings ORDER BY ts DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                sensor_age_s = now.timestamp() - row['ts']
                health["checks"]["sensor_age_s"] = round(sensor_age_s, 1)
                health["checks"]["sensor_fresh"] = sensor_age_s < 120
            else:
                health["checks"]["sensor_fresh"] = False
                health["checks"]["sensor_note"] = "no_readings"
        except Exception as e:
            health["checks"]["sensor_error"] = str(e)
        
        # 2. Dose events count & breakdown
        try:
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN blocked_by IS NULL THEN 1 ELSE 0 END) as ok,
                    SUM(CASE WHEN blocked_by IS NOT NULL THEN 1 ELSE 0 END) as blocked
                FROM dose_events
            """)
            row = cur.fetchone()
            health["checks"]["dose_events"] = {
                "total": row['total'] or 0,
                "ok": row['ok'] or 0,
                "blocked": row['blocked'] or 0
            }
        except Exception as e:
            health["checks"]["dose_events_error"] = str(e)
        
        # 3. Daily dose usage
        try:
            cur.execute("""
                SELECT SUM(CASE WHEN blocked_by IS NULL THEN seconds ELSE 0 END) as used
                FROM dose_events
                WHERE ts >= (datetime('now', 'start of day', 'unixepoch') * 1000)
            """)
            row = cur.fetchone()
            used = float(row['used'] or 0)
            cap = float(get_setting("safety.max_total_seconds_per_24h", "120"))
            health["checks"]["daily_dose"] = {
                "used_s": round(used, 1),
                "cap_s": cap,
                "remaining_s": round(max(0, cap - used), 1),
                "pct": round(100.0 * used / cap if cap > 0 else 0, 1)
            }
        except Exception as e:
            health["checks"]["daily_dose_error"] = str(e)
        
        # 4. Auto modes check
        try:
            auto_keys = [
                "controls.global_auto",
                "controls.ph_auto",
                "controls.ec_auto",
                "controls.chiller_auto"
            ]
            all_auto = True
            for key in auto_keys:
                val = get_setting(key, "false")
                if val.lower() != "true":
                    all_auto = False
                    break
            health["checks"]["all_auto_enabled"] = all_auto
        except Exception as e:
            health["checks"]["auto_error"] = str(e)
        
        # 5. Database size
        try:
            db_size_mb = DB_PATH.stat().st_size / (1024 * 1024)
            health["checks"]["db_size_mb"] = round(db_size_mb, 1)
        except Exception as e:
            health["checks"]["db_size_error"] = str(e)
        
        # 6. Relay status check
        try:
            cur.execute("SELECT COUNT(*) as cnt FROM relay_events ORDER BY ts DESC LIMIT 100")
            count = cur.fetchone()['cnt']
            health["checks"]["relay_events_recent"] = count
        except:
            health["checks"]["relay_events_note"] = "table_not_found"
        
        # 7. System state
        try:
            cur.execute("SELECT value FROM settings WHERE key='safety.estop'")
            row = cur.fetchone()
            estop = (row['value'].lower() == 'true') if row else False
            health["checks"]["estop_active"] = estop
        except Exception as e:
            health["checks"]["estop_error"] = str(e)
    
    # Overall status
    errors = [v for k, v in health["checks"].items() if "error" in k]
    if errors:
        health["status"] = "warning"
    elif health["checks"].get("sensor_fresh") and health["checks"].get("all_auto_enabled"):
        health["status"] = "healthy"
    else:
        health["status"] = "degraded"
    
    return health

def main():
    print(f"\n{'='*80}")
    print(f"RDWC-v4 HOUSEKEEPING — System Health Check")
    print(f"{'='*80}\n")
    
    health = check_system_health()
    
    # Pretty print
    print(f"Timestamp: {health['ts']}")
    print(f"Status: {health['status'].upper()}")
    print(f"\nChecks:")
    for key, value in health["checks"].items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")
    
    # Log entry
    log_health_entry(health)
    print(f"\n✅ Health check logged to {LOG_PATH}")
    
    # Exit code based on status
    if health["status"] == "healthy":
        sys.exit(0)
    elif health["status"] == "degraded":
        sys.exit(1)
    else:
        sys.exit(2)

if __name__ == "__main__":
    main()
