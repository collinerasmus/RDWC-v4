from fastapi import FastAPI, Body, Query
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse, StreamingResponse
import threading
import time
import os
import csv
import io
import asyncio
from contextlib import suppress
from typing import Optional
from subprocess import run, PIPE
from datetime import datetime, timedelta  # Keep global import
from app.debug import router as debug_router, trace_relay_request
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
app.include_router(debug_router, prefix="/debug", tags=["debug"])

# Initialize centralized relay system
initialize_all_safe_off()

_relays = RelayBank()
# Restore state for main_pump and chiller_pump on startup
_relays.load_state(allowlist=["main_pump","chiller_pump"], default_off=True)
_pumps = PumpController(_relays)
_scheduler = Scheduler(_relays)

# Debug router now holds the relay request ring buffer and tracer

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
    # Restore relay states from previous session
    from app.relays_core import _load_state
    _load_state()
    # Start async sensor loop
    sensor_task = asyncio.create_task(sensor_loop(), name="sensor_loop")
    # Also start the old thread as backup
    if not any(t.name == "_sensor_loop" for t in threading.enumerate()):
        threading.Thread(target=_sensor_loop, name="_sensor_loop", daemon=True).start()
    _scheduler.start()
    # Start alert monitoring
    start_monitoring()
    # Initialize camera (non-blocking; will gracefully stay unavailable if drivers missing)
    try:
        from app.camera import CameraManager
        CameraManager.init()
    except Exception:
        pass

@app.on_event("shutdown")  
async def _stop_tasks():
    global sensor_task
    with suppress(Exception):
        if sensor_task:
            sensor_task.cancel()
    _scheduler.shutdown()
    # Stop alert monitoring
    stop_monitoring()
    # Shutdown camera cleanly
    with suppress(Exception):
        from app.camera import CameraManager
        CameraManager.shutdown()

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

    # Get sensors heartbeat (shallow check, no actual read)
    sensors_heartbeat = {"ready": False}
    try:
        from app.sensors_core import get_last_temp_comp_state
        comp_state = get_last_temp_comp_state()
        time_since = comp_state.get("time_since_last")
        sensors_heartbeat = {
            "ready": time_since is not None,
            "last_read_age_s": round(time_since, 1) if time_since is not None else None
        }
    except Exception as e:
        sensors_heartbeat = {"ready": False, "error": str(e)}

    # Build response
    response_data = {
        "ok": db_ready and i2c_ready,
        "uptime_s": age,
        "db": db_ready,
        "i2c": i2c_ready,
        "camera": camera_status,
        "lights_window": lights_info,
        "relay_states": relay_states,
        "antiflap_active": antiflap_active,
        "sensors": sensors_heartbeat
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
    return FileResponse(path, media_type="text/html", headers={"Cache-Control":"no-store, must-revalidate"})

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

@app.get("/api/trends")
def api_trends(
    from_param: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None)
):
    """
    Trends API endpoint for Chart.js frontend.
    Returns: { "series": { "ph": [{ts, value}], "ec": [...], "temp": [...] } }
    """
    def parse_iso(s):
        if not s:
            return None
        try:
            # Parse ISO string and convert to Unix timestamp
            if s.endswith('Z'):
                s = s.replace('Z', '+00:00')
            dt = datetime.fromisoformat(s)
            return int(dt.timestamp())
        except Exception:
            return None
    
    from_ts = parse_iso(from_param)
    to_ts = parse_iso(to)
    
    # Default to last 7 days if no range specified
    if not from_ts:
        from_ts = int(time.time()) - (7 * 24 * 3600)
    if not to_ts:
        to_ts = int(time.time())
    
    # Fetch historical data
    rows = fetch_history_since(from_ts)
    
    # Filter by end time and structure for Chart.js
    ph_series = []
    ec_series = []
    temp_series = []
    
    for row in rows:
        ts = row.get("ts")
        if ts and ts <= to_ts:
            if row.get("ph") is not None:
                ph_series.append({"ts": ts, "value": row["ph"]})
            if row.get("ec_ms_cm") is not None:
                ec_series.append({"ts": ts, "value": row["ec_ms_cm"]})
            if row.get("temp_c") is not None:
                temp_series.append({"ts": ts, "value": row["temp_c"]})
    
    return {
        "series": {
            "ph": ph_series,
            "ec": ec_series,
            "temp": temp_series
        }
    }

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
    from app.settings import get_settings, get_todays_lights_window
    settings = get_settings()

    # Also include today's lights window preview for UI/verify scripts
    window = {}
    try:
        on_dt, off_dt = get_todays_lights_window()
        window = {
            "on_time": on_dt.strftime("%H:%M"),
            "off_time": off_dt.strftime("%H:%M"),
            "on_datetime": on_dt.isoformat(),
            "off_datetime": off_dt.isoformat(),
        }
    except Exception as e:
        window = {"error": str(e)}

    return {
        "system_volume_liters": settings.system_volume_liters,
        "lights_on_time": settings.lights_on_time,
        "lights_duration_hours": settings.lights_duration_hours,
        "today_window": window,
    }

