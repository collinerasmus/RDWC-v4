import subprocess, json
from .config import settings
from .sensors import Sensors, EZO

def i2c_scan():
    try:
        out = subprocess.check_output(["i2cdetect","-y","1"], text=True, timeout=5)
        return {"ok": True, "table": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def probe_now():
    s = Sensors()
    return s.sample_once()

def atlas(addr_hex: str, cmd: str):
    addr = int(addr_hex, 16)
    sensor = EZO(settings.i2c_bus, addr, mock_override=settings.force_mock_sensors)
    # Use low delay for non-"R" commands, 0.9s for reads
    if cmd.upper().startswith("R"):
        val = sensor.read_float("R", delay=0.9)
        return {"ok": True, "value": val}
    else:
        # send generic, then try to read text (OK/response)
        try:
            resp = sensor._exchange(cmd, delay=0.3)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "resp": resp}