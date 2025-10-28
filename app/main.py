from fastapi import FastAPI, Body, Query
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, PlainTextResponse
import threading, time, os, csv, io, sqlite3
import asyncio
from contextlib import suppress
from subprocess import run, PIPE
from app.ezo_i2c_stabilized import read_all
from app.ezo_i2c import identify, ADDR_PH, ADDR_EC, ADDR_RTD
from app.diag import router as diag_router
from app.hardware import PumpController, RelayBank
from app.logger import log_reading, last_n
from app.scheduler import Scheduler, load_cfg, save_cfg

DB_PATH = os.environ.get("RDWC_DB", os.path.join(os.path.dirname(__file__), "..", "data", "rdwc.db"))
DB_PATH = os.path.abspath(DB_PATH)

def fetch_history_since(since_ts: int):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT ts, temp_c, ph, ec_ms_cm FROM readings WHERE ts >= ? ORDER BY ts DESC", (since_ts,))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows

app = FastAPI()
app.include_router(diag_router)
_relays = RelayBank()
# Restore state for main_pump and chiller_pump on startup
_relays.load_state(allowlist=["main_pump","chiller_pump"], default_off=True)
_pumps = PumpController(_relays)
_scheduler = Scheduler(_relays)

_last = {"temp_c": None, "ph": None, "ec_ms_cm": None, "errors": {}}
_last_t = 0.0
START_TS = time.time()
sensor_task = None

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

async def sensor_loop():
    """Async version of sensor loop for proper startup management"""
    global _last, _last_t
    while True:
        try:
            vals = read_all()
            _last = {
                "temp_c": vals.get("temperature"),
                "ph": vals.get("ph"), 
                "ec_ms_cm": vals.get("ec_ms"),
                "errors": {}
            }
            _last_t = time.time()
            if all(v is not None for v in (_last["temp_c"], _last["ph"], _last["ec_ms_cm"])):
                log_reading(_last["temp_c"], _last["ph"], _last["ec_ms_cm"])
        except Exception as e:
            _last = {"temp_c": None, "ph": None, "ec_ms_cm": None, "errors": {"loop": str(e)}}
        await asyncio.sleep(10)

@app.on_event("startup")
async def _start_tasks():
    global sensor_task
    if sensor_task is None or sensor_task.done():
        sensor_task = asyncio.create_task(sensor_loop(), name="sensor_loop")
    # Also start the old thread as backup
    if not any(t.name == "_sensor_loop" for t in threading.enumerate()):
        threading.Thread(target=_sensor_loop, name="_sensor_loop", daemon=True).start()
    _scheduler.start()

@app.on_event("shutdown")  
async def _stop_tasks():
    global sensor_task
    with suppress(Exception):
        if sensor_task:
            sensor_task.cancel()
    _scheduler.shutdown()

@app.get("/health")
def health():
    age = max(0, time.time() - START_TS)
    return {"ok": True, "uptime_s": age}

@app.get("/")
def ui():
    path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return FileResponse(path, media_type="text/html")

@app.get("/history")
def history(limit: int = 100):
    return last_n(limit)

@app.get("/history_window")
def history_window(hours: float = Query(6.0)):
    # return last {hours} hours
    secs = max(60, int(hours * 3600))
    # reuse your existing DB helper to fetch rows by timestamp
    since = int(time.time()) - secs
    # expect a function fetch_history_since(since_ts) -> list of dicts
    rows = fetch_history_since(since)  # implement or adapt existing utility
    return rows

@app.get("/export_csv", response_class=PlainTextResponse)
def export_csv(hours: float = Query(24.0)):
    secs = max(60, int(hours * 3600))
    since = int(time.time()) - secs
    rows = fetch_history_since(since)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ts","temp_c","ph","ec_ms_cm"])
    for r in rows:
        w.writerow([r.get("ts"), r.get("temp_c"), r.get("ph"), r.get("ec_ms_cm")])
    return out.getvalue()

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

@app.get("/relay/persist")
def relay_persist_info():
    import os, json
    p = os.environ.get("RDWC_STATE_DIR", os.path.expanduser("~/.rdwc"))
    f = os.path.join(p, "relay_state.json")
    payload = {}
    try:
        with open(f,"r") as fh: payload = json.load(fh)
    except Exception: payload = {"note":"state file not found"}
    return {"dir": p, "file": f, "payload": payload}

@app.post("/relay/save")
def relay_save():
    _relays.save_state(allowlist=["main_pump","chiller_pump"])
    return {"ok": True}

@app.post("/relay/restore")
def relay_restore():
    _relays.load_state(allowlist=["main_pump","chiller_pump"], default_off=True)
    return {"ok": True}

@app.get("/schedule")
def schedule_get():
    return load_cfg()

@app.post("/schedule")
def schedule_set(cfg: dict = Body(...)):
    save_cfg(cfg)
    return {"ok": True}

@app.post("/schedule/enable")
def schedule_enable(enabled: bool = Body(..., embed=True)):
    cfg = load_cfg(); cfg["enabled"] = bool(enabled); save_cfg(cfg)
    return {"ok": True, "enabled": cfg["enabled"]}

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