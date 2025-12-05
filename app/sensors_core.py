"""
Centralized sensor reading with RTD-first and throttled temperature compensation.
Minimizes I²C traffic while maintaining accuracy.
"""
import os
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Atlas EZO I²C addresses
ADDR_RTD = 0x66  # Temperature sensor
ADDR_PH = 0x63   # pH sensor
ADDR_EC = 0x64   # EC sensor

# Temperature compensation throttling state
_last_t_sent_c: Optional[float] = None
_last_t_set_ts: float = 0.0

I2C_AVAILABLE = True  # sensor_controller already handles simulation fallback


def _should_send_temp_comp(temp_c: float) -> tuple[bool, float]:
    """
    Determine if temperature compensation should be sent to pH/EC sensors.
    
    Throttle rule:
    - Send T if ΔT >= 0.2°C OR time since last send >= 60s
    - Otherwise skip to reduce I²C traffic
    
    Returns:
        (should_send: bool, delta_t: float)
    """
    global _last_t_sent_c, _last_t_set_ts
    
    now = time.time()
    
    # First time - always send
    if _last_t_sent_c is None:
        return True, 0.0
    
    delta_t = abs(temp_c - _last_t_sent_c)
    time_since_last = now - _last_t_set_ts
    
    # Send if temperature changed significantly OR enough time passed
    should_send = (delta_t >= 0.2) or (time_since_last >= 60.0)
    
    return should_send, delta_t


def _update_temp_comp_cache(temp_c: float):
    """Update the temperature compensation cache after a successful send."""
    global _last_t_sent_c, _last_t_set_ts
    _last_t_sent_c = temp_c
    _last_t_set_ts = time.time()


def read_all_sensors() -> Dict[str, Any]:
    """
    Unified sensor read via sensor_controller (single source of truth).
    Returns sensor dict with temperature_c, ec_mscm, ph, online, ts, errors.
    """
    import datetime as dt
    try:
        from .sensor_controller import read_sensors
        data = read_sensors()
        return {
            "temperature_c": data.get("temperature_c"),
            "ec_mscm": data.get("ec_mscm"),
            "ph": data.get("ph"),
            "online": data.get("online", False),
            "ts": data.get("ts") or dt.datetime.utcnow().isoformat() + "Z",
            "temp_comp_applied": data.get("temp_comp_applied", True),
            "temp_comp_reason": data.get("temp_comp_reason", "sensor_controller"),
            "errors": data.get("errors", {})
        }
    except Exception as e:
        logger.error(f"Sensor read failed: {e}", exc_info=True)
        return {
            "temperature_c": None, "ec_mscm": None, "ph": None,
            "online": False, "ts": dt.datetime.utcnow().isoformat() + "Z",
            "temp_comp_applied": False, "temp_comp_reason": "",
            "errors": {"read": str(e)}
        }

    DEADLINE_S = float(os.getenv("RDWC_SENSORS_READ_DEADLINE_S", "2.5"))
    t0 = time.time()
    
    def left() -> float:
        return DEADLINE_S - (time.time() - t0)

    def timed_out() -> bool:
        return left() <= 0.0



def get_last_temp_comp_state() -> Dict[str, Any]:
    """
    Get current temperature compensation throttle state.
    Useful for diagnostics and testing.
    """
    return {
        "last_t_sent_c": _last_t_sent_c,
        "last_t_set_ts": _last_t_set_ts,
        "time_since_last": time.time() - _last_t_set_ts if _last_t_set_ts > 0 else None
    }


def read_sensors_from_db(db_path: str = None, max_age_sec: int = 60) -> Dict[str, Any]:
    """
    Read most recent sensor values from database (written by sensor_poller).
    This is the PREFERRED method for all non-poller consumers (API endpoints, controllers).
    
    Args:
        db_path: Path to rdwc.db (defaults to RDWC_DB env var or data/rdwc.db)
        max_age_sec: Maximum acceptable age of reading (default 60s)
        
    Returns:
        Dict with temperature_c, ph, ec_mscm, online, ts, age_sec, errors
        online=False if reading is stale or missing
    """
    import sqlite3
    import datetime as dt
    from pathlib import Path
    
    if db_path is None:
        db_path = os.environ.get("RDWC_DB", "data/rdwc.db")
    
    db_path = Path(db_path)
    if not db_path.exists():
        return {
            "temperature_c": None, "ph": None, "ec_mscm": None,
            "online": False, "ts": None, "age_sec": None,
            "errors": {"db": "database not found"}
        }
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        # Get most recent reading
        row = conn.execute(
            "SELECT ts, temp_c, ph, ec_ms_cm FROM readings ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        conn.close()
        
        if not row:
            return {
                "temperature_c": None, "ph": None, "ec_mscm": None,
                "online": False, "ts": None, "age_sec": None,
                "errors": {"db": "no readings found"}
            }
        
        now_ts = int(time.time())
        age_sec = now_ts - row["ts"]
        is_stale = age_sec > max_age_sec
        
        # Apply maintenance overrides if active
        original = {
            "temperature_c": row["temp_c"],
            "ph": row["ph"],
            "ec_mscm": row["ec_ms_cm"],
        }
        effective = dict(original)
        # NOTE: Sensor readings are always returned. The auto-enable system
        # controls controller automation, not sensor data visibility.
        # Mode overrides are deprecated - return actual sensor values.
        overrides = {"temperature_c": None, "ph": None, "ec_mscm": None, "updated_ts": None}
        return {
            "temperature_c": effective["temperature_c"],
            "ph": effective["ph"],
            "ec_mscm": effective["ec_mscm"],
            "online": not is_stale,
            "ts": dt.datetime.utcfromtimestamp(row["ts"]).isoformat() + "Z",
            "age_sec": age_sec,
            "errors": {"stale": f"reading is {age_sec}s old"} if is_stale else {},
            "overrides": overrides,
            "original_temperature_c": original["temperature_c"],
            "original_ph": original["ph"],
            "original_ec_mscm": original["ec_mscm"],
        }
    except Exception as e:
        logger.error(f"Failed to read sensors from DB: {e}", exc_info=True)
        return {
            "temperature_c": None, "ph": None, "ec_mscm": None,
            "online": False, "ts": None, "age_sec": None,
            "errors": {"db": str(e)}
        }
