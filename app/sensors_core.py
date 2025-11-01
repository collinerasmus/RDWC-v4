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
    Deadline-aware best-effort read (pH->Temp->EC).
    - Returns within RDWC_SENSORS_READ_DEADLINE_S (default 2.5s).
    - Temp-comp only when BOTH temp & EC exist and time remains.
    - online=True if ANY value present. All float parsing is tolerant.
    """
    import time
    import math
    import datetime as dt
    from app import ezo_i2c

    DEADLINE_S = float(os.getenv("RDWC_SENSORS_READ_DEADLINE_S", "2.5"))
    t0 = time.time()
    
    def left() -> float:
        return DEADLINE_S - (time.time() - t0)

    def timed_out() -> bool:
        return left() <= 0.0

    def iso() -> str:
        return dt.datetime.utcnow().isoformat() + "Z"

    def fnum(x):
        try:
            if x is None:
                return None
            s = str(x).strip()
            if s == "" or s.lower() == "nan":
                return None
            v = float(s)
            if math.isnan(v):
                return None
            return v
        except Exception:
            return None

    out = {
        "temperature_c": None, "ec_mscm": None, "ph": None,
        "temp_comp_applied": False, "temp_comp_reason": "",
        "online": False, "ts": iso(), "errors": {}
    }

    def safe_read(addr, label):
        if timed_out():
            out["errors"][label] = "deadline"
            return None, None
        try:
            # Our ezo_i2c.read_single returns value only; unit not available
            v = ezo_i2c.read_single(addr)
            return v, None
        except Exception as ex:
            out["errors"][label] = type(ex).__name__
            return None, None

    # 1) pH first
    v,_ = safe_read(0x63, "ph")
    out["ph"] = fnum(v)

    # 2) Temp (RTD)
    if not timed_out():
        v,_ = safe_read(0x66, "temp")
        out["temperature_c"] = fnum(v)

    # 3) EC with uS->mS normalization
    if not timed_out():
        v, u = safe_read(0x64, "ec")
        vv, uu = fnum(v), (u or "").lower()
        if vv is not None:
            if uu.startswith("us"):
                out["ec_mscm"] = vv / 1000.0
            elif uu.startswith("ms"):
                out["ec_mscm"] = vv
            else:
                out["ec_mscm"] = vv / 1000.0 if vv > 10 else vv

    # 4) Temp-comp only if BOTH temp & EC exist and time remains
    if (out["temperature_c"] is not None and out["ec_mscm"] is not None and left()>0.9):
        try:
            if ezo_i2c.set_temp_comp(0x64, out["temperature_c"]):
                time.sleep(min(left(), float(os.getenv("RDWC_I2C_COMP_SETTLE_S","0.90"))))
            if left() > 0.2 and ezo_i2c.set_temp_comp(0x63, out["temperature_c"]):
                out["temp_comp_applied"] = True
                out["temp_comp_reason"] = "ec,ph"
        except Exception as ex:
            out["temp_comp_applied"] = False
            out["temp_comp_reason"] = f"error:{type(ex).__name__}"

    out["online"] = any(out[k] is not None for k in ("ph","temperature_c","ec_mscm"))
    out["ts"] = iso()
    return out


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
