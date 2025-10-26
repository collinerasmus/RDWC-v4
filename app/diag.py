import json, re, subprocess
from fastapi import APIRouter
from app.ezo_i2c import identify, read_all, ADDR_PH, ADDR_EC, ADDR_RTD

router = APIRouter(prefix="/diag", tags=["diag"])

@router.get("/i2c_scan")
def i2c_scan():
    # Run i2cdetect and parse addresses
    try:
        out = subprocess.run(["i2cdetect","-y","1"], capture_output=True, text=True, check=True).stdout
        addrs = re.findall(r"\b([0-9a-f]{2})\b", out, re.I)
        return {"ok": True, "grid": out, "addresses": sorted(set(a.lower() for a in addrs))}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/identify")
def diag_identify():
    res = {}
    for name, addr in (("ph", ADDR_PH), ("ec", ADDR_EC), ("rtd", ADDR_RTD)):
        try:
            res[name] = identify(addr=addr)
        except Exception as e:
            res[name] = f"ERR: {e}"
    return {"ids": res}

@router.get("/probe")
def diag_probe():
    # Convenience: perform read_all and return raw
    return {"data": read_all()}