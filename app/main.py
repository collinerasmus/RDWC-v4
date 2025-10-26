from fastapi import FastAPI
from fastapi.responses import JSONResponse
import threading, time
from subprocess import run, PIPE
from app.ezo_i2c_stabilized import read_all
from app.ezo_i2c import identify, ADDR_PH, ADDR_EC, ADDR_RTD
from app.diag import router as diag_router

app = FastAPI()
app.include_router(diag_router)

_last = {"temp_c": None, "ph": None, "ec_ms_cm": None, "errors": {}}
_last_t = 0.0

def _sensor_loop():
    global _last, _last_t
    while True:
        try:
            data = read_all()
            # Convert from stabilized format to original format
            _last = {
                "temp_c": data.get("temperature"),
                "ph": data.get("ph"),
                "ec_ms_cm": data.get("ec_ms"),
                "errors": {}
            }
            _last_t = time.time()
        except Exception as e:
            _last = {"temp_c": None, "ph": None, "ec_ms_cm": None, "errors": {"loop": str(e)}}
        time.sleep(10)

if not any(t.name == "_sensor_loop" for t in threading.enumerate()):
    threading.Thread(target=_sensor_loop, name="_sensor_loop", daemon=True).start()

@app.get("/status")
def status():
    age = time.time() - _last_t
    return {"age_s": round(age, 2), **_last}

@app.post("/read_now")
def read_now():
    try:
        data = read_all()
        return JSONResponse({"ok": True, "data": data})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

@app.post("/fix_ezo")
def fix_ezo():
    try:
        id_ph  = identify(addr=ADDR_PH)
        id_ec  = identify(addr=ADDR_EC)
        id_rtd = identify(addr=ADDR_RTD)
        data   = read_all()
        return JSONResponse({"ok": True, "ids": {"ph": id_ph, "ec": id_ec, "rtd": id_rtd}, "data": data})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

@app.get("/cam_status")
def cam_status():
    svc = run(["systemctl", "is-active", "mjpg-streamer.service"], stdout=PIPE, stderr=PIPE, text=True)
    active = (svc.stdout.strip() == "active")
    return {"active": active, "url": "http://192.168.88.49:8081/?action=stream"}