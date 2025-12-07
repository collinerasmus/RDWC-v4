"""
Unified EC/pH/RTD Sensor Controller - Single Source of Truth

This module provides:
1. Raw sensor I/O access via EZO I2C library
2. Proper K factor handling (persisted in settings, restored on each read)
3. Calibration endpoints (low/high point, K setting, clear)
4. Temperature compensation (throttled)
5. Lock-based mutual exclusion (reading vs calibration AND read vs read)

Philosophy:
- All sensor operations go through this module - NO OTHER MODULE ACCESSES I2C DIRECTLY
- K factor is managed per settings, not probe memory (since EZO doesn't persist K)
- Calibration and readings are mutually exclusive via /tmp/rdwc_calib.lock
- All reads are serialized via threading.Lock to prevent concurrent I2C access
- Each read restores K from settings to ensure consistency
"""

import os
import time
import logging
import threading
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# I/O addresses
RTD_ADDR = 0x66  # Temperature sensor
PH_ADDR = 0x63   # pH sensor  
EC_ADDR = 0x64   # EC sensor

# Mutex for read-to-read mutual exclusion (prevents concurrent I2C access)
_READ_MUTEX = threading.Lock()

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
    
    CRITICAL: Acquires _READ_MUTEX to serialize I2C access.
    All sensor reads go through this function to prevent race conditions.
    
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
    # Acquire read mutex to prevent concurrent I2C access
    with _READ_MUTEX:
        return _read_sensors_locked()


