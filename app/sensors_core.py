"""
Centralized sensor reading with RTD-first and throttled temperature compensation.
Minimizes I²C traffic while maintaining accuracy.
"""
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
# Use the stabilized EZO interface that's proven to work
try:
    from .ezo_i2c_stabilized import EZO
    I2C_AVAILABLE = True
except ImportError:
    I2C_AVAILABLE = False
    logger.warning("I²C libraries not available - running in simulation mode")
    
    # Stub class for dev environments
    class EZO:  # type: ignore
        def __init__(self, bus_num, addr, name):
            self.name = name
        def init_once(self): pass
        def read_value(self, request="R", timeout=1.8, poll=0.15):
            return "23.0" if self.name == "RTD" else "6.5" if self.name == "pH" else "1500"
        def cmd(self, cmd, read_len=0, settle=0.06): pass


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


def _read_rtd_temp() -> Optional[float]:
    """Read temperature from RTD sensor."""
    if not I2C_AVAILABLE:
        # Simulated temperature for dev environments
        return 23.0 + (time.time() % 10) * 0.05
    
    try:
        rtd = EZO(1, ADDR_RTD, "RTD")
        rtd.init_once()
        result = rtd.read_value()
        return float(result)
    except Exception as e:
        logger.error(f"RTD read failed: {e}")
        return None


def _send_temp_comp_to_probes(temp_c: float) -> dict:
    """
    Send temperature compensation to pH and EC sensors.
    
    Returns:
        Dict with success status for each probe
    """
    results = {"ph": False, "ec": False}
    
    if not I2C_AVAILABLE:
        results = {"ph": True, "ec": True}  # Simulate success
        return results
    
    # Send to pH
    try:
        ph = EZO(1, ADDR_PH, "pH")
        ph.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.06)
        results["ph"] = True
    except Exception as e:
        logger.warning(f"pH temp comp failed: {e}")
    
    # Send to EC
    try:
        ec = EZO(1, ADDR_EC, "EC")
        ec.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.06)
        results["ec"] = True
    except Exception as e:
        logger.warning(f"EC temp comp failed: {e}")
    
    return results


def _read_ph() -> Optional[float]:
    """Read pH value."""
    if not I2C_AVAILABLE:
        return 5.8 + (time.time() % 20) * 0.02
    
    try:
        ph = EZO(1, ADDR_PH, "pH")
        ph.init_once()
        result = ph.read_value()
        return float(result)
    except Exception as e:
        logger.error(f"pH read failed: {e}")
        return None


def _read_ec() -> Optional[float]:
    """Read EC value in μS/cm."""
    if not I2C_AVAILABLE:
        return 1500.0 + (time.time() % 50) * 10.0
    
    try:
        ec = EZO(1, ADDR_EC, "EC")
        ec.init_once()
        result = ec.read_value()
        return float(result)
    except Exception as e:
        logger.error(f"EC read failed: {e}")
        return None


def read_all_sensors() -> Dict[str, Any]:
    """
    Perform a complete sensor read with throttled temperature compensation.
    
    Sequence:
    1. Read RTD temperature first
    2. Check throttle conditions for temp compensation
    3. If throttle passes, send T to pH and EC
    4. Read pH and EC values
    
    Returns:
        Comprehensive dict with sensor values, throttle info, I²C operation counts,
        and any errors encountered
    """
    result = {
        "temp_c": None,
        "ph": None,
        "ec_uS": None,
        "ec_mS": None,
        "comp_temp_c": None,
        "t_write": False,
        "t_delta": 0.0,
        "i2c_ops": {
            "t_writes": 0,
            "reads": {"rtd": 0, "ph": 0, "ec": 0}
        },
        "errors": []
    }
    
    # Step 1: Read RTD temperature first
    temp_c = _read_rtd_temp()
    if temp_c is not None:
        result["temp_c"] = round(temp_c, 2)
        result["comp_temp_c"] = round(temp_c, 2)
        result["i2c_ops"]["reads"]["rtd"] = 1
    else:
        result["errors"].append("RTD read failed or returned None")
        # Cannot proceed without temperature for compensation
        return result
    
    # Step 2: Check throttle conditions
    should_send, delta_t = _should_send_temp_comp(temp_c)
    result["t_delta"] = round(delta_t, 2)
    
    # Step 3: Send temperature compensation if throttle passes
    if should_send:
        comp_results = _send_temp_comp_to_probes(temp_c)
        result["t_write"] = True
        result["i2c_ops"]["t_writes"] = sum(1 for v in comp_results.values() if v)
        
        # Update cache after successful send
        _update_temp_comp_cache(temp_c)
        
        # Log the T-write event (concise, only when it happens)
        probes_updated = [k for k, v in comp_results.items() if v]
        if probes_updated:
            logger.info(f"T-comp sent: {temp_c:.2f}°C → {', '.join(probes_updated)} (ΔT={delta_t:.2f}°C)")
    else:
        result["t_write"] = False
        logger.debug(f"T-comp throttled: ΔT={delta_t:.2f}°C (< 0.2) and < 60s elapsed")
    
    # Step 4: Read pH and EC
    ph_val = _read_ph()
    if ph_val is not None:
        result["ph"] = round(ph_val, 2)
        result["i2c_ops"]["reads"]["ph"] = 1
    else:
        result["errors"].append("pH read failed or returned None")
    
    ec_val = _read_ec()
    if ec_val is not None:
        result["ec_uS"] = round(ec_val, 0)
        result["ec_mS"] = round(ec_val / 1000.0, 2)
        result["i2c_ops"]["reads"]["ec"] = 1
    else:
        result["errors"].append("EC read failed or returned None")
    
    return result


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
