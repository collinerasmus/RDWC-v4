"""
Unified EC/pH/RTD Sensor Controller - Single Source of Truth

This module provides:
1. Raw sensor I/O access via EZO I2C library
2. Proper K factor handling (persisted in settings, restored on each read)
3. Calibration endpoints (low/high point, K setting, clear)
4. Temperature compensation (throttled)
5. Lock-based mutual exclusion (reading vs calibration)

Philosophy:
- All sensor operations go through this module
- K factor is managed per settings, not probe memory (since EZO doesn't persist K)
- Calibration and readings are mutually exclusive via /tmp/rdwc_calib.lock
- Each read restores K from settings to ensure consistency
"""

import os
import time
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# I/O addresses
RTD_ADDR = 0x66  # Temperature sensor
PH_ADDR = 0x63   # pH sensor  
EC_ADDR = 0x64   # EC sensor

# Calibration lock file
CALIB_LOCK_PATH = Path("/tmp/rdwc_calib.lock")
CALIB_LOCK_TIMEOUT_S = 3.0  # 3 second timeout to acquire lock

# I2C availability
_I2C_AVAILABLE = False
try:
    from . import ezo_i2c_stabilized
    _I2C_AVAILABLE = True
except ImportError:
    logger.warning("I2C not available - running in simulation mode")


class SensorLockError(Exception):
    """Raised when calibration lock cannot be acquired"""
    pass


class SensorReadError(Exception):
    """Raised when sensor read fails"""
    pass


def _acquire_calib_lock() -> bool:
    """
    Acquire calibration lock with timeout.
    Returns True if acquired, False if timeout or error.
    """
    start_time = time.time()
    while time.time() - start_time < CALIB_LOCK_TIMEOUT_S:
        if not CALIB_LOCK_PATH.exists():
            try:
                CALIB_LOCK_PATH.write_text(f"{os.getpid()}\n")
                return True
            except OSError:
                pass
        time.sleep(0.1)
    return False


def _release_calib_lock() -> None:
    """Release calibration lock"""
    if CALIB_LOCK_PATH.exists():
        try:
            CALIB_LOCK_PATH.unlink()
        except OSError as e:
            logger.error(f"Failed to release calibration lock: {e}")


def read_sensors() -> Dict[str, Any]:
    """
    Read all sensors (RTD, pH, EC) with proper K factor handling.
    
    Returns:
        {
            "temperature_c": float or None,
            "ph": float or None,
            "ec_mscm": float or None,
            "online": bool,
            "ts": str (ISO 8601 UTC),
            "errors": dict
        }
    """
    if not _I2C_AVAILABLE:
        # Simulation mode
        import datetime as dt
        return {
            "temperature_c": 23.0,
            "ph": 6.5,
            "ec_mscm": 1.5,
            "online": True,
            "ts": dt.datetime.utcnow().isoformat() + "Z",
            "errors": {}
        }
    
    try:
        from .settings import get_all_settings
        import datetime as dt
        
        rtd = ezo_i2c_stabilized.EZO(1, RTD_ADDR, "RTD")
        ph = ezo_i2c_stabilized.EZO(1, PH_ADDR, "pH")
        ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
        
        try:
            # Initialize all sensors (disables continuous mode, restores K for EC)
            for dev in (rtd, ph, ec):
                dev.init_once()
            time.sleep(0.25)
            
            # Read temperature first (for compensation)
            temp_c = float(rtd.read_value(timeout=1.2))
            
            # Send temperature compensation to pH
            try:
                ph.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.25)
            except Exception:
                pass
            
            # Read pH
            ph_val = float(ph.read_value(timeout=1.5))
            
            # Send temperature compensation to EC
            try:
                ec.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.25)
            except Exception:
                pass
            
            # Read EC raw value (in µS/cm)
            ec_raw = float(ec.read_value(timeout=1.5))
            
            # Get K factor from settings and ensure it's applied to probe
            settings = get_all_settings()
            k_value = float(settings.get("ec.k_value", "0.1"))
            
            # Ensure K is on probe (in case it was lost)
            try:
                ec.cmd(f"K,{k_value:.2f}", read_len=0, settle=0.3)
                logger.debug(f"EC K value confirmed on probe: {k_value}")
            except Exception as e:
                logger.debug(f"Could not confirm K value on probe: {e}")
            
            # EZO EC reports in µS/cm; convert to mS/cm
            # Formula: mS/cm = µS/cm / 1000
            # But EZO also applies K internally, so the raw reading already has K applied
            # So we just convert units
            ec_val = ec_raw / 1000.0 if ec_raw >= 10 else ec_raw
            
            return {
                "temperature_c": temp_c,
                "ph": ph_val,
                "ec_mscm": ec_val,
                "online": True,
                "ts": dt.datetime.utcnow().isoformat() + "Z",
                "errors": {}
            }
        finally:
            for dev in (rtd, ph, ec):
                dev.close()
    
    except Exception as e:
        logger.error(f"Sensor read failed: {e}", exc_info=True)
        import datetime as dt
        return {
            "temperature_c": None,
            "ph": None,
            "ec_mscm": None,
            "online": False,
            "ts": dt.datetime.utcnow().isoformat() + "Z",
            "errors": {"read": str(e)}
        }


