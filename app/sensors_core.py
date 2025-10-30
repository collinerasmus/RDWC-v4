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
I2C_AVAILABLE = False

# Stub class for dev environments
class _EZOStub:  # type: ignore
    def __init__(self, bus_num, addr, name):
        self.name = name
    def init_once(self): pass
    def read_value(self, request="R", timeout=1.8, poll=0.15):
        return "23.0" if self.name == "RTD" else "6.5" if self.name == "pH" else "1500"
    def cmd(self, cmd, read_len=0, settle=0.06): pass

try:
    from .ezo_i2c_stabilized import EZO
    I2C_AVAILABLE = True
except ImportError as e:
    logger.warning(f"I²C libraries not available - running in simulation mode: {e}")
    EZO = _EZOStub  # type: ignore


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
    Read sensors using proven ezo_i2c_stabilized.read_all() with throttled T compensation.
    
    Returns:
        tuple: (t_write_performed, compensation_results, temp_c, ph_val, ec_val)
    """
    if not I2C_AVAILABLE:
        # Simulated read
        return False, {"ph": True, "ec": True}, 23.0, 6.5, 1500.0
    
    # Use the proven read_all function from ezo_i2c_stabilized
    # But we need to control T compensation ourselves for throttling
    try:
        from .ezo_i2c_stabilized import EZO, RTD_ADDR, PH_ADDR, EC_ADDR
        
        # Initialize all devices
        rtd = EZO(1, RTD_ADDR, "RTD")
        ph = EZO(1, PH_ADDR, "pH")
        ec = EZO(1, EC_ADDR, "EC")
        
        for dev in (rtd, ph, ec):
            dev.init_once()
        
        # Read RTD first
        temp_c = float(rtd.read_value())
        
        # Check throttle conditions AFTER reading temp
        should_send, _ = _should_send_temp_comp(temp_c)
        
        # Apply temperature compensation with throttling
        comp_results = {"ph": False, "ec": False}
        if should_send:
            for dev, name in [(ph, "ph"), (ec, "ec")]:
                try:
                    dev.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.06)
                    comp_results[name] = True
                except Exception as e:
                    logger.warning(f"{name} temp comp failed: {e}")
            
            # Update cache after successful send
            _update_temp_comp_cache(temp_c)
        
        # Read pH and EC
        ph_val = float(ph.read_value())
        ec_val = float(ec.read_value())
        
        return should_send, comp_results, temp_c, ph_val, ec_val
        
    except Exception as e:
        logger.error(f"Sensor read failed: {e}")
        raise


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
    
    # Use simulated values for dev environments
    if not I2C_AVAILABLE:
        result["temp_c"] = 23.0
        result["comp_temp_c"] = 23.0
        result["ph"] = 6.5
        result["ec_uS"] = 1500
        result["ec_mS"] = 1.5
        result["i2c_ops"]["reads"] = {"rtd": 1, "ph": 1, "ec": 1}
        result["t_write"] = False
        return result
    
    # Read all sensors with throttled T compensation
    try:
        should_send_t, comp_results, temp_c, ph_val, ec_val = _read_with_temp_comp_check()
        
        # Populate result with values
        result["temp_c"] = round(temp_c, 2)
        result["comp_temp_c"] = round(temp_c, 2)
        result["ph"] = round(ph_val, 2)
        result["ec_uS"] = round(ec_val, 0)
        result["ec_mS"] = round(ec_val / 1000.0, 2)
        
        # Populate throttle info
        result["t_write"] = should_send_t
        result["t_delta"] = round(_last_t_sent_c - temp_c if _last_t_sent_c is not None else 999.0, 2)
        result["i2c_ops"]["t_writes"] = sum(1 for v in comp_results.values() if v) if should_send_t else 0
        result["i2c_ops"]["reads"]["rtd"] = 1
        result["i2c_ops"]["reads"]["ph"] = 1
        result["i2c_ops"]["reads"]["ec"] = 1
        
        # Log T-write if it occurred
        if should_send_t:
            probes_updated = [k for k, v in comp_results.items() if v]
            if probes_updated:
                logger.info(f"T-comp sent: {temp_c:.2f}°C → {', '.join(probes_updated)} (ΔT={result['t_delta']:.2f}°C)")
        else:
            logger.debug(f"T-comp throttled: ΔT={result['t_delta']:.2f}°C")
        
    except Exception as e:
        logger.error(f"Sensor read failed: {e}", exc_info=True)
        result["errors"].append(f"Sensor read failed: {str(e)}")
    
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
