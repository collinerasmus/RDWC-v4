from fastapi import FastAPI, Body, Query
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, PlainTextResponse
import threading, time, os, csv, io
import asyncio
from contextlib import suppress
from typing import Optional
from subprocess import run, PIPE
from app.ezo_i2c_stabilized import read_all
from app.ezo_i2c import identify, ADDR_PH, ADDR_EC, ADDR_RTD
from app.diag import router as diag_router
from app.hardware import PumpController, RelayBank
from app.logger import log_reading, last_n, fetch_history_since
from app.scheduler import Scheduler, load_cfg, save_cfg
from app.monitor import start_monitoring, stop_monitoring, get_monitoring_status
from app.relays_core import initialize_all_safe_off, get_relay_event_log, allowed_lights_reasons, set_lights_hold

DB_PATH = os.environ.get("RDWC_DB", os.path.join(os.path.dirname(__file__), "..", "data", "rdwc.db"))
DB_PATH = os.path.abspath(DB_PATH)

app = FastAPI()
app.include_router(diag_router)

# Initialize centralized relay system
initialize_all_safe_off()

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
    # Start alert monitoring
    start_monitoring()

@app.on_event("shutdown")  
async def _stop_tasks():
    global sensor_task
    with suppress(Exception):
        if sensor_task:
            sensor_task.cancel()
    _scheduler.shutdown()
    # Stop alert monitoring
    stop_monitoring()

@app.get("/health")
def health():
    """Health check with readiness gates"""
    age = max(0, time.time() - START_TS)
    require_camera = os.environ.get("READINESS_REQUIRE_CAMERA", "false").lower() == "true"
    
    # Core readiness checks
    db_ready = False
    i2c_ready = False
    camera_status = {"ready": False, "note": "non-blocking"}
    
    # Check database writer
    try:
        from app.infra.db_writer import get_db_writer
        db_writer = get_db_writer()
        db_ready = db_writer.worker_thread and db_writer.worker_thread.is_alive()
    except Exception as e:
        camera_status["db_error"] = str(e)
    
    # Check I²C bus
    try:
        from app.infra.i2c_bus import get_bus
        bus = get_bus()
        i2c_ready = bus is not None
    except Exception as e:
        camera_status["i2c_error"] = str(e)
    
    # Check camera (non-blocking unless env var set)
    try:
        # Simple check - we don't have camera module yet, so assume ready
        camera_status = {"ready": True, "note": "assumed ready"}
    except Exception as e:
        camera_status = {"ready": False, "note": f"camera error: {str(e)}"}
    
    # Get today's lights window
    lights_info = {"error": "unable to get lights schedule"}
    try:
        from app.settings import get_todays_lights_window
        on_dt, off_dt = get_todays_lights_window()
        lights_info = {
            "on_time": on_dt.strftime("%H:%M"),
            "off_time": off_dt.strftime("%H:%M"),
            "on_datetime": on_dt.isoformat(),
            "off_datetime": off_dt.isoformat()
        }
    except Exception as e:
        lights_info = {"error": str(e)}
    
    # Get relay status
    relay_states = {}
    antiflap_active = []
    try:
        from app.relays_core import get_relay_status, get_antiflap_relays
        relay_status = get_relay_status()
        relay_states = {
            name: {
                "state": info.get("state", False),
                "last_reason": info.get("last_reason", "unknown"),
                "seconds_since_change": info.get("seconds_since_change", 0)
            }
            for name, info in relay_status.items()
        }
        antiflap_active = get_antiflap_relays()
    except Exception as e:
        relay_states = {"error": str(e)}

    # Build response
    response_data = {
        "ok": db_ready and i2c_ready,
        "uptime_s": age,
        "db": db_ready,
        "i2c": i2c_ready,
        "camera": camera_status,
        "lights_window": lights_info,
        "relay_states": relay_states,
        "antiflap_active": antiflap_active
    }
    
    # Only fail on camera if explicitly required
    if require_camera and not camera_status["ready"]:
        response_data["ok"] = False
        return JSONResponse(status_code=503, content=response_data)
    
    # Return 503 only if core systems (DB/I2C) aren't ready
    if not (db_ready and i2c_ready):
        return JSONResponse(status_code=503, content=response_data)
    
    return response_data

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

# Alert monitoring endpoints
@app.get("/monitoring/status")
def monitoring_status():
    """Get current monitoring and alert status"""
    return get_monitoring_status()

@app.post("/monitoring/test_alerts")
async def test_alerts():
    """Test alert system - sends test messages to all configured channels"""
    from app.alerts import test_alerts
    results = await test_alerts()
    return {"results": results}

# Settings endpoints
@app.get("/settings")
def get_settings_api():
    """Get current system settings"""
    from app.settings import get_settings
    settings = get_settings()
    return {
        "system_volume_liters": settings.system_volume_liters,
        "lights_on_time": settings.lights_on_time,
        "lights_duration_hours": settings.lights_duration_hours
    }

