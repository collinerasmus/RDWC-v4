import time
from .config import settings
from .sensors import EZO

DEVICE_DELAY = {
    0x63: 0.9,   # pH
    0x64: 1.0,   # EC
    0x66: 0.6,   # RTD
}

def _delay_for(addr:int)->float:
    return DEVICE_DELAY.get(addr, 0.9)

def read_value(addr: int, cmd="R"):
    sensor = EZO(settings.i2c_bus, addr, mock_override=settings.force_mock_sensors)
    return sensor.read_float(cmd=cmd, delay=_delay_for(addr))

def set_temp_comp(t_c: float):
    """Push temperature to EC and pH boards (if supported)."""
    for addr in (settings.ec_addr, settings.ph_addr):
        e = EZO(settings.i2c_bus, addr, mock_override=settings.force_mock_sensors)
        try:
            e._exchange(f"T,{t_c:.2f}", delay=0.3)
        except Exception:
            pass

def identify(addr:int):
    e = EZO(settings.i2c_bus, addr, mock_override=settings.force_mock_sensors)
    try:
        txt = e._exchange("I", delay=0.3)
        return txt
    except Exception as ex:
        return f"ERR:{ex}"

def run_fixer():
    """
    Known-good sequence we used in v2/v3:
    - Null-terminated writes (handled in sensors.py)
    - Device-specific read delays
    - RTD temp -> temp compensation to EC & pH
    - Retry reads when 0xFE (processing)
    """
    results = {}
    # 1) Read RTD
    t = read_value(settings.rtd_addr, "R")
    results["temperature_c"] = t
    # 2) Push temp-comp
    set_temp_comp(t)
    time.sleep(0.2)
    # 3) Read EC & pH with safe delays
    ec = read_value(settings.ec_addr, "R")
    ph = read_value(settings.ph_addr, "R")
    # 4) Identify strings
    info = {
        "rtd_info": identify(settings.rtd_addr),
        "ec_info": identify(settings.ec_addr),
        "ph_info": identify(settings.ph_addr),
    }
    results.update({"ec": ec, "pH": ph, "info": info})
    return results