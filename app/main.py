from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
import threading, time, os
from subprocess import run, PIPE
from app.ezo_i2c_stabilized import read_all
from app.ezo_i2c import identify, ADDR_PH, ADDR_EC, ADDR_RTD
from app.diag import router as diag_router
from app.hardware import PumpController, RelayBank
from app.logger import log_reading, last_n

app = FastAPI()
app.include_router(diag_router)
_relays = RelayBank()
_pumps = PumpController(_relays)

_last = {"temp_c": None, "ph": None, "ec_ms_cm": None, "errors": {}}
_last_t = 0.0

def _sensor_loop():
    global _last, _last_t
    while True:
        try:
            # read_all() returns {"temperature": <float>, "ph": <float>, "ec_ms": <float>}
            vals = read_all()
            _last = {
                "temp_c": vals.get("temperature"),
                "ph": vals.get("ph"),
                "ec_ms_cm": vals.get("ec_ms"),
                "errors": {}
            }
            _last_t = time.time()
            # log only if we have numbers
            if all(v is not None for v in (_last["temp_c"], _last["ph"], _last["ec_ms_cm"])):
                log_reading(_last["temp_c"], _last["ph"], _last["ec_ms_cm"])
        except Exception as e:
            _last = {"temp_c": None, "ph": None, "ec_ms_cm": None, "errors": {"loop": str(e)}}
        time.sleep(10)

if not any(t.name == "_sensor_loop" for t in threading.enumerate()):
    threading.Thread(target=_sensor_loop, name="_sensor_loop", daemon=True).start()

@app.get("/")
def ui():
    path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return FileResponse(path, media_type="text/html")

@app.get("/history")
def history(limit: int = 100):
    return last_n(limit)

@app.get("/pump/status")
def pump_status():
    return _pumps.status()

@app.post("/pump/{name}")
def pump_set(name: str, body: dict = Body(...)):
    state = body.get("state", "").lower()
    _pumps.set(name, state == "on")
    return {"ok": True, "state": _pumps.get(name)}

@app.get("/relay/status")
def relay_status():
    return _relays.status()

@app.post("/relay/{name}")
def relay_set(name: str, body: dict = Body(...)):
    state = (body.get("state","").lower() == "on")
    _relays.set(name, state)
    return {"ok": True, "state": _relays.get(name)}

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