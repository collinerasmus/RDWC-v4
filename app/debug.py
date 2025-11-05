# app/debug.py
from fastapi import APIRouter
from typing import Dict, Any
from collections import deque
import time
import threading

router = APIRouter()
_lock = threading.Lock()
_relay_requests = deque(maxlen=50)  # ring buffer of recent relay requests

def trace_relay_request(name: str, on: bool, via: str, result: Dict[str, Any]) -> None:
    item = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "name": name,
        "on": on,
        "via": via,
        "result": result,
    }
    with _lock:
        _relay_requests.append(item)

@router.get("/relay_requests")
def relay_requests() -> Dict[str, Any]:
    """Get the last 50 relay set requests for debugging."""
    with _lock:
        return {"count": len(_relay_requests), "items": list(_relay_requests)}


@router.get("/readings/hourly")
def readings_hourly(hours: int = 48) -> Dict[str, Any]:
    """Get hourly reading counts for gap detection"""
    import sqlite3
    import time
    from pathlib import Path
    
    try:
        db_path = Path("data/rdwc.db")
        if not db_path.exists():
            return {"error": "Database file not found"}
        
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            # ts is Unix timestamp integer, calculate cutoff
            cutoff_ts = int(time.time()) - (hours * 3600)
            cursor.execute("""
                SELECT 
                    strftime('%Y-%m-%d %H:00:00', datetime(ts, 'unixepoch')) as hour_iso,
                    COUNT(*) as rows
                FROM readings
                WHERE ts >= ?
                GROUP BY hour_iso
                ORDER BY hour_iso DESC
            """, (cutoff_ts,))
            
            results = [{"hour_iso": row[0], "rows": row[1]} for row in cursor.fetchall()]
            return {"hours_back": hours, "data": results}
    except Exception as e:
        return {"error": str(e)}


@router.get("/readings/gaps")
def readings_gaps(hours: int = 72, min_gap_sec: int = 180) -> Dict[str, Any]:
    """Find telemetry gaps larger than threshold"""
    import sqlite3
    import time
    from pathlib import Path
    from datetime import datetime, timezone
    
    try:
        db_path = Path("data/rdwc.db")
        if not db_path.exists():
            return {"error": "Database file not found"}
        
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            # ts is Unix timestamp integer
            cutoff_ts = int(time.time()) - (hours * 3600)
            cursor.execute("""
                WITH gaps AS (
                    SELECT 
                        ts as gap_end,
                        LAG(ts) OVER (ORDER BY ts) as gap_start,
                        (ts - LAG(ts) OVER (ORDER BY ts)) as gap_sec
                    FROM readings
                    WHERE ts >= ?
                )
                SELECT gap_start, gap_end, gap_sec
                FROM gaps
                WHERE gap_sec > ?
                ORDER BY gap_sec DESC
            """, (cutoff_ts, min_gap_sec))
            
            results = []
            for row in cursor.fetchall():
                gap_start_ts = row[0]
                gap_end_ts = row[1]
                gap_sec = row[2]
                # Convert Unix timestamps to ISO
                gap_start_iso = datetime.fromtimestamp(gap_start_ts, tz=timezone.utc).isoformat() if gap_start_ts else None
                gap_end_iso = datetime.fromtimestamp(gap_end_ts, tz=timezone.utc).isoformat() if gap_end_ts else None
                results.append({
                    "gap_start_iso": gap_start_iso,
                    "gap_end_iso": gap_end_iso,
                    "gap_sec": gap_sec
                })
            
            return {
                "hours_back": hours,
                "min_gap_sec": min_gap_sec,
                "gaps_found": len(results),
                "data": results
            }
    except Exception as e:
        return {"error": str(e)}


@router.get("/service/state")
def service_state() -> Dict[str, Any]:
    """Get RDWC service state from systemd"""
    from subprocess import run
    
    try:
        # Check service status
        result = run(
            ["systemctl", "is-active", "rdwc.service"],
            capture_output=True,
            text=True,
            timeout=5
        )
        service_active = result.stdout.strip() == "active"
        
        # Get uptime
        uptime_result = run(
            ["systemctl", "show", "rdwc.service", "--property=ActiveEnterTimestamp"],
            capture_output=True,
            text=True,
            timeout=5
        )
        uptime_info = uptime_result.stdout.strip()
        
        return {
            "rdwc_service": {
                "active": service_active,
                "status": result.stdout.strip(),
                "uptime_info": uptime_info
            }
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/log/tail")
def log_tail(n: int = 200) -> Dict[str, Any]:
    """Get last N lines from systemd journal"""
    from subprocess import run
    
    try:
        result = run(
            ["journalctl", "-u", "rdwc.service", "-n", str(n), "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        return {
            "lines_requested": n,
            "log": result.stdout
        }
    except Exception as e:
        return {"error": str(e)}
