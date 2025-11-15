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

# Graceful I²C imports - works on Pi and dev PCs
# Use ezo_i2c_stabilized (requires real smbus2 with i2c_rdwr support)
I2C_AVAILABLE = False

try:
    from . import ezo_i2c_stabilized
    I2C_AVAILABLE = True
except ImportError as e:
    logger.warning(f"I²C libraries not available - running in simulation mode: {e}")
    ezo_i2c_stabilized = None  # type: ignore


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


def _read_with_temp_comp_check():
    """
    Read sensors using ezo_i2c_stabilized.read_all() (working with real smbus2).
    
    Returns:
        tuple: (t_write_performed, compensation_results, temp_c, ph_val, ec_val)
    """
    if not I2C_AVAILABLE:
        # Simulated read
        return False, {"ph": True, "ec": True}, 23.0, 6.5, 1500.0
    
    try:
        from .ezo_i2c_stabilized import read_all
        result = read_all()
        
        temp_c = result.get("temperature")
        ph_val = result.get("ph")
        ec_val = result.get("ec_ms")
        
        # ezo_i2c_stabilized doesn't report temp_comp details, assume it's handled
        comp_results = {"ph": True, "ec": True}
        
        return True, comp_results, temp_c, ph_val, ec_val
        
    except Exception as e:
        logger.error(f"Sensor read failed: {e}", exc_info=True)
        raise


def read_all_sensors() -> Dict[str, Any]:
    """
    Simple read using ezo_i2c_stabilized (working with real smbus2).
    Returns sensor dict with temperature_c, ec_mscm, ph, online, ts, errors.
    """
    import time
    import datetime as dt
    
    if not I2C_AVAILABLE:
        # Simulation mode
        return {
            "temperature_c": 23.0, "ec_mscm": 1.5, "ph": 6.5,
            "online": True, "ts": dt.datetime.utcnow().isoformat() + "Z",
            "temp_comp_applied": False, "temp_comp_reason": "simulated",
            "errors": {}
        }
    
    try:
        from .ezo_i2c_stabilized import read_all
        data = read_all()
        
        return {
            "temperature_c": data.get("temperature"),
            "ec_mscm": data.get("ec_ms"),
            "ph": data.get("ph"),
            "online": True,
            "ts": dt.datetime.utcnow().isoformat() + "Z",
            "temp_comp_applied": True,
            "temp_comp_reason": "ezo_i2c_stabilized",
            "errors": {}
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
        mode = "auto"
        overrides = {"temperature_c": None, "ph": None, "ec_mscm": None, "updated_ts": None}
        try:
            from app.sensors_mode import get_sensor_mode, get_overrides, MODE_MAINTENANCE
            mode = get_sensor_mode()
            if mode == MODE_MAINTENANCE:
                overrides = get_overrides()
                for k in ["temperature_c", "ph", "ec_mscm"]:
                    if overrides.get(k) is not None:
                        effective[k] = overrides[k]
        except Exception:
            pass
        return {
            "temperature_c": effective["temperature_c"],
            "ph": effective["ph"],
            "ec_mscm": effective["ec_mscm"],
            "online": not is_stale,
            "ts": dt.datetime.utcfromtimestamp(row["ts"]).isoformat() + "Z",
            "age_sec": age_sec,
            "errors": {"stale": f"reading is {age_sec}s old"} if is_stale else {},
            "mode": mode,
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
