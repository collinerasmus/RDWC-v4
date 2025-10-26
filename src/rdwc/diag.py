import subprocess, json, os
from .config import settings
from .sensors import Sensors

def i2c_scan():
    try:
        out = subprocess.check_output(["i2cdetect","-y","1"], text=True, timeout=5)
        return {"ok": True, "table": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def sensors_probe():
    try:
        s = Sensors()
        return {
            "mock": settings.force_mock_sensors,
            "ph_addr": hex(settings.ph_addr),
            "ec_addr": hex(settings.ec_addr),
            "rtd_addr": hex(settings.rtd_addr),
            "sample_try": s.sample_once() if hasattr(s,"sample_once") else None
        }
    except Exception as e:
        return {"error": str(e)}

def diag_bundle():
    return {
        "env": settings.env,
        "force_mock": settings.force_mock_sensors,
        "i2c_scan": i2c_scan(),
        "probe": sensors_probe()
    }