def _read_sensors_locked() -> Dict[str, Any]:
    """
    Internal sensor read implementation (called while holding _READ_MUTEX).
    
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


def get_sensor_status() -> Dict[str, Any]:
    """
    Get current sensor status without taking a full read.
    Used by status endpoints to avoid interfering with calibration.
    
    Returns latest cached reading or last-known online status.
    """
    # Just return a simple status - if we can read, devices are online
    try:
        result = read_sensors()
        return {
            "online": result.get("online", False),
            "ts": result.get("ts"),
            "age_seconds": 0
        }
    except Exception as e:
        logger.debug(f"get_sensor_status error: {e}")
        return {"online": False, "error": str(e)}


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
    
    CRITICAL: EZO EC probes lose calibration on power cycle. This function:
    1. Sends calibration command to probe (stored in probe RAM)
    2. Stores calibration status in database (persists across power cycles)
    3. On next init, calibration is re-applied to probe from database
    
    Returns:
        {
            "ok": bool,
            "response": str,
            "k_value": float (restored),
            "k_response": str,
            "persisted": bool (whether saved to database)
        }
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    # Acquire BOTH read mutex AND calibration lock for exclusive I2C access
    if not _READ_MUTEX.acquire(timeout=3.0):
        return {"ok": False, "error": "Could not acquire I2C access (another operation in progress)"}
    
    try:
        if not _acquire_calib_lock():
            return {"ok": False, "error": "Calibration lock held by sensor poller"}
        
        try:
            from .settings import get_all_settings, upsert_settings
            
            ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
            try:
                # Ensure continuous mode is OFF before calibration
                ec.cmd("C,0", read_len=0, settle=0.3)
                time.sleep(0.5)
                
                # Retry dry calibration up to 3 times with much longer settle
                # EC probes can take 3-5 seconds to process calibration commands
                success = False
                last_error = None
                for attempt in range(3):
                    logger.info(f"EC dry calibration attempt {attempt + 1}/3")
                    success = ec.calibration_cmd("Cal,dry", settle=5.0)  # Increased to 5 seconds
                    if success:
                        break
                    time.sleep(2.0)  # Wait between retries
                
                if not success:
                    return {"ok": False, "error": "Dry calibration command not acknowledged by probe after 3 attempts - ensure probe is completely dry and in air"}
                
                logger.info("EC dry calibration applied to probe")
                # CRITICAL: Give probe time to settle after calibration
                time.sleep(2.0)
                
                # Get K value - store it in probe BEFORE persisting calibration flag
                settings = get_all_settings()
                k_value = float(settings.get("ec.k_value", "0.1"))
                
                # Set K value on probe (do this BEFORE marking as calibrated)
                k_response = ec.cmd(f"K,{k_value:.2f}", read_len=32, settle=0.5)
                time.sleep(0.5)
                
                # PERSIST: Store calibration status to database (survives power cycles)
                upsert_settings({"ec.cal_dry": "1"})
                logger.info("EC dry calibration persisted to database")
                
                # Final stabilization before releasing lock
                time.sleep(1.0)
                
                return {
                    "ok": True,
                    "response": "Dry calibration applied and persisted",
                    "k_value": k_value,
                    "k_response": k_response or f"K={k_value} set",
                    "persisted": True
                }
            finally:
                ec.close()
        except Exception as e:
            logger.error(f"EC dry calibration failed: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            _release_calib_lock()
    finally:
        _READ_MUTEX.release()


def calibrate_ec_low(us_cm: float = None) -> Dict[str, Any]:
    """
    Apply EC low-point calibration.
    Automatically selects default based on current K value:
    - K=0.1: 84 µS/cm (default)
    - K=1.0: 1413 µS/cm
    - K=10.0: 12880 µS/cm
    
    CRITICAL: EZO EC probes lose calibration on power cycle. This function:
    1. Sends calibration command to probe (stored in probe RAM)
    2. Stores calibration point value in database (persists across power cycles)
    3. On next init, calibration is re-applied to probe from database
    
    Args:
        us_cm: Low calibration point in µS/cm (None to use K-based default)
    
    Returns:
        {
            "ok": bool,
            "response": str,
            "k_value": float (restored),
            "k_response": str,
            "persisted": bool (whether saved to database)
        }
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    # Acquire BOTH read mutex AND calibration lock for exclusive I2C access
    if not _READ_MUTEX.acquire(timeout=3.0):
        return {"ok": False, "error": "Could not acquire I2C access (another operation in progress)"}
    
    try:
        if not _acquire_calib_lock():
            return {"ok": False, "error": "Calibration lock held by sensor poller"}
        
        try:
            from .settings import get_all_settings, upsert_settings
            
            # Get K value to determine default calibration value
            settings = get_all_settings()
            k_value = float(settings.get("ec.k_value", "0.1"))
            
            # Auto-select calibration value based on K if not specified
            if us_cm is None:
                if k_value == 0.1:
                    us_cm = 84
                elif k_value == 1.0:
                    us_cm = 1413
                elif k_value == 10.0:
                    us_cm = 12880
                else:
                    # Unknown K, default to K=0.1 value
                    us_cm = 84
            
            us_cm = int(us_cm)  # Ensure integer for calibration point
            
            ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
            try:
                # Ensure continuous mode OFF
                ec.cmd("C,0", read_len=0, settle=0.3)
                time.sleep(0.5)
                
                # Send low calibration command with VERY long settle (10 seconds for probe to process)
                # Some EC probes take time to acknowledge calibration
                success = ec.calibration_cmd(f"Cal,low,{us_cm}", settle=10.0)
                
                if not success:
                    return {"ok": False, "error": f"Low calibration command not acknowledged - ensure probe is in {us_cm} µS/cm solution and probe K value is set correctly. Also check I2C communication."}
                
                logger.info(f"EC low calibration applied at {us_cm} µS/cm to probe")
                # CRITICAL: Give probe time to settle after calibration
                time.sleep(2.0)
                
                # Set K value on probe (do this BEFORE persisting calibration point)
                k_response = ec.cmd(f"K,{k_value:.2f}", read_len=32, settle=0.5)
                time.sleep(0.5)
                
                # PERSIST: Store calibration point to database (survives power cycles)
                upsert_settings({"ec.cal_low_us": str(us_cm)})
                logger.info(f"EC low calibration point {us_cm} µS/cm persisted to database")
                
                # Final stabilization before releasing lock
                time.sleep(1.0)
                
                return {
                    "ok": True,
                    "response": f"Low calibration applied at {us_cm} µS/cm and persisted",
                    "k_value": k_value,
                    "k_response": k_response or f"K={k_value} set",
                    "persisted": True
                }
            finally:
                ec.close()
        except Exception as e:
            logger.error(f"EC low calibration failed: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            _release_calib_lock()
    finally:
        _READ_MUTEX.release()


def calibrate_ec_high(us_cm: float = None) -> Dict[str, Any]:
    """
    Apply EC high-point calibration.
    Automatically selects default based on current K value:
    - K=0.1: 1413 µS/cm (standard two-point with 84 low)
    - K=1.0: 12880 µS/cm
    - K=10.0: 80000 µS/cm
    
    CRITICAL: EZO EC probes lose calibration on power cycle. This function:
    1. Sends calibration command to probe (stored in probe RAM)
    2. Stores calibration point value in database (persists across power cycles)
    3. On next init, calibration is re-applied to probe from database
    
    Args:
        us_cm: High calibration point in µS/cm (None to use K-based default)
    
    Returns:
        {
            "ok": bool,
            "response": str,
            "k_value": float (restored),
            "k_response": str,
            "persisted": bool (whether saved to database)
        }
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    # Acquire BOTH read mutex AND calibration lock for exclusive I2C access
    if not _READ_MUTEX.acquire(timeout=3.0):
        return {"ok": False, "error": "Could not acquire I2C access (another operation in progress)"}
    
    try:
        if not _acquire_calib_lock():
            return {"ok": False, "error": "Calibration lock held by sensor poller"}
        
        try:
            from .settings import get_all_settings, upsert_settings
            
            # Get K value to determine default calibration value
            settings = get_all_settings()
            k_value = float(settings.get("ec.k_value", "0.1"))
            
            # Auto-select calibration value based on K if not specified
            if us_cm is None:
                if k_value == 0.1:
                    us_cm = 1413
                elif k_value == 1.0:
                    us_cm = 12880
                elif k_value == 10.0:
                    us_cm = 80000
                else:
                    # Unknown K, default to K=0.1 value
                    us_cm = 1413
            
            us_cm = int(us_cm)  # Ensure integer for calibration point
            
            ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
            try:
                # Ensure continuous mode OFF
                ec.cmd("C,0", read_len=0, settle=0.3)
                time.sleep(0.3)
                
                # Send high calibration command and verify success
                success = ec.calibration_cmd(f"Cal,high,{us_cm}", settle=1.5)
                
                if not success:
                    return {"ok": False, "error": f"High calibration command not acknowledged - ensure probe is in {us_cm} µS/cm solution"}
                
                logger.info(f"EC high calibration applied at {us_cm} µS/cm to probe")
                # CRITICAL: Give probe time to settle after calibration
                time.sleep(2.0)
                
                # Set K value on probe (do this BEFORE persisting calibration point)
                k_response = ec.cmd(f"K,{k_value:.2f}", read_len=32, settle=0.5)
                time.sleep(0.5)
                
                # PERSIST: Store calibration point to database (survives power cycles)
                upsert_settings({"ec.cal_high_us": str(us_cm)})
                logger.info(f"EC high calibration point {us_cm} µS/cm persisted to database")
                
                # Final stabilization before releasing lock
                time.sleep(1.0)
                
                return {
                    "ok": True,
                    "response": f"High calibration applied at {us_cm} µS/cm and persisted",
                    "k_value": k_value,
                    "k_response": k_response or f"K={k_value} set",
                    "persisted": True
                }
            finally:
                ec.close()
        except Exception as e:
            logger.error(f"EC high calibration failed: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            _release_calib_lock()
    finally:
        _READ_MUTEX.release()


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
    Clear all EC calibration points from both probe and database.
    
    Returns:
        {"ok": bool, "response": str}
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    # Acquire BOTH read mutex AND calibration lock for exclusive I2C access
    if not _READ_MUTEX.acquire(timeout=3.0):
        return {"ok": False, "error": "Could not acquire I2C access (another operation in progress)"}
    
    try:
        if not _acquire_calib_lock():
            return {"ok": False, "error": "Calibration lock held by sensor poller"}
        
        try:
            from .settings import upsert_settings
            
            ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
            try:
                response = ec.cmd("Cal,clear", read_len=32, settle=0.5)
                logger.info("EC calibration cleared from probe")
                
                # CRITICAL: Also clear persisted calibration data from database
                upsert_settings({
                    "ec.cal_dry": "0",
                    "ec.cal_low_us": "0",
                    "ec.cal_high_us": "0"
                })
                logger.info("EC calibration cleared from database")
                
                return {
                    "ok": True,
                    "response": response or "Calibration cleared from probe and database"
                }
            finally:
                ec.close()
        except Exception as e:
            logger.error(f"Failed to clear EC calibration: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            _release_calib_lock()
    finally:
        _READ_MUTEX.release()


def get_ec_calibration_status() -> Dict[str, Any]:
    """
    Get current EC calibration status and K factor.
    Reads calibration state from BOTH probe (RAM) and database (persistent).
    Preferred source is database since probe loses calibration on power cycle.
    
    Returns:
        {
            "ok": bool,
            "k": float,
            "cal": str (e.g., "dry", "one-point", "two-point"),
            "dry": bool,
            "low": bool,
            "high": bool,
            "low_us": int (persisted low calibration point),
            "high_us": int (persisted high calibration point),
            "cal_response": str (from probe query),
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
        
        # Read calibration status from DATABASE (most reliable source)
        dry_db = settings.get("ec.cal_dry", "0") == "1"
        low_db = settings.get("ec.cal_low_us", "0") != "0"
        high_db = settings.get("ec.cal_high_us", "0") != "0"
        low_us_db = int(settings.get("ec.cal_low_us", "0")) if low_db else 0
        high_us_db = int(settings.get("ec.cal_high_us", "0")) if high_db else 0
        
        # Also try to query calibration from probe (may not respond if powered down)
        cal_status = ""
        dry_probe = False
        low_probe = False
        high_probe = False
        cal_summary = "uncalibrated"
        
        try:
            ec = ezo_i2c_stabilized.EZO(1, EC_ADDR, "EC")
            try:
                cal_status = ec.cmd("Cal,?", read_len=32, settle=0.5)
            finally:
                ec.close()
            
            # Parse calibration status from probe
            # Response format: "?CAL,0" (uncalibrated), "?CAL,1" (one-point), "?CAL,2" (two-point), "?CAL,3" (dry+two-point)
            if cal_status:
                if "?CAL,0" in cal_status:
                    pass  # uncalibrated
                elif "?CAL,1" in cal_status:
                    low_probe = True
                elif "?CAL,2" in cal_status:
                    low_probe = True
                    high_probe = True
                elif "?CAL,3" in cal_status:
                    dry_probe = True
                    low_probe = True
                    high_probe = True
                else:
                    # Try alternative format
                    cal_status_lower = cal_status.lower()
                    if "dry" in cal_status_lower:
                        dry_probe = True
                    if "low" in cal_status_lower:
                        low_probe = True
                    if "high" in cal_status_lower:
                        high_probe = True
        except Exception as e:
            logger.debug(f"Could not query EC probe calibration status: {e}")
            cal_status = "Probe not responding"
        
        # Determine final status: prefer DATABASE over probe (since probe loses it on power cycle)
        dry = dry_db
        low = low_db
        high = high_db
        
        # Build summary
        if dry and low and high:
            cal_summary = "dry+two-point (persisted)"
        elif dry and low:
            cal_summary = "dry+low (persisted)"
        elif low and high:
            cal_summary = "two-point (persisted)"
        elif low:
            cal_summary = "one-point/low (persisted)"
        elif dry:
            cal_summary = "dry only (persisted)"
        else:
            cal_summary = "uncalibrated"
        
        return {
            "ok": True,
            "k": k_value,
            "cal": cal_summary,
            "dry": dry,
            "low": low,
            "high": high,
            "low_us": low_us_db,
            "high_us": high_us_db,
            "cal_response": cal_status or "Probe does not respond to Cal,? query",
            "probe_dry": dry_probe,
            "probe_low": low_probe,
            "probe_high": high_probe,
            "note": "Status is read from database (persists across power cycles). Probe RAM is lost on power cycle - calibration will be restored on next sensor init."
        }
    except Exception as e:
        logger.error(f"Failed to get EC calibration status: {e}")
        return {"ok": False, "error": str(e)}
        
        return {
            "ok": True,
            "k": k_value,
            "cal": cal_summary,
            "dry": dry,
            "low": low,
            "high": high,
            "cal_response": cal_status or "Probe does not respond to Cal,? query",
            "probe_dry": dry_probe,
            "probe_low": low_probe,
            "probe_high": high_probe,
            "note": "Status is read from database (persists across power cycles). Probe RAM is lost on power cycle - calibration will be restored on next sensor init."
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


# ==================== pH Calibration Functions ====================


def read_ph_single() -> Dict[str, Any]:
    """
    Perform a single locked pH reading for calibration UI.
    Uses dual locks: _READ_MUTEX (I2C serialization) + _acquire_calib_lock (poller coordination).
    
    Returns:
        {"ok": bool, "value": float, "note": str}
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "note": "HardwareUnavailable"}
    
    # Acquire I2C mutex first
    if not _READ_MUTEX.acquire(timeout=3.0):
        return {"ok": False, "note": "Could not acquire I2C access; sensor read in progress"}
    try:
        # Then acquire calibration lock
        if not _acquire_calib_lock():
            return {"ok": False, "note": "Calibration lock held by sensor poller"}
        
        try:
            # Wait for any in-flight sensor read to complete
            time.sleep(1.0)
            
            ph = ezo_i2c_stabilized.EZO(1, PH_ADDR, "pH")
            try:
                # Disable continuous mode
                ph.cmd("C,0", read_len=0, settle=0.3)
                
                # Retry read up to 3 times
                for attempt in range(3):
                    try:
                        value_str = ph.read_value(timeout=3.0)
                        if value_str:
                            # Parse first token (pH value)
                            val = float(value_str.split(",")[0].strip())
                            return {"ok": True, "value": round(val, 3)}
                    except Exception as e:
                        logger.debug(f"pH read attempt {attempt + 1} failed: {e}")
                        if attempt < 2:
                            time.sleep(0.5)
                
                return {"ok": False, "note": "NoData"}
            finally:
                ph.close()
        except Exception as e:
            logger.error(f"pH single read failed: {e}")
            return {"ok": False, "note": str(e)}
        finally:
            _release_calib_lock()
    finally:
        _READ_MUTEX.release()


def read_ph_stable(timeout_s: float = 25.0, delta: float = 0.03, 
                   min_samples: int = 4, poll_s: float = 2.0) -> Dict[str, Any]:
    """
    Wait for pH reading to stabilize.
    
    Args:
        timeout_s: Maximum time to wait for stability
        delta: Maximum allowed difference between consecutive readings
        min_samples: Minimum number of samples before declaring stable
        poll_s: Time between samples
        
    Returns:
        {
            "ok": bool,
            "stable": bool,
            "value": float or None,
            "samples": int,
            "duration_s": float
        }
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "stable": False, "note": "HardwareUnavailable"}
    
    start_time = time.time()
    readings = []
    
    while time.time() - start_time < timeout_s:
        result = read_ph_single()
        
        if not result.get("ok"):
            # If hardware unavailable, exit immediately
            if "HardwareUnavailable" in result.get("note", ""):
                return {
                    "ok": False,
                    "stable": False,
                    "note": "HardwareUnavailable",
                    "samples": len(readings),
                    "duration_s": time.time() - start_time
                }
            # Otherwise continue trying
            time.sleep(poll_s)
            continue
        
        value = result.get("value")
        if value is not None:
            readings.append(value)
        
        # Check for stability
        if len(readings) >= min_samples:
            # Check if last readings are within delta
            recent = readings[-min_samples:]
            max_val = max(recent)
            min_val = min(recent)
            if max_val - min_val <= delta:
                avg_val = sum(recent) / len(recent)
                return {
                    "ok": True,
                    "stable": True,
                    "value": round(avg_val, 3),
                    "samples": len(readings),
                    "duration_s": round(time.time() - start_time, 1)
                }
        
        time.sleep(poll_s)
    
    # Timeout - not stable
    avg_val = sum(readings) / len(readings) if readings else None
    return {
        "ok": True,
        "stable": False,
        "value": round(avg_val, 3) if avg_val is not None else None,
        "samples": len(readings),
        "duration_s": round(time.time() - start_time, 1),
        "note": "Timeout - reading did not stabilize"
    }


def get_ph_calibration_status() -> Dict[str, Any]:
    """
    Get current pH calibration status.
    Uses dual locks: _READ_MUTEX (I2C serialization) + _acquire_calib_lock (poller coordination).
    
    Returns:
        {
            "ok": bool,
            "status": str (raw response),
            "flags": list (parsed calibration points),
            "points": list (friendly point names)
        }
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "error": "I2C not available"}
    
    # Acquire I2C mutex first
    if not _READ_MUTEX.acquire(timeout=3.0):
        return {"ok": False, "error": "Could not acquire I2C access; sensor read in progress"}
    try:
        # Then acquire calibration lock
        if not _acquire_calib_lock():
            return {"ok": False, "error": "Calibration lock held by sensor poller"}
        
        try:
            time.sleep(0.6)  # Allow in-flight reads to complete
            
            ph = ezo_i2c_stabilized.EZO(1, PH_ADDR, "pH")
            try:
                response = ph.cmd("Cal,?", read_len=32, settle=1.0)
                
                # Parse response
                flags = []
                if response:
                    parts = [p.strip() for p in response.split(",") if p.strip()]
                    # Remove leading '?' if present
                    if parts and parts[0] == '?':
                        parts = parts[1:]
                    flags = parts
                
                # Derive friendly point names
                points = []
                if flags:
                    # If any non-numeric tokens beyond first, treat them as explicit calibration points
                    named = [f for f in flags if not f.isdigit() and f.lower() not in ("?cal",)]
                    if named:
                        points = named
                    else:
                        # Numeric-only form; first numeric token = count
                        nums = [int(f) for f in flags if f.isdigit()]
                        if nums:
                            cnt = nums[0]
                            if cnt == 1:
                                points = ["mid"]
                            elif cnt == 2:
                                points = ["mid", "low"]
                            elif cnt >= 3:
                                points = ["mid", "low", "high"]
                
                return {
                    "ok": True,
                    "status": response or "No response",
                    "flags": flags,
                    "points": points
                }
            finally:
                ph.close()
        finally:
            _release_calib_lock()
    except Exception as e:
        logger.error(f"Failed to get pH calibration status: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        _READ_MUTEX.release()


def clear_ph_calibration() -> Dict[str, Any]:
    """
    Clear all pH calibration points.
    Uses dual locks: _READ_MUTEX (I2C serialization) + _acquire_calib_lock (poller coordination).
    
    Returns:
        {"ok": bool, "note": str}
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "note": "I2C not available"}
    
    # Acquire I2C mutex first
    if not _READ_MUTEX.acquire(timeout=3.0):
        return {"ok": False, "note": "Could not acquire I2C access; sensor read in progress"}
    try:
        # Then acquire calibration lock
        if not _acquire_calib_lock():
            return {"ok": False, "note": "Calibration lock held by sensor poller"}
        
        try:
            time.sleep(1.0)  # Allow in-flight reads to finish
            
            ph = ezo_i2c_stabilized.EZO(1, PH_ADDR, "pH")
            try:
                response = ph.cmd("Cal,clear", read_len=32, settle=1.2)
                
                # Check if successful - EZO typically returns "1" or empty string on success
                if response is not None:
                    logger.info("pH calibration cleared")
                    return {"ok": True, "note": "Cleared"}
                else:
                    # Retry once on failure
                    time.sleep(0.5)
                    response = ph.cmd("Cal,clear", read_len=32, settle=1.6)
                    if response is not None:
                        logger.info("pH calibration cleared (retry)")
                        return {"ok": True, "note": "Cleared"}
                    else:
                        return {"ok": False, "note": "Clear failed"}
            finally:
                ph.close()
        finally:
            _release_calib_lock()
    except Exception as e:
        logger.error(f"Failed to clear pH calibration: {e}")
        return {"ok": False, "note": str(e)}
    finally:
        _READ_MUTEX.release()


def calibrate_ph_point(point: str, value: float) -> Dict[str, Any]:
    """
    Apply pH calibration at a specific point (mid, low, or high).
    Uses dual locks: _READ_MUTEX (I2C serialization) + _acquire_calib_lock (poller coordination).
    
    Args:
        point: Calibration point name ("mid", "low", or "high")
        value: pH value of the calibration buffer
        
    Returns:
        {"ok": bool, "note": str}
    """
    if not _I2C_AVAILABLE:
        return {"ok": False, "note": "I2C not available"}
    
    # Validate inputs
    if point not in ("mid", "low", "high"):
        return {"ok": False, "note": f"Invalid point: {point}"}
    
    value = max(0.0, min(14.0, float(value)))
    
    # Acquire I2C mutex first
    if not _READ_MUTEX.acquire(timeout=3.0):
        return {"ok": False, "note": "Could not acquire I2C access; sensor read in progress"}
    try:
        # Then acquire calibration lock
        if not _acquire_calib_lock():
            return {"ok": False, "note": "Calibration lock held by sensor poller"}
        
        try:
            # Wait for any in-flight sensor read to complete
            time.sleep(2.0)
            
            ph = ezo_i2c_stabilized.EZO(1, PH_ADDR, "pH")
            try:
                # Ensure continuous mode is off and device is ready
                ph.cmd("C,0", read_len=0, settle=0.25)
                time.sleep(0.25)
                
                # Attempt calibration with progressively longer settle times
                attempts = [
                    (1.6, 5.0),
                    (2.2, 6.5),
                    (2.8, 8.0),
                ]
                
                for idx, (settle_s, timeout_s) in enumerate(attempts, start=1):
                    try:
                        response = ph.cmd(f"Cal,{point},{value:.2f}", read_len=32, settle=settle_s)
                        
                        # Consider it successful if we get any response or empty string
                        # EZO pH returns "1" on success or empty string
                        if response is not None:
                            logger.info(f"pH {point} calibration success on attempt {idx}")
                            # CRITICAL: Give probe time to settle after calibration before releasing lock
                            time.sleep(3.0)
                            return {
                                "ok": True,
                                "note": f"{point.title()} calibrated at {value:.2f}"
                            }
                    except Exception as e:
                        logger.warning(f"pH calibration attempt {idx} failed: {e}")
                        if idx < len(attempts):
                            time.sleep(0.8)
                
                return {"ok": False, "note": "All calibration attempts failed"}
            finally:
                ph.close()
        finally:
            _release_calib_lock()
    except Exception as e:
        logger.error(f"pH calibration failed: {e}")
        return {"ok": False, "note": str(e)}
    finally:
        _READ_MUTEX.release()