@app.put("/settings")
def update_settings_api(
    system_volume_liters: Optional[float] = Body(None),
    lights_on_time: Optional[str] = Body(None), 
    lights_duration_hours: Optional[int] = Body(None)
):
    """Update system settings with validation"""
    from app.settings import update_settings, get_todays_lights_window
    
    try:
        updated_settings = update_settings(
            system_volume_liters=system_volume_liters,
            lights_on_time=lights_on_time,
            lights_duration_hours=lights_duration_hours
        )
        
        # Apply settings effects: recompute scheduler immediately (edge-only; no catch-up)
        _scheduler._update_lights_schedule()

        # Include today's window in response for immediate UI preview
        window = {}
        try:
            on_dt, off_dt = get_todays_lights_window()
            window = {
                "on_time": on_dt.strftime("%H:%M"),
                "off_time": off_dt.strftime("%H:%M"),
                "on_datetime": on_dt.isoformat(),
                "off_datetime": off_dt.isoformat(),
            }
        except Exception as e:
            window = {"error": str(e)}

        return {
            "system_volume_liters": updated_settings.system_volume_liters,
            "lights_on_time": updated_settings.lights_on_time,
            "lights_duration_hours": updated_settings.lights_duration_hours,
            "today_window": window,
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

# Chiller override dedicated endpoints (thin wrapper over overrides module)
@app.get("/chiller/override")
def get_chiller_override():
    """Return current chiller override mode.
    Response: {"override": "auto|force_on|force_off"}
    """
    from app.overrides import get_overrides
    ov = get_overrides()
    return {"override": ov.chiller_mode}


@app.put("/chiller/override")
def set_chiller_override(body: dict = Body(...)):
    """Set chiller override mode. Body: {"override": "auto|force_on|force_off"}
    Persists to DB and applies via control_chiller().
    """
    from app.overrides import set_overrides, control_chiller

    override = str(body.get("override", "")).lower()
    if override not in ("auto", "force_on", "force_off"):
        return JSONResponse(status_code=400, content={"error": "override must be 'auto', 'force_on', or 'force_off'"})

    # Persist setting
    set_overrides(chiller_mode=override)

    # Apply control once, respecting cooldowns (no thermostat in AUTO)
    control_chiller("override")

    return {"override": override}

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
    """Get comprehensive relay status from relays_core with timing info"""
    from app.relays_core import get_relay_status
    return get_relay_status()

@app.get("/relay/debug")
def relay_debug():
    """Get detailed relay debug information including antiflap state"""
    from app.relays_core import _antiflap_until, _last_change_ts, _change_history, RELAY_PINS
    import time
    
    now = time.monotonic()
    debug_info = {}
    
    for name in RELAY_PINS.keys():
        antiflap_remaining = 0
        if name in _antiflap_until and now < _antiflap_until[name]:
            antiflap_remaining = int(_antiflap_until[name] - now)
        
        history = _change_history.get(name, [])
        recent_changes = [ts for ts, _ in history if ts > now - 300]  # Last 5 minutes
        
        debug_info[name] = {
            "antiflap_remaining": antiflap_remaining,
            "recent_changes_5min": len(recent_changes),
            "seconds_since_last_change": int(now - _last_change_ts.get(name, now))
        }
    
    return debug_info

@app.post("/relay/set")
def relay_set_new(body: dict = Body(...)):
    """Set relay state using proper relays_core with whitelisted 'override' reason"""
    from app.relays_core import (
        set_lights, set_main_pump, set_chiller_pump, set_chiller_power,
        set_dosing_grow, set_dosing_micro, set_dosing_bloom, set_dosing_ph_up, RELAY_PINS
    )
    
    name = body.get("name")
    on = body.get("on", False)
    
    # Validate relay name
    if name not in RELAY_PINS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid relay name '{name}'. Valid names: {list(RELAY_PINS.keys())}"}
        )
    
    # Use whitelisted 'override' reason for manual control
    # Route through specific functions for proper handling
    relay_funcs = {
        "lights": set_lights,
        "main_pump": set_main_pump,
        "chiller_pump": set_chiller_pump,
        "chiller_power": set_chiller_power,
        "dosing_grow": set_dosing_grow,
        "dosing_micro": set_dosing_micro,
        "dosing_bloom": set_dosing_bloom,
        "dosing_ph_up": set_dosing_ph_up,
    }
    
    func = relay_funcs.get(name)
    if func:
        result = func(bool(on), reason="override", force=False)
    else:
        # Fallback for any other relays
        from app.relays_core import set_relay
        result = set_relay(name, bool(on), reason="override", force=False)
    # Trace via debug module
    try:
        trace_relay_request(name, bool(on), "post", {
            "changed": result.get("changed", False),
            "state": result.get("state", False),
            "reason": result.get("reason", "unknown"),
            "cooldown_remaining": result.get("cooldown_remaining", 0)
        })
    except Exception:
        pass
    
    return {
        "ok": True,
        "changed": result.get("changed", False),
        "state": result.get("state", False),
        "reason": result.get("reason", "unknown"),
        "cooldown_remaining": result.get("cooldown_remaining", 0)
    }

