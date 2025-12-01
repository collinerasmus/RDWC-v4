import os
from time import sleep, time
from typing import Optional, Tuple, Any
from .infra.i2c_bus import get_bus
from smbus2 import i2c_msg

REG = 0x00
EZO_STATUS_SUCCESS = 1
EZO_STATUS_SYNTAX_ERROR = 2
EZO_STATUS_PENDING = 254

# Linux SMBus block read is effectively 32 bytes max; keep 32 for reliability
MAX_REPLY_LEN = 32
DEFAULT_I2C_BUS = 1

ADDR_PH  = 0x63
ADDR_EC  = 0x64
ADDR_RTD = 0x66

# EC unit detection threshold: values above this are assumed to be in µS/cm
# Atlas EZO K=0.1 probe returns µS/cm (range 0.07-50,000 µS/cm)
# Typical hydro nutrient EC: 1.0-3.0 mS/cm = 1000-3000 µS/cm
EC_UNIT_THRESHOLD = 10.0  # µS/cm values above this get converted to mS/cm

# Env-tunable timeouts (fast defaults, stable in prod)
POLL_TIMEOUT_S   = float(os.getenv("RDWC_I2C_POLL_TIMEOUT_S",   "1.0"))   # was 6.0
RETRY_DELAY_S    = float(os.getenv("RDWC_I2C_RETRY_DELAY_S",    "0.15"))  # was 0.35
IO_RETRY_DELAY_S = float(os.getenv("RDWC_I2C_IO_RETRY_DELAY_S", "0.05"))  # was 0.10
COMP_SETTLE_S    = float(os.getenv("RDWC_I2C_COMP_SETTLE_S",    "0.90"))

# Slightly longer settles to avoid empty first payloads
SETTLE_RTD = 0.8
SETTLE_PH  = 1.0
SETTLE_EC  = 1.0

# Temperature compensation throttling
# {addr: (last_temp, last_time)}
_temp_comp_cache = {}

def _sleep(s: float) -> None:
    """Safe sleep wrapper that won't crash on interrupts."""
    try:
        sleep(s)
    except Exception:
        pass

def _send_cmd(bus: Any, addr: int, cmd: str) -> None:
    """Send a null-terminated ASCII command to an EZO device.
    Uses write_i2c_block_data when available; falls back to i2c_msg sequence otherwise.
    """
    data = list(cmd.encode("ascii")) + [0x00]   # null-terminated
    if hasattr(bus, "write_i2c_block_data"):
        bus.write_i2c_block_data(addr, REG, data)
    else:
        # Fallback: emulate block write with register prefix
        payload = bytes([REG] + data)
        bus.i2c_rdwr(i2c_msg.write(addr, payload))

def _read_raw(bus: Any, addr: int, max_len: int = MAX_REPLY_LEN) -> Tuple[int, str]:
    """Read raw payload from EZO device into a buffer of up to max_len bytes.
    Prefer read_i2c_block_data; fallback to i2c_msg register-then-read if unavailable.
    """
    if hasattr(bus, "read_i2c_block_data"):
        raw = bus.read_i2c_block_data(addr, REG, max_len)
    else:
        # Fallback: write register byte 0x00 then read max_len bytes
        w = i2c_msg.write(addr, bytes([REG]))
        r = i2c_msg.read(addr, max_len)
        bus.i2c_rdwr(w, r)
        raw = list(bytes(r))
    status = raw[0]
    if 0x00 in raw[1:]:
        end = raw[1:].index(0x00) + 1
    else:
        end = len(raw)
    payload = bytes(raw[1:1+end-1]).decode("ascii", errors="ignore").strip()
    return status, payload