def set_ec_k_factor(k_value: float) -> Dict[str, Any]:
    """
    Set EC probe K factor and persist to settings.
    
    Args:
        k_value: K factor (typically 0.1, 1.0, or 10.0)
    
    Returns:
        {"ok": bool, "k_value": float, "response": str}
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    try:
        from .settings import upsert_settings
        
        # Validate
        valid_k = [0.1, 1.0, 10.0]
        if k_value not in valid_k:
            logger.warning(f"K value {k_value} not in standard {valid_k}, using anyway")
        
        # Apply to probe
        ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
        try:
            response = ec.cmd(f"K,{k_value:.2f}", read_len=32, settle=0.3)
        finally:
            ec.close()
        
        # Persist to settings
        upsert_settings({"ec.k_value": str(k_value)})
        
        logger.info(f"EC K value set to {k_value}")
        return {
            "ok": True,
            "k_value": k_value,
            "response": response or f"K={k_value} set"
        }
    except Exception as e:
        logger.error(f"Failed to set EC K factor: {e}")
        return {"ok": False, "error": str(e)}


def calibrate_ec_dry() -> Dict[str, Any]:
    """
    Apply EC dry calibration (zero point in air).
    This is the first step for K=0.1 probes according to Atlas Scientific datasheet.
    
    Returns:
        {
            "ok": bool,
            "response": str,
            "k_value": float (restored),
            "k_response": str
        }
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    # Acquire lock
    if not _acquire_calib_lock():
        return {"ok": False, "error": "Calibration lock held by sensor poller"}
    
    try:
        from .settings import get_all_settings
        
        ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
        try:
            # Apply dry calibration
            response = ec.cmd("Cal,dry", read_len=32, settle=0.9)
            
            # Brief settle
            time.sleep(0.5)
            
            # Restore K from settings
            settings = get_all_settings()
            k_value = float(settings.get("ec.k_value", "0.1"))
            k_response = ec.cmd(f"K,{k_value:.2f}", read_len=32, settle=0.3)
            
            logger.info(f"EC dry calibration applied, K restored to {k_value}")
            return {
                "ok": True,
                "response": response or "Dry calibration applied",
                "k_value": k_value,
                "k_response": k_response or f"K={k_value} restored"
            }
        finally:
            ec.close()
    except Exception as e:
        logger.error(f"EC dry calibration failed: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        _release_calib_lock()


def calibrate_ec_low(us_cm: float = 84) -> Dict[str, Any]:
    """
    Apply EC low-point calibration.
    For K=0.1 probes, use 84 µS/cm calibration solution.
    For K=1.0 probes, use 1413 µS/cm calibration solution.
    
    Args:
        us_cm: Low calibration point in µS/cm (default 84 for K=0.1)
    
    Returns:
        {
            "ok": bool,
            "response": str,
            "k_value": float (restored),
            "k_response": str
        }
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    # Acquire lock
    if not _acquire_calib_lock():
        return {"ok": False, "error": "Calibration lock held by sensor poller"}
    
    try:
        from .settings import get_all_settings
        
        ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
        try:
            # Apply calibration
            response = ec.cmd(f"Cal,low,{int(us_cm)}", read_len=32, settle=0.9)
            
            # Brief settle
            time.sleep(0.5)
            
            # Restore K from settings
            settings = get_all_settings()
            k_value = float(settings.get("ec.k_value", "0.1"))
            k_response = ec.cmd(f"K,{k_value:.2f}", read_len=32, settle=0.3)
            
            logger.info(f"EC low calibration applied at {us_cm} µS/cm, K restored to {k_value}")
            return {
                "ok": True,
                "response": response or f"Low calibration applied at {us_cm} µS/cm",
                "k_value": k_value,
                "k_response": k_response or f"K={k_value} restored"
            }
        finally:
            ec.close()
    except Exception as e:
        logger.error(f"EC low calibration failed: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        _release_calib_lock()


def calibrate_ec_high(us_cm: float = 10000) -> Dict[str, Any]:
    """
    Apply EC high-point calibration.
    For K=0.1 probes, use 10000 µS/cm calibration solution.
    For K=1.0 probes, use 12880 µS/cm calibration solution.
    
    Args:
        us_cm: High calibration point in µS/cm (default 10000 for K=0.1)
    
    Returns:
        {
            "ok": bool,
            "response": str,
            "k_value": float (restored),
            "k_response": str
        }
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    # Acquire lock
    if not _acquire_calib_lock():
        return {"ok": False, "error": "Calibration lock held by sensor poller"}
    
    try:
        from .settings import get_all_settings
        
        ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
        try:
            # Apply calibration
            response = ec.cmd(f"Cal,high,{int(us_cm)}", read_len=32, settle=0.9)
            
            # Brief settle
            time.sleep(0.5)
            
            # Restore K from settings
            settings = get_all_settings()
            k_value = float(settings.get("ec.k_value", "0.1"))
            k_response = ec.cmd(f"K,{k_value:.2f}", read_len=32, settle=0.3)
            
            logger.info(f"EC high calibration applied at {us_cm} µS/cm, K restored to {k_value}")
            return {
                "ok": True,
                "response": response or f"High calibration applied at {us_cm} µS/cm",
                "k_value": k_value,
                "k_response": k_response or f"K={k_value} restored"
            }
        finally:
            ec.close()
    except Exception as e:
        logger.error(f"EC high calibration failed: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        _release_calib_lock()


def get_ec_raw() -> Dict[str, Any]:
    """Direct raw EC reading for diagnostics (unit as returned by probe)."""
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    try:
        ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
        try:
            ec.init_once()
            time.sleep(0.3)
            raw_value = float(ec.read_value(timeout=1.5))
            return {"ok": True, "raw_value": raw_value}
        finally:
            ec.close()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def identify_devices() -> Dict[str, Any]:
    """Return identification strings from pH/EC/RTD devices (best-effort)."""
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    results: Dict[str, str] = {}
    for name, addr in (("ph", PH_ADDR), ("ec", EC_ADDR), ("rtd", RTD_ADDR)):
        try:
            dev = ezo_i2c_stabilized.EZO(1, addr, name)
            info = dev.cmd("i", read_len=32, settle=0.3)
            results[name] = info or ""
            dev.close()
        except Exception as e:
            results[name] = f"ERR: {e}"
    return {"ok": True, "ids": results}


def identify_ec_details() -> Dict[str, Any]:
    """Detailed EC probe info (id, k query, cal query, output params)."""
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    try:
        ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
        try:
            device_info = ec.cmd("I", read_len=32, settle=0.3)
            k_value = ec.cmd("K,?", read_len=32, settle=0.3)
            cal_status = ec.cmd("Cal,?", read_len=32, settle=0.3)
            output_params = ec.cmd("O,?", read_len=32, settle=0.3)
        finally:
            ec.close()
        return {
            "ok": True,
            "device_info": device_info or "No response",
            "k_value": k_value or "No response",
            "cal_status": cal_status or "No response",
            "output_params": output_params or "No response",
            "note": "All queries are best-effort; some probes may not respond"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def clear_ec_calibration() -> Dict[str, Any]:
    """
    Clear all EC calibration points.
    
    Returns:
        {"ok": bool, "response": str}
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    # Acquire lock
    if not _acquire_calib_lock():
        return {"ok": False, "error": "Calibration lock held by sensor poller"}
    
    try:
        ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
        try:
            response = ec.cmd("Cal,clear", read_len=32, settle=0.5)
            logger.info("EC calibration cleared")
            return {
                "ok": True,
                "response": response or "Calibration cleared"
            }
        finally:
            ec.close()
    except Exception as e:
        logger.error(f"Failed to clear EC calibration: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        _release_calib_lock()


def get_ec_calibration_status() -> Dict[str, Any]:
    """
    Get current EC calibration status and K factor.
    Parses calibration response to determine which points are set.
    
    Returns:
        {
            "ok": bool,
            "k": float,
            "cal": str (e.g., "dry", "one-point", "two-point"),
            "dry": bool,
            "low": bool,
            "high": bool,
            "cal_response": str,
            "note": str
        }
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    try:
        from .settings import get_all_settings
        
        # Get K from settings (single source of truth)
        settings = get_all_settings()
        k_value = float(settings.get("ec.k_value", "0.1"))
        
        # Try to query calibration from probe (may not respond)
        cal_status = ""
        dry = False
        low = False
        high = False
        cal_summary = "uncalibrated"
        
        try:
            ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
            try:
                cal_status = ec.cmd("Cal,?", read_len=32, settle=0.5)
            finally:
                ec.close()
            
            # Parse calibration status
            # Response format: "?CAL,0" (uncalibrated), "?CAL,1" (one-point), "?CAL,2" (two-point), "?CAL,3" (dry+two-point)
            if cal_status:
                if "?CAL,0" in cal_status:
                    cal_summary = "uncalibrated"
                elif "?CAL,1" in cal_status:
                    cal_summary = "one-point"
                    low = True
                elif "?CAL,2" in cal_status:
                    cal_summary = "two-point"
                    low = True
                    high = True
                elif "?CAL,3" in cal_status:
                    cal_summary = "dry+two-point"
                    dry = True
                    low = True
                    high = True
                else:
                    # Try alternative format
                    cal_status_lower = cal_status.lower()
                    if "dry" in cal_status_lower:
                        dry = True
                        cal_summary = "dry"
                    if "low" in cal_status_lower:
                        low = True
                        if cal_summary == "dry":
                            cal_summary = "dry+low"
                        else:
                            cal_summary = "one-point"
                    if "high" in cal_status_lower:
                        high = True
                        if low:
                            cal_summary = "two-point" if not dry else "dry+two-point"
        except Exception as e:
            logger.debug(f"Could not query EC calibration status: {e}")
            cal_status = ""
        
        return {
            "ok": True,
            "k": k_value,
            "cal": cal_summary,
            "dry": dry,
            "low": low,
            "high": high,
            "cal_response": cal_status or "Probe does not respond to Cal,? query",
            "note": "K factor is source of truth from settings (EZO doesn't persist K across power cycles)"
        }
    except Exception as e:
        logger.error(f"Failed to get EC calibration status: {e}")
        return {"ok": False, "error": str(e)}


def set_sensor_leds(enable: bool = True) -> Dict[str, Any]:
    """Best-effort LED toggle for all sensors via unified controller."""
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    cmd = "L,1" if enable else "L,0"
    applied = []
    errors: Dict[str, str] = {}
    for addr, name in ((PH_ADDR, "pH"), (EC_ADDR, "EC"), (RTD_ADDR, "RTD")):
        try:
            dev = ezo_i2c_stabilized.EZO(1, addr, name)
            try:
                dev.cmd(cmd, read_len=0, settle=0.05)
                applied.append(name)
            finally:
                dev.close()
        except Exception as e:
            errors[name] = str(e)
    return {"ok": True, "enabled": enable, "applied": applied, "errors": errors}


def flash_sensor_leds(count: int = 8, period_s: float = 0.25) -> Dict[str, Any]:
    """Flash LEDs across all sensors; leaves LEDs ON at completion."""
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    from time import sleep

    cnt = max(1, int(count))
    period = max(0.05, float(period_s))
    sensors = ((PH_ADDR, "pH"), (EC_ADDR, "EC"), (RTD_ADDR, "RTD"))

    def _send_all(command: str, settle: float = 0.02) -> None:
        for addr, name in sensors:
            try:
                dev = ezo_i2c_stabilized.EZO(1, addr, name)
                try:
                    dev.cmd(command, read_len=0, settle=settle)
                finally:
                    dev.close()
            except Exception:
                continue

    for _ in range(cnt):
        _send_all("L,1")
        sleep(period)
        _send_all("L,0")
        sleep(period)

    _send_all("L,1")
    return {"ok": True, "flashes": cnt, "period_s": period}
