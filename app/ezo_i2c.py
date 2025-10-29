from time import sleep, time
from typing import Optional, Tuple, Any
from .infra.i2c_bus import get_bus

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

# Slightly longer settles to avoid empty first payloads
SETTLE_RTD = 0.8
SETTLE_PH  = 1.0
SETTLE_EC  = 1.0

# Temperature compensation throttling
# {addr: (last_temp, last_time)}
_temp_comp_cache = {}

def _send_cmd(bus: Any, addr: int, cmd: str) -> None:
    data = list(cmd.encode("ascii")) + [0x00]   # null-terminated
    bus.write_i2c_block_data(addr, REG, data)

def _read_raw(bus: Any, addr: int, max_len: int = MAX_REPLY_LEN) -> Tuple[int, str]:
    raw = bus.read_i2c_block_data(addr, REG, max_len)
    status = raw[0]
    if 0x00 in raw[1:]:
        end = raw[1:].index(0x00) + 1
    else:
        end = len(raw)
    payload = bytes(raw[1:1+end-1]).decode("ascii", errors="ignore").strip()
    return status, payload

def _poll_until_ready(bus: Any, addr: int, timeout_s: float = 6.0, interval_s: float = 0.15) -> Tuple[int, str]:
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
        sleep(interval_s)

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

def _read_numeric_token(payload: str) -> float:
    token = payload.split(",")[0].strip()
    if token == "":
        raise ValueError("Empty token")
    return float(token)

def read_single(addr: int, bus_id: int = DEFAULT_I2C_BUS, temp_c: Optional[float] = None) -> float:
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
            # One more chance after short wait
            sleep(0.35)
            status, payload = _poll_until_ready(bus, addr)
            if not payload:
                raise ValueError(f"Empty payload from 0x{addr:02X}")
        return _read_numeric_token(payload)
    
    try:
        return _attempt_read()
    except (IOError, OSError):
        sleep(0.1)  # Brief retry delay
        return _attempt_read()

def read_all(bus_id: int = DEFAULT_I2C_BUS) -> dict:
    out = {"temp_c": None, "ph": None, "ec_ms_cm": None, "errors": {}}

    # RTD first
    temp_c = None
    try:
        temp_c = read_single(ADDR_RTD, bus_id=bus_id)
        out["temp_c"] = temp_c
    except Exception as e:
        out["errors"]["temp"] = str(e)

    if temp_c is not None:
        try:
            set_temp_comp_both(temp_c, bus_id=bus_id)
        except Exception:
            pass

    try:
        out["ph"] = read_single(ADDR_PH, bus_id=bus_id, temp_c=temp_c)
    except Exception as e:
        out["errors"]["ph"] = str(e)

    try:
        out["ec_ms_cm"] = read_single(ADDR_EC, bus_id=bus_id, temp_c=temp_c)
    except Exception as e:
        out["errors"]["ec"] = str(e)

    return out