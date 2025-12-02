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


@router.get("/ec_raw")
def ec_raw() -> Dict[str, Any]:
    """Get raw EC reading from EZO device for scale diagnostics (read-only)"""
    try:
        # Lazy import to avoid I2C ownership at module load
        from app.ezo_i2c_stabilized import EZO, EC_ADDR
        
        ec_dev = EZO(1, EC_ADDR, "EC")
        ec_dev.init_once()
        time.sleep(0.3)
        
        # Read raw value from device
        raw_str = ec_dev.read_value(timeout=1.5)
        raw_value = float(raw_str)
        
        # Get the processed value from _last (global in main.py)
        import app.main as main_module
        processed_mS_cm = main_module._last.get("ec_ms_cm")
        
        # Infer unit based on magnitude
        if raw_value >= 1000:
            raw_unit = "µS/cm"
            suggested_scale = 0.001  # Convert µS/cm to mS/cm
        elif raw_value >= 10:
            raw_unit = "mS/cm (maybe)"
            suggested_scale = 1.0
        else:
            raw_unit = "mS/cm"
            suggested_scale = 1.0
        
        return {
            "raw_value": raw_value,
            "raw_unit": raw_unit,
            "processed_mS_cm": processed_mS_cm,
            "suggested_scale_hint": suggested_scale,
            "note": f"If raw is {raw_value} {raw_unit}, processed should be ~{raw_value * suggested_scale:.2f} mS/cm"
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/i2c_ec_id")
def i2c_ec_id() -> Dict[str, Any]:
    """Get EZO EC device identification (read-only probe)"""
    try:
        # Lazy import to avoid I2C ownership at module load
        from app.ezo_i2c_stabilized import EZO, EC_ADDR
        
        ec_dev = EZO(1, EC_ADDR, "EC")
        
        # Query device info
        device_info = ec_dev.cmd("I", read_len=32, settle=0.3)
        
        # Query K value (probe constant)
        k_value = ec_dev.cmd("K,?", read_len=32, settle=0.3)
        
        # Query calibration status
        cal_status = ec_dev.cmd("Cal,?", read_len=32, settle=0.3)
        
        # Query output parameters (shows if EC is in µS or mS)
        output_params = ec_dev.cmd("O,?", read_len=32, settle=0.3)
        
        return {
            "device_info": device_info or "No response",
            "k_value": k_value or "No response",
            "cal_status": cal_status or "No response",
            "output_params": output_params or "No response",
            "note": "Check cal_status for calibration type and output_params for units"
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/ec_unit_check")
def ec_unit_check() -> Dict[str, Any]:
    """
    Diagnostic endpoint to verify EC unit conversion is working.
    Compares raw sensor value with converted value.
    """
    try:
        from app.ezo_i2c_stabilized import EZO, EC_ADDR, EC_UNIT_THRESHOLD
        
        ec_dev = EZO(1, EC_ADDR, "EC")
        ec_dev.init_once()
        time.sleep(0.3)
        
        # Read raw value directly
        raw_str = ec_dev.read_value(timeout=1.5)
        raw_value = float(raw_str)
        
        # Apply same conversion logic
        if raw_value > EC_UNIT_THRESHOLD:
            converted = raw_value / 1000.0
            conversion_applied = True
            from_unit = "µS/cm"
            to_unit = "mS/cm"
        else:
            converted = raw_value
            conversion_applied = False
            from_unit = "mS/cm"
            to_unit = "mS/cm"
        
        # Get what the API is returning
        import app.main as main_module
        cached_ec = main_module._last.get("ec_ms_cm")
        
        # Read from database
        from app.sensors_core import read_sensors_from_db
        db_data = read_sensors_from_db(max_age_sec=300)
        db_ec = db_data.get("ec_mscm")
        
        return {
            "EC_UNIT_THRESHOLD": EC_UNIT_THRESHOLD,
            "raw_from_sensor": raw_value,
            "conversion_applied": conversion_applied,
            "converted_value": converted,
            "from_unit": from_unit,
            "to_unit": to_unit,
            "cached_ec_ms_cm": cached_ec,
            "db_ec_mscm": db_ec,
            "status": "OK" if (cached_ec is not None and cached_ec < EC_UNIT_THRESHOLD) else "NEEDS_SERVICE_RESTART",
            "note": f"If raw={raw_value:.1f} {from_unit} and threshold={EC_UNIT_THRESHOLD}, "
                    f"converted should be {converted:.4f} {to_unit}. "
                    f"Cache shows {cached_ec}, DB shows {db_ec}. "
                    f"If cache/DB shows >{EC_UNIT_THRESHOLD}, service needs restart."
        }
    except Exception as e:
        return {"error": str(e), "note": "Run on Pi with I2C access"}