@app.put("/settings")
def update_settings_api(
    system_volume_liters: Optional[float] = Body(None),
    lights_on_time: Optional[str] = Body(None), 
    lights_duration_hours: Optional[int] = Body(None)
):
    """Update system settings with validation"""
    from app.settings import update_settings
    
    try:
        updated_settings = update_settings(
            system_volume_liters=system_volume_liters,
            lights_on_time=lights_on_time,
            lights_duration_hours=lights_duration_hours
        )
        
        # Trigger scheduler update if lights settings changed
        if lights_on_time is not None or lights_duration_hours is not None:
            _scheduler._update_lights_schedule()
        
        return {
            "system_volume_liters": updated_settings.system_volume_liters,
            "lights_on_time": updated_settings.lights_on_time,
            "lights_duration_hours": updated_settings.lights_duration_hours
        }
        
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Validation failed: {str(e)}"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to update settings: {str(e)}"}
        )

# Override endpoints
@app.get("/overrides")
def get_overrides_api():
    """Get current overrides"""
    from app.overrides import get_override_status
    return get_override_status()

@app.put("/overrides")
def update_overrides_api(
    chiller_mode: Optional[str] = Body(None),
    hold_minutes: Optional[int] = Body(None),
    hold_until: Optional[str] = Body(None)
):
    """Update system overrides with validation"""
    from app.overrides import set_overrides, get_override_status
    from datetime import datetime
    
    try:
        # Validate chiller_mode
        if chiller_mode and chiller_mode not in ("auto", "force_on", "force_off"):
            return JSONResponse(
                status_code=400,
                content={"error": "chiller_mode must be 'auto', 'force_on', or 'force_off'"}
            )
        
        # Parse hold_until if provided
        hold_until_dt = None
        if hold_until:
            try:
                hold_until_dt = datetime.fromisoformat(hold_until)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": "hold_until must be ISO8601 format"}
                )
        
        # Update overrides
        set_overrides(
            chiller_mode=chiller_mode if chiller_mode in ("auto", "force_on", "force_off") else None,
            hold_minutes=hold_minutes,
            hold_until=hold_until_dt
        )
        
        # Return effective overrides
        return get_override_status()
        
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Validation failed: {str(e)}"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to update overrides: {str(e)}"}
        )

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

# Debug endpoints for lights control investigation
@app.get("/debug/lights_log")
def debug_lights_log(last: int = Query(50, description="Number of recent events to return")):
    """Get recent lights control event log with summary statistics."""
    events = get_relay_event_log("lights", last=last)
    
    # Generate summary statistics
    by_reason = {}
    blocked_count = 0
    changed_count = 0
    
    for event in events:
        reason = event.get("reason", "unknown")
        by_reason[reason] = by_reason.get(reason, 0) + 1
        if event.get("blocked", False):
            blocked_count += 1
        if event.get("final", True):  # final=True means the change was applied
            changed_count += 1
    
    summary = {
        "total": len(events),
        "by_reason": by_reason,
        "blocked": blocked_count,
        "applied": changed_count,
        "success_rate": f"{(changed_count / len(events) * 100):.1f}%" if events else "0%"
    }
    
    return {
        "relay": "lights",
        "summary": summary,
        "total_events": len(events),
        "events": events
    }

@app.get("/debug/lights_allowed")
def debug_lights_allowed():
    """Get list of allowed reasons for lights control."""
    reasons = allowed_lights_reasons()
    return {
        "allowed_reasons": reasons,
        "total": len(reasons)
    }

@app.get("/debug/lights_sources")
def debug_lights_sources(minutes: int = Query(15, description="Look back this many minutes")):
    """Get counts by reason and caller for recent lights control attempts."""
    from datetime import datetime, timedelta
    
    events = get_relay_event_log("lights", last=200)  # Get more events to filter by time
    cutoff_time = datetime.now() - timedelta(minutes=minutes)
    
    # Filter events to the specified time window
    recent_events = []
    for event in events:
        try:
            event_time = datetime.fromisoformat(event.get("ts", "").replace("Z", "+00:00"))
            if event_time >= cutoff_time:
                recent_events.append(event)
        except (ValueError, TypeError):
            continue  # Skip events with invalid timestamps
    
    # Analyze sources
    by_reason = {}
    by_caller = {}
    blocked_by_reason = {}
    
    for event in recent_events:
        reason = event.get("reason", "unknown")
        caller = event.get("caller", "unknown")
        blocked = event.get("blocked", False)
        
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_caller[caller] = by_caller.get(caller, 0) + 1
        
        if blocked:
            blocked_by_reason[reason] = blocked_by_reason.get(reason, 0) + 1
    
    return {
        "time_window_minutes": minutes,
        "events_found": len(recent_events),
        "by_reason": by_reason,
        "by_caller": by_caller,
        "blocked_by_reason": blocked_by_reason,
        "analysis": {
            "most_active_reason": max(by_reason.items(), key=lambda x: x[1])[0] if by_reason else None,
            "most_active_caller": max(by_caller.items(), key=lambda x: x[1])[0] if by_caller else None,
            "most_blocked_reason": max(blocked_by_reason.items(), key=lambda x: x[1])[0] if blocked_by_reason else None
        }
    }

@app.post("/debug/lights_hold")
def debug_lights_hold(seconds: int = Body(..., embed=True)):
    """Set temporary hold on lights for debugging (blocks all changes)."""
    result = set_lights_hold(seconds)
    return {"ok": True, "message": f"Lights held for {seconds} seconds", **result}

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