@app.get("/relay/set")
def relay_set_query(name: str = Query(...), on: int = Query(...)):
    """Fallback GET handler for relay control via query params. Mirrors /relay/set POST."""
    from app.relays_core import (
        set_lights, set_main_pump, set_chiller_pump, set_chiller_power,
        set_dosing_grow, set_dosing_micro, set_dosing_bloom, set_dosing_ph_up, RELAY_PINS
    )

    desired = bool(int(on))
    if name not in RELAY_PINS:
        return JSONResponse(status_code=400, content={"error": f"Invalid relay name '{name}'"})

    # Route through specific functions for proper handling
    relay_funcs = {
        "lights": set_lights,
        "main_pump": set_main_pump,
        "chiller_pump": set_chiller_pump,
        "chiller_power": set_chiller_power,
        "dosing_grow": set_dosing_grow,
        "dosing_micro": set_dosing_micro,
        "dosing_bloom": set_dosing_bloom,
        "dosing_ph_up": set_dosing_ph_up,
    }
    
    func = relay_funcs.get(name)
    if func:
        result = func(desired, reason="override", force=False)
    else:
        # Fallback for any other relays
        from app.relays_core import set_relay
        result = set_relay(name, desired, reason="override", force=False)
    try:
        trace_relay_request(name, desired, "get", {
            "changed": result.get("changed", False),
            "state": result.get("state", False),
            "reason": result.get("reason", "unknown"),
            "cooldown_remaining": result.get("cooldown_remaining", 0)
        })
    except Exception:
        pass
    return {
        "ok": True,
        "changed": result.get("changed", False),
        "state": result.get("state", False),
        "reason": result.get("reason", "unknown"),
        "cooldown_remaining": result.get("cooldown_remaining", 0)
    }