def _poll_until_ready(bus: Any, addr: int, timeout_s: Optional[float] = None, interval_s: float = 0.15) -> Tuple[int, str]:
    if timeout_s is None:
        timeout_s = POLL_TIMEOUT_S
    t0 = time()
    last = (255, "")
    while True:
        last = _read_raw(bus, addr)
        if last[0] == EZO_STATUS_SUCCESS:
            return last
        if last[0] == EZO_STATUS_SYNTAX_ERROR:
            return last
        if time() - t0 > timeout_s:
            return last
        _sleep(interval_s)

def _disable_continuous(bus: Any, addr: int) -> None:
    # Some boards can be left in continuous mode—turn it off (non-fatal if unsupported)
    try:
        _send_cmd(bus, addr, "C,0")
        sleep(0.15)
        _poll_until_ready(bus, addr)
    except Exception:
        pass

def identify(bus_id: int = DEFAULT_I2C_BUS, addr: int = ADDR_PH) -> str:
    bus = get_bus()
    try:
        _send_cmd(bus, addr, "i")   # LOWERCASE per Atlas docs
        sleep(0.35)
        _, payload = _poll_until_ready(bus, addr)
        return payload
    except (IOError, OSError):
        sleep(0.1)  # Brief retry delay
        _send_cmd(bus, addr, "i")
        sleep(0.35)
        _, payload = _poll_until_ready(bus, addr)
        return payload

def set_temp_comp(address_hex: int, temp_c: float, bus_id: int = DEFAULT_I2C_BUS) -> bool:
    """
    Set temperature compensation for a specific EZO device with throttling
    
    Args:
        address_hex: I2C address (e.g., 0x63 for pH, 0x64 for EC)
        temp_c: Temperature in Celsius
        bus_id: I2C bus number
        
    Returns:
        True if temperature compensation was sent, False if throttled
    """
    global _temp_comp_cache
    
    current_time = time()
    
    # Check if we should throttle this update
    if address_hex in _temp_comp_cache:
        last_temp, last_time = _temp_comp_cache[address_hex]
        
        # Skip if temperature change is small AND recent
        temp_diff = abs(temp_c - last_temp)
        time_diff = current_time - last_time
        
        if temp_diff < 0.2 and time_diff < 60.0:  # Less than 0.2°C change and less than 60s
            return False
    
    # Send temperature compensation command
    bus = get_bus()
    try:
        _send_cmd(bus, address_hex, f"T,{temp_c:.2f}")
        sleep(0.1)
        _poll_until_ready(bus, address_hex)
        
        # Update cache
        _temp_comp_cache[address_hex] = (temp_c, current_time)
        return True
        
    except (IOError, OSError):
        sleep(0.1)  # Brief retry delay
        try:
            _send_cmd(bus, address_hex, f"T,{temp_c:.2f}")
            sleep(0.1)
            _poll_until_ready(bus, address_hex)
            
            # Update cache
            _temp_comp_cache[address_hex] = (temp_c, current_time)
            return True
        except Exception:
            return False
    except Exception:
        return False


def set_temp_comp_both(temp_c: float, bus_id: int = DEFAULT_I2C_BUS) -> dict:
    """
    Set temperature compensation for both pH and EC devices
    
    Returns:
        Dict with results for each device
    """
    results = {}
    results['ph'] = set_temp_comp(ADDR_PH, temp_c, bus_id)
    results['ec'] = set_temp_comp(ADDR_EC, temp_c, bus_id)
    return results

def _read_numeric_token(payload: str) -> Optional[float]:
    """Parse first numeric token; return None on empty/invalid instead of raising."""
    try:
        token = payload.split(",")[0].strip()
        if token == "":
            return None
        return float(token)
    except Exception:
        return None

