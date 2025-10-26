from time import sleep, time
from smbus2 import SMBus
from typing import Optional, Tuple

REG = 0x00
EZO_STATUS_SUCCESS = 1
EZO_STATUS_SYNTAX_ERROR = 2
EZO_STATUS_PENDING = 254

# Some EZO boards (EC) return longer CSV; allow bigger buffer
MAX_REPLY_LEN = 48
DEFAULT_I2C_BUS = 1

ADDR_PH  = 0x63
ADDR_EC  = 0x64
ADDR_RTD = 0x66

SETTLE_RTD = 0.6
SETTLE_PH  = 0.9
SETTLE_EC  = 0.6

def _send_cmd(bus: SMBus, addr: int, cmd: str) -> None:
    data = list(cmd.encode("ascii")) + [0x00]     # null-terminate
    bus.write_i2c_block_data(addr, REG, data)

def _read_raw(bus: SMBus, addr: int, max_len: int = MAX_REPLY_LEN) -> Tuple[int, str]:
    raw = bus.read_i2c_block_data(addr, REG, max_len)
    status = raw[0]
    if 0x00 in raw[1:]:
        end = raw[1:].index(0x00) + 1
    else:
        end = len(raw)
    payload = bytes(raw[1:1+end-1]).decode("ascii", errors="ignore").strip()
    return status, payload

def _poll_until_ready(bus: SMBus, addr: int, timeout_s: float = 3.5, interval_s: float = 0.15) -> Tuple[int, str]:
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

def identify(bus_id: int = DEFAULT_I2C_BUS, addr: int = ADDR_PH) -> str:
    with SMBus(bus_id) as bus:
        _send_cmd(bus, addr, "I")   # uppercase I for info
        sleep(0.35)
        _, payload = _poll_until_ready(bus, addr)
        return payload

def set_temp_comp(temp_c: float, bus_id: int = DEFAULT_I2C_BUS) -> None:
    with SMBus(bus_id) as bus:
        for a in (ADDR_PH, ADDR_EC):
            try:
                _send_cmd(bus, a, f"T,{temp_c:.2f}")
                sleep(0.1)
                _poll_until_ready(bus, a)
            except Exception:
                pass

def _read_numeric_token(payload: str) -> float:
    token = payload.split(",")[0].strip()
    if token == "":
        raise ValueError("Empty token")
    return float(token)

def read_single(addr: int, bus_id: int = DEFAULT_I2C_BUS, temp_c: Optional[float] = None) -> float:
    with SMBus(bus_id) as bus:
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
            # Some kernels need an extra read; try once more after short delay
            sleep(0.25)
            status, payload = _poll_until_ready(bus, addr)
            if not payload:
                raise ValueError(f"Empty payload from 0x{addr:02X}")

        return _read_numeric_token(payload)

def read_all(bus_id: int = DEFAULT_I2C_BUS) -> dict:
    out = {"temp_c": None, "ph": None, "ec_ms_cm": None, "errors": {}}

    # 1) Temperature first for compensation
    temp_c = None
    try:
        temp_c = read_single(ADDR_RTD, bus_id=bus_id)
        out["temp_c"] = temp_c
    except Exception as e:
        out["errors"]["temp"] = str(e)

    # 2) Push temp comp then read pH & EC
    if temp_c is not None:
        try:
            set_temp_comp(temp_c, bus_id=bus_id)
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