@app.post("/relay/emergency_off")
def relay_emergency_off():
    """Emergency endpoint to force all relays OFF and clear antiflap protection"""
    from app.relays_core import set_relay, RELAY_PINS, _antiflap_until, _last_change_ts
    import time
    
    results = {}
    # Clear all antiflap protection
    _antiflap_until.clear()
    
    # Force all relays OFF
    for name in RELAY_PINS.keys():
        result = set_relay(name, False, reason="emergency", force=True)
        results[name] = {
            "changed": result.get("changed", False),
            "state": result.get("state", False)
        }
    
    # Reset all change timestamps to allow immediate re-toggling
    now = time.monotonic()
    for name in RELAY_PINS.keys():
        _last_change_ts[name] = now - 1000  # Set to 1000 seconds ago
    
    return {
        "ok": True,
        "message": "All relays forced OFF, antiflap cleared, cooldowns reset",
        "results": results
    }

@app.post("/relay/{name}")
def relay_set_legacy(name: str, body: dict = Body(...)):
    """Legacy endpoint - now redirects to relays_core for consistency"""
    from app.relays_core import set_relay
    state = (body.get("state","").lower() == "on")
    result = set_relay(name, state, reason="override", force=False)
    return {
        "ok": True, 
        "state": result.get("state", False),
        "changed": result.get("changed", False)
    }

@app.get("/relay/persist")
def relay_persist_info():
    import os
    import json
    p = os.environ.get("RDWC_STATE_DIR", os.path.expanduser("~/.rdwc"))
    f = os.path.join(p, "relay_state.json")
    payload = {}
    try:
        with open(f, "r") as fh:
            payload = json.load(fh)
    except Exception:
        payload = {"note": "state file not found"}
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
    cfg = load_cfg()
    cfg["enabled"] = bool(enabled)
    save_cfg(cfg)
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

@app.get("/debug/relay_try")
def debug_relay_try(name: str = Query(...), on: int = Query(...)):
    """Diagnostic endpoint to test relay control bypassing UI cache"""
    from app.relays_core import set_relay, RELAY_PINS
    
    if name not in RELAY_PINS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid relay name '{name}'. Valid names: {list(RELAY_PINS.keys())}"}
        )
    
    result = set_relay(name, bool(on), reason="override", force=False)
    
    return {
        "relay": name,
        "requested": bool(on),
        "changed": result.get("changed", False),
        "state": result.get("state", False),
        "reason": result.get("reason", "unknown"),
        "cooldown_remaining": result.get("cooldown_remaining", 0)
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

@app.get("/sensors/read")
def sensors_read():
    """Get sensor readings with throttled temperature compensation details."""
    from app.sensors_core import read_all_sensors
    try:
        result = read_all_sensors()
        return result
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "errors": [str(e)]}
        )

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

# --- Camera endpoints ---
@app.get("/camera/status")
def camera_status():
    from app.camera import CameraManager
    return CameraManager.status()

@app.get("/camera/stream")
def camera_stream():
    from app.camera import CameraManager
    info = CameraManager.status()
    if not info.get("available", False):
        return JSONResponse(status_code=404, content={"error": "camera unavailable", **info})

    fps = int(os.environ.get("CAM_FPS", "8"))
    boundary = "frame"

    def _gen():
        for part in CameraManager.mjpeg_generator(fps=fps):
            yield part

    return StreamingResponse(
        _gen(), 
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Content-Type-Options": "nosniff"
        }
    )

@app.get("/camera/snapshot.jpg")
def camera_snapshot():
    """Single JPEG snapshot from current camera frame."""
    from app.camera import CameraManager
    
    jpeg_bytes = CameraManager.capture_single_frame()
    
    if jpeg_bytes is None:
        # Return minimal 1x1 red JPEG as fallback
        fallback_jpeg = (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c'
            b'\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c'
            b'\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00'
            b'\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xc4\x00\x14\x10'
            b'\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\x00\xff\xd9'
        )
        return StreamingResponse(
            io.BytesIO(fallback_jpeg),
            media_type="image/jpeg",
            status_code=503,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"
            }
        )
    
    return StreamingResponse(
        io.BytesIO(jpeg_bytes),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"
        }
    )

@app.get("/camera/stream/health")
def camera_stream_health():
    """Health check for camera stream - 204 if healthy, 503 if not."""
    from app.camera import CameraManager
    
    if CameraManager.is_healthy():
        return StreamingResponse(content=iter([]), status_code=204)
    else:
        return JSONResponse(status_code=503, content={"healthy": False})