def read_single(addr: int, bus_id: int = DEFAULT_I2C_BUS, temp_c: Optional[float] = None) -> Optional[float]:
    # Check for calibration lock - if calibration is in progress, skip this read
    import fcntl
    lock_path = "/tmp/rdwc_calib.lock"
    try:
        lock_fd = open(lock_path, 'w')
        # Try non-blocking lock - if it fails, calibration is happening
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Got lock, release immediately and proceed
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
    except (IOError, BlockingIOError):
        # Calibration in progress, return None to skip this read
        return None
    except Exception:
        pass  # Lock check failed, proceed anyway
    
    bus = get_bus()
    
    def _attempt_read():
        # Safety: ensure continuous is off (ok if not supported)
        _disable_continuous(bus, addr)

        if temp_c is not None and addr in (ADDR_PH, ADDR_EC):
            try:
                _send_cmd(bus, addr, f"T,{temp_c:.2f}")
                sleep(0.1)
                _poll_until_ready(bus, addr)
            except Exception:
                pass

        _send_cmd(bus, addr, "R")
        sleep(SETTLE_PH if addr == ADDR_PH else SETTLE_EC if addr == ADDR_EC else SETTLE_RTD)

        status, payload = _poll_until_ready(bus, addr)
        if status == EZO_STATUS_SYNTAX_ERROR:
            raise ValueError(f"EZO status 2 (syntax error) on 0x{addr:02X}, payload='{payload}'")
        if not payload:
            # One more chance after short wait; if still empty, return None
            _sleep(RETRY_DELAY_S)
            status, payload = _poll_until_ready(bus, addr)
            if not payload:
                return None
        return _read_numeric_token(payload)
    
    try:
        return _attempt_read()
    except (IOError, OSError):
        _sleep(IO_RETRY_DELAY_S)  # Brief retry delay
        return _attempt_read()

# Module-level throttle tracking for temp compensation
_LAST_COMP_TS = 0.0
_THROTTLE_S = 8.0  # Don't rewrite temp-comp more than once every 8s

def read_all(bus_id: int = DEFAULT_I2C_BUS) -> dict:
    """
    Read all sensors with proper temperature compensation sequence.
    
    Exact sequence per Atlas EZO specs:
    1. Read RTD (temperature)
    2. Send temp to EC, wait 900ms, read EC (throttled to avoid spam)
    3. Send temp to pH, wait 900ms, read pH (throttled to avoid spam)
    
    Returns dict with temp_comp_applied flag and reason for UI indicator.
    """
    global _LAST_COMP_TS
    
    out = {
        "temp_c": None, 
        "ph": None, 
        "ec_ms_cm": None, 
        "temp_comp_applied": False,
        "temp_comp_reason": "",
        "errors": {}
    }

    # Step 1: RTD first
    temp_c = None
    try:
        temp_c = read_single(ADDR_RTD, bus_id=bus_id)
        out["temp_c"] = temp_c
    except Exception as e:
        out["errors"]["temp"] = str(e)
        return out  # Can't continue without temperature

    # Track whether we actually wrote temp comp this cycle
    now = time()
    comp_applied = False
    comp_reason = []

    # Step 2: EC with temp compensation (throttled)
    if temp_c is not None:
        try:
            # Check throttle: only write if enough time passed
            if now - _LAST_COMP_TS > _THROTTLE_S:
                if set_temp_comp(ADDR_EC, temp_c, bus_id=bus_id):
                    comp_applied = True
                    comp_reason.append("ec")
                    _sleep(COMP_SETTLE_S)  # Wait for EC to apply temp comp
                else:
                    comp_reason.append("ec-skipped")
            else:
                comp_reason.append("ec-throttled")
        except Exception as e:
            out["errors"]["ec_temp_comp"] = str(e)
            comp_reason.append("ec-error")

    try:
        ec_val = read_single(ADDR_EC, bus_id=bus_id)
        # EC unit conversion using threshold constant
        if ec_val is not None:
            v = float(ec_val)
            out["ec_ms_cm"] = v / 1000.0 if v > EC_UNIT_THRESHOLD else v
        else:
            out["ec_ms_cm"] = None
    except Exception as e:
        out["errors"]["ec"] = str(e)

    # Step 3: pH with temp compensation (throttled)
    if temp_c is not None:
        try:
            # Check throttle: only write if enough time passed
            if time() - _LAST_COMP_TS > _THROTTLE_S:
                if set_temp_comp(ADDR_PH, temp_c, bus_id=bus_id):
                    comp_applied = True
                    comp_reason.append("ph")
                    _sleep(COMP_SETTLE_S)  # Wait for pH to apply temp comp
                else:
                    comp_reason.append("ph-skipped")
            else:
                comp_reason.append("ph-throttled")
        except Exception as e:
            out["errors"]["ph_temp_comp"] = str(e)
            comp_reason.append("ph-error")

    try:
        out["ph"] = read_single(ADDR_PH, bus_id=bus_id)
    except Exception as e:
        out["errors"]["ph"] = str(e)

    # Update throttle timestamp if we actually wrote
    if comp_applied:
        _LAST_COMP_TS = time()

    # Set flags for UI
    out["temp_comp_applied"] = comp_applied
    out["temp_comp_reason"] = ",".join(comp_reason)

    return out


