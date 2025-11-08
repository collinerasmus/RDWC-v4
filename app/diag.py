import re, subprocess
from fastapi import APIRouter
from app.ezo_i2c_stabilized import EZO, PH_ADDR, EC_ADDR, RTD_ADDR
from app.sensors_core import read_all_sensors

router = APIRouter(prefix="/diag", tags=["diag"])

@router.get("/i2c_scan")
def i2c_scan():
    try:
        out = subprocess.run(["i2cdetect","-y","1"], capture_output=True, text=True, check=True).stdout
        addrs = re.findall(r"\b([0-9a-f]{2})\b", out, re.I)
        return {"ok": True, "addresses": sorted(set(a.lower() for a in addrs)), "grid": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/identify")
def diag_identify():
    res = {}
    for name, addr in (("ph", PH_ADDR), ("ec", EC_ADDR), ("rtd", RTD_ADDR)):
        try:
            dev = EZO(1, addr, name)
            info = dev.cmd("i", read_len=32, settle=0.3)
            res[name] = info if info else ""
        except Exception as e:
            res[name] = f"ERR: {e}"
    return {"ids": res}

@router.get("/probe")
def diag_probe():
    return {"data": read_all_sensors()}