# --- Dose jog endpoint ---
_jog_last = {}
_jog_locks = {name: threading.Lock() for name in [
    "dosing_grow","dosing_micro","dosing_bloom","dosing_ph_up"
]}

@app.post("/dose/jog")
def dose_jog(body: dict = Body(...)):
    from app.relays_core import (
        set_dosing_grow, set_dosing_micro, set_dosing_bloom, set_dosing_ph_up
    )
    name_in = str(body.get("name", "")).strip()
    ms = int(body.get("ms", 500))
    ms = max(50, min(2000, ms))

    # name mapping and whitelist
    name_map = {
        "dosing_grow": ("dosing_grow", set_dosing_grow),
        "dosing_micro": ("dosing_micro", set_dosing_micro),
        "dosing_bloom": ("dosing_bloom", set_dosing_bloom),
        "dosing_ph_up": ("dosing_ph_up", set_dosing_ph_up),
        "ph_up": ("dosing_ph_up", set_dosing_ph_up),
    }
    if name_in not in name_map:
        return JSONResponse(status_code=400, content={"error": "invalid name", "allowed": list(name_map.keys())})
    relay_name, setter = name_map[name_in]

    # cooldown check (5s per pump)
    now = time.monotonic()
    last = _jog_last.get(relay_name, 0)
    if now - last < 5:
        remaining = int(5 - (now - last))
        return {"ok": False, "started": False, "cooldown_remaining": max(0, remaining)}

    lock = _jog_locks[relay_name]
    if not lock.acquire(blocking=False):
        return {"ok": False, "started": False, "error": "concurrent_jog"}

    try:
        # turn ON via relays_core (respecting cooldowns)
        res_on = setter(True, reason="dose_jog", force=False)
        if not res_on.get("changed", False) and not res_on.get("state", False):
            # blocked by cooldown or antiflap
            return {
                "ok": False,
                "started": False,
                "reason": res_on.get("reason", "unknown"),
                "cooldown_remaining": res_on.get("cooldown_remaining", 0)
            }
        # Jog duration (bounded)
        time.sleep(ms/1000.0)
    finally:
        # Ensure OFF, even if sleep raised or client disconnected
        try:
            setter(False, reason="dose_jog", force=False)
        except Exception:
            pass
        _jog_last[relay_name] = time.monotonic()
        lock.release()

    return {"ok": True, "started": True, "ms": ms}

# --- CSV export ---
@app.get("/export/sensors.csv", response_class=PlainTextResponse)
def export_sensors_csv(hours: float = Query(24.0)):
    secs = max(60, int(hours * 3600))
    since = int(time.time()) - secs
    rows = fetch_history_since(since)

    def _iter():
        yield "ts,temp_c,ph,ec_uS,ec_mS,comp_temp_c,t_write\n"
        for r in rows:
            ts = r.get("ts", "")
            temp_c = r.get("temp_c", "")
            ph = r.get("ph", "")
            ec_ms = r.get("ec_ms_cm", None)
            ec_us = int(ec_ms*1000) if isinstance(ec_ms, (int, float)) else ""
            ec_ms_out = ec_ms if ec_ms is not None else ""
            comp_t = ""  # not stored per-row
            t_write = ""  # not stored per-row
            yield f"{ts},{temp_c},{ph},{ec_us},{ec_ms_out},{comp_t},{t_write}\n"

    return StreamingResponse(_iter(), media_type="text/csv")

# --- Calibration stubs ---
@app.post("/calib/ph/start")
def calib_ph_start():
    steps = [
        "Rinse probe",
        "Place in 7.00 buffer",
        "Place in 4.00 buffer",
        "Confirm and (optionally) apply"
    ]
    return {"ok": True, "mode": "ph", "steps": steps, "note": "Writes are disabled by default."}

@app.post("/calib/ph/apply")
def calib_ph_apply():
    enabled = os.environ.get("CALIB_ENABLE", "0") == "1"
    if not enabled:
        return {"ok": False, "applied": False, "note": "Calibration writes disabled. Set CALIB_ENABLE=1 to enable."}
    # TODO: perform actual calibration commands to the probe when enabled
    return {"ok": True, "applied": False, "note": "Stub only - implement calibration logic when enabled."}