# ----- LED helpers (Atlas EZO) -----
def set_led(addr: int, on: bool = True) -> bool:
    """
    Atlas EZO LED control: "L,1"=on, "L,0"=off
    Returns True if command accepted; False otherwise.
    """
    try:
        bus = get_bus()
        cmd = "L,1" if on else "L,0"
        _send_cmd(bus, addr, cmd)
        # Short poll until ready, honoring env-tunable timeout
        _poll_until_ready(bus, addr, timeout_s=POLL_TIMEOUT_S)
        return True
    except Exception:
        return False

def enable_all_leds(on: bool = True) -> dict:
    out = {"0x66": False, "0x64": False, "0x63": False}
    try:
        out["0x66"] = set_led(ADDR_RTD, on)
    except Exception:
        pass
    try:
        out["0x64"] = set_led(ADDR_EC, on)
    except Exception:
        pass
    try:
        out["0x63"] = set_led(ADDR_PH, on)
    except Exception:
        pass
    return out
# -----------------------------------


def blink_leds(count: int = 8, period_s: float = 0.25) -> dict:
    """
    Best-effort blink sequence so the user can visually confirm activity.
    Leaves LEDs ON at the end. Returns {ok: bool, count: int, error?: str}.
    """
    out = {"ok": True, "count": int(count)}
    try:
        n = max(0, int(count))
        per = max(0.05, float(period_s))
        for _ in range(n):
            enable_all_leds(True)
            _sleep(per)
            enable_all_leds(False)
            _sleep(per)
        enable_all_leds(True)
        return out
    except Exception as ex:
        out["ok"] = False
        out["error"] = type(ex).__name__
        return out


# ---------- FAST READ (no temp-comp, fail-fast) ----------
def read_all_fast():
    """
    Minimal, non-blocking read.
    - No temp-comp writes
    - 1.0s poll timeout per device (uses existing POLL_TIMEOUT_S env if present)
    - µS→mS normalization for EC
    Returns dict: {temperature_c, ec_mscm, ph, temp_comp_applied=False}
    """
    out = {"temperature_c": None, "ec_mscm": None, "ph": None, "temp_comp_applied": False}
    
    # RTD (temperature)
    try:
        t_val = read_single(ADDR_RTD)
        if t_val is not None:
            out["temperature_c"] = float(t_val)
    except Exception:
        pass
    
    # EC
    try:
        ec_val = read_single(ADDR_EC)
        if ec_val is not None:
            v = float(ec_val)
            out["ec_mscm"] = v / 1000.0 if v > EC_UNIT_THRESHOLD else v
    except Exception:
        pass
    
    # pH
    try:
        ph_val = read_single(ADDR_PH)
        if ph_val is not None:
            out["ph"] = float(ph_val)
    except Exception:
        pass
    
    return out
# ---------------------------------------------------------