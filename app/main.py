from fastapi import FastAPI, Body, Query, APIRouter, Response
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import threading
import time
import os
import csv
import io
import asyncio
from contextlib import suppress
from typing import Optional, Any
from subprocess import run, PIPE
from datetime import datetime, timedelta  # Keep global import
from app.debug import router as debug_router, trace_relay_request
import logging
logger = logging.getLogger(__name__)
# NOTE: Avoid importing EZO/I2C helpers at module import time to prevent
# accidental /dev/i2c-1 ownership by the web process. Perform lazy imports
# within endpoints that explicitly request direct hardware access.
from app.diag import router as diag_router
from app.blueprints.sensors_api import sensors_router
from app.blueprints.frontend_logs_api import router as frontend_logs_router
from app.blueprints.commissioning_api import router as commissioning_router
from app.hardware import PumpController, RelayBank
from app.ph_control import router as ph_router
from app.ec_control import router as ec_router
from app.schedule_api import router as schedule_router
from app.logger import log_reading, last_n, fetch_history_since
from app.scheduler import Scheduler, load_cfg, save_cfg
from app.monitor import start_monitoring, stop_monitoring, get_monitoring_status
from app.relays_core import initialize_all_safe_off, get_relay_event_log, allowed_lights_reasons, set_lights_hold
from app.relays_core import set as relay_set
from app.relays_core import get_estop_status
from app.relays_core import get_relay_status
# Removed unused lru_cache import

DB_PATH = os.environ.get("RDWC_DB", os.path.join(os.path.dirname(__file__), "..", "data", "rdwc.db"))
DB_PATH = os.path.abspath(DB_PATH)

def _compute_asset_version() -> str:
    """Return a robust asset version token for cache busting.
    Preference order:
    1) ASSET_VERSION env var (explicit override)
    2) Current git short SHA of the repo
    3) UTC timestamp down to seconds
    """
    v = os.environ.get("ASSET_VERSION")
    if v:
        # Sanitize: ignore suspicious values (paths or empty)
        vv = str(v).strip()
        if vv and all((c.isalnum() or c in "-_.") for c in vv):
            return vv
    # Try git short SHA from repository root
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        res = run(["git", "-C", repo_root, "rev-parse", "--short", "HEAD"], stdout=PIPE, stderr=PIPE, text=True)
        if res.returncode == 0:
            sha = (res.stdout or "").strip()
            if sha:
                return sha
    except Exception:
        pass
    # Fallback: timestamp to seconds ensures a new value on each service start
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")

# Asset version for cache-busting of static JS/CSS assets (used by /api/version and loader)
ASSET_VERSION = _compute_asset_version()

app = FastAPI()
progress_router = APIRouter()

# --- Progress state (in-memory with occasional recompute) ---
_progress_cache = {
    "last_compute_ts": 0.0,
    "percent": 0.0,
    "components": {},
    "eta_minutes": None,
    "heartbeat_ts": time.time(),
}

def _progress_components() -> dict:
    """Compute component OK flags used by UI progress widget.
    Lightweight: relies on existing endpoints/helpers instead of extra sensor reads.
    """
    comps = {}
    # relays/system mode & estop
    try:
        from app.relays_core import get_relay_status, get_estop_status
        rs = get_relay_status()  # Returns {relay_name: {state, ...}}
        estop = get_estop_status()
        # System healthy when relays readable and E-STOP not active
        comps['system'] = bool(rs and (estop is False))
        # Lights component true if lights relay exists
        comps['lights'] = bool(rs and 'lights' in rs)
    except Exception:
        comps['system'] = False
        comps['lights'] = False
    # sensors (read from DB cache, not I²C directly)
    try:
        from app.sensors_core import read_sensors_from_db
        d = read_sensors_from_db(max_age_sec=15)  # Fresh if <15s old
        comps['sensors'] = bool(d and d.get('online'))
    except Exception:
        comps['sensors'] = False
    # pH
    try:
        from app.ph_control import ph_status
        phs = ph_status()
        hard = bool(phs and (phs.get('guards', {}).get('estop') or phs.get('guards', {}).get('sensor_stale') or phs.get('guards', {}).get('reservoir')))
        comps['ph'] = bool(phs and not hard)
    except Exception:
        comps['ph'] = False
    # EC
    try:
        from app.ec_control import get_ec_status
        ecs = get_ec_status()
        hard = bool(ecs and (ecs.get('guards', {}).get('estop') or ecs.get('guards', {}).get('sensor_stale') or ecs.get('guards', {}).get('reservoir')))
        comps['ec'] = bool(ecs and not hard)
    except Exception:
        comps['ec'] = False
    # schedule
    try:
        from app.schedule_api import get_nutrient_schedule
        sch = get_nutrient_schedule()
        comps['schedule'] = bool(sch and sch.get('weeks'))
    except Exception:
        comps['schedule'] = False
    # environment (chiller control running)
    try:
        from app.temperature_control import get_temperature_state
        ch = get_temperature_state()
        comps['env'] = bool(ch)
    except Exception:
        comps['env'] = False
    # tests (allow override via env or DB setting key 'tests.pass')
    try:
        tests_env = os.environ.get('RDWC_TESTS_PASS', '0')
        tests_ok = (tests_env == '1')
        if not tests_ok:
            try:
                from app.settings import get_setting_key
                tests_ok = str(get_setting_key('tests.pass', '0')).lower() in ('1', 'true')
            except Exception:
                tests_ok = False
        comps['tests'] = bool(tests_ok)
    except Exception:
        comps['tests'] = False
    return comps

def _progress_percent(comps: dict) -> float:
    weights = {
        'system':15,'sensors':20,'ph':15,'ec':15,'schedule':10,'env':10,'lights':10,'tests':5
    }
    pct = 0.0
    for k, w in weights.items():
        if comps.get(k):
            pct += w
    return pct

def _progress_eta(pct: float) -> int | None:
    if pct >= 99.9:
        return 0
    remain = max(0.0, 100.0 - pct)
    # simple heuristic like UI: early pessimistic then linear
    if pct < 30:
        return int((remain/10.0)*2)  # 2m per 10% block early
    return int((remain/20.0))        # 1m per 20% later

@progress_router.get('/api/progress')
def api_progress(force: bool = Query(False)):
    """Server-side progress snapshot consumed by UI/banner.
    Cached for 5s unless force=true to avoid hammering subsystems.
    """
    now = time.time()
    if force or (now - _progress_cache['last_compute_ts'] > 5):
        comps = _progress_components()
        pct = _progress_percent(comps)
        eta = _progress_eta(pct)
        _progress_cache.update({
            'last_compute_ts': now,
            'components': comps,
            'percent': pct,
            'eta_minutes': eta,
            'heartbeat_ts': now,
        })
    return {
        'percent': round(_progress_cache['percent'],2),
        'eta_minutes': _progress_cache['eta_minutes'],
        'heartbeat_age_s': int(time.time() - _progress_cache['heartbeat_ts']),
        'components': _progress_cache['components'],
        'cached': True,
        'computed_ts': _progress_cache['last_compute_ts'],
    }

 

# --- Startup hook: ensure sensor LEDs honor persistent setting (default ON) ---
@app.on_event("startup")
def _startup_leds_apply():
    try:
        from app.settings import get_all_settings, upsert_settings
        from app.sensor_controller import set_sensor_leds
        s = get_all_settings()
        # Seed default if missing (should already be in DEFAULTS but guard anyway)
        if "sensors.leds_enabled" not in s:
            upsert_settings({"sensors.leds_enabled": "1"})
            s["sensors.leds_enabled"] = "1"
        want_on = s.get("sensors.leds_enabled", "1") in ("1", "true", "True")
        set_sensor_leds(want_on)
    except Exception:
        # Non-fatal: service continues even if LEDs can't be set
        pass

@app.on_event("startup")
def _startup_system_metrics():
    """Initialize system metrics table on startup"""
    try:
        from app.system_metrics import init_system_metrics_table
        init_system_metrics_table()
    except Exception as e:
        logger.debug(f"System metrics table init skipped or failed: {e}")

@app.on_event("startup")
def _startup_migrate_auto_control():
    """Migrate old mode systems to new clean auto_control system (one-time)"""
    try:
        from app.auto_control import migrate_from_legacy
        migrate_from_legacy()
    except Exception as e:
        from app.logger import get_logger
        logger = get_logger()
        logger.warning(f"Auto-control migration failed (non-fatal): {e}")

@app.on_event("startup")
def _startup_seed_lights_events():
    """Seed lights event log with historical data on startup."""
    try:
        from app.relays_core import _relay_event_logs
        from datetime import datetime, timedelta
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Clear any stale events on startup
        _relay_event_logs["lights"].clear()
        
        start_date = datetime(2025, 12, 1, 0, 0, 0)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        lights_on_time = "15:00"
        lights_duration_hours = 16
        
        on_h, on_m = map(int, lights_on_time.split(':'))
        
        current_date = start_date
        event_count = 0
        while current_date <= today:
            on_datetime = current_date.replace(hour=on_h, minute=on_m, second=0)
            _relay_event_logs["lights"].append({
                "ts": on_datetime.isoformat(),
                "requested": False,
                "final": True,
                "reason": "schedule",
                "cooldown": 0,
                "blocked": False,
                "caller": "scheduler:edge"
            })
            event_count += 1
            
            off_datetime = on_datetime + timedelta(hours=lights_duration_hours)
            _relay_event_logs["lights"].append({
                "ts": off_datetime.isoformat(),
                "requested": False,
                "final": False,
                "reason": "schedule",
                "cooldown": 0,
                "blocked": False,
                "caller": "scheduler:edge"
            })
            event_count += 1
            
            current_date += timedelta(days=1)
        
        logger.info(f"Seeded {event_count} lights events from Dec 1 to today")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Seed lights events failed (non-fatal): {e}")

# --- Sensor LED state endpoints (persistent) ---
@app.get("/api/sensors/leds")
def api_sensors_leds():
    try:
        from app.settings import get_all_settings
        s = get_all_settings()
        enabled = s.get("sensors.leds_enabled", "1") in ("1", "true", "True")
        return {"ok": True, "enabled": enabled}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/sensors/leds")
def api_sensors_leds_set(enable: bool = True):
    """Persist and apply sensor LED state (Atlas EZO L,1 / L,0)."""
    try:
        from app.settings import upsert_settings
        from app.sensor_controller import set_sensor_leds
        upsert_settings({"sensors.leds_enabled": "1" if enable else "0"})
        result = set_sensor_leds(enable)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Request audit middleware: log all requests to detect unexpected POSTs
class RequestAuditMiddleware(BaseHTTPMiddleware):
    """
    Logs all requests with:
    - method, path, query params
    - body preview (first 256 bytes) for POST/PUT
    - per-minute POST/PUT counter by path
    
    Purpose: Detect unexpected POST/PUT requests on UI tab loads (should be GET/OPTIONS only)
    """
    def __init__(self, app):
        super().__init__(app)
        self._write_counts = {}  # {path: {minute_bucket: count}}
        import logging
        self.logger = logging.getLogger("request_audit")
    
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path
        query = str(request.query_params) if request.query_params else ""
        client = request.client.host if request.client else "unknown"

        # Only audit write methods to reduce noise
        if method in ("POST", "PUT", "PATCH"):
            # Log without reading body to avoid blocking - body reading can cause issues
            log_msg = f"request_audit method={method} path={path} actor={client}"
            if query:
                log_msg += f" query={query}"
            self.logger.info(log_msg)

            # Per-minute write counts
            minute_bucket = int(time.time() // 60)
            if path not in self._write_counts:
                self._write_counts[path] = {}
            self._write_counts[path][minute_bucket] = self._write_counts[path].get(minute_bucket, 0) + 1
            count = self._write_counts[path][minute_bucket]
            if count > 10:
                self.logger.warning(f"request_audit_highfreq path={path} count_per_min={count}")

        # Process request
        response = await call_next(request)
        return response

app.add_middleware(RequestAuditMiddleware)

app.include_router(diag_router)
app.include_router(debug_router, prefix="/debug", tags=["debug"])
app.include_router(sensors_router)
app.include_router(frontend_logs_router)
app.include_router(commissioning_router)
app.include_router(ph_router)
app.include_router(ec_router)
app.include_router(schedule_router)
app.include_router(progress_router)

# --- System metrics (current snapshot + history) ---
@app.get('/api/system/metrics/current')
def api_system_metrics_current():
    try:
        from app.system_metrics import collect_current_metrics  # lazy import
        data = collect_current_metrics()
        return {"ok": True, "data": data}
    except Exception as e:
        logger.exception("system metrics current failure")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@app.get('/api/system/metrics/history')
def api_system_metrics_history(
    start_hours: int = Query(24, ge=1, le=168),
    metrics: str = Query("cpu_percent,memory_percent,disk_percent,core_voltage_v,load_1m,load_5m,load_15m,net_rx_bytes,net_tx_bytes")
):
    """Query system metrics history.
    
    Args:
        start_hours: How many hours back (1-168, default 24)
        metrics: Comma-separated metric names
    
    Returns:
        List of samples with requested metrics.
    """
    try:
        from app.system_metrics import get_metrics_history  # lazy import
        import time
        
        end_ts = int(time.time())
        start_ts = end_ts - (start_hours * 3600)
        
        # Validate and filter metric names
        allowed = {
            "ts", "cpu_percent", "memory_percent", "disk_percent", "core_voltage_v",
            "load_1m", "load_5m", "load_15m", "net_rx_bytes", "net_tx_bytes"
        }
        requested = {m.strip() for m in metrics.split(",")}
        valid_metrics = [m for m in requested if m in allowed]
        
        data = get_metrics_history(start_ts, end_ts, valid_metrics)
        return {
            "ok": True,
            "count": len(data),
            "start_ts": start_ts,
            "end_ts": end_ts,
            "hours": start_hours,
            "metrics": valid_metrics,
            "data": data
        }
    except Exception as e:
        logger.exception("system metrics history failure")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

# --- Server-Sent Events (SSE) sensor stream ---
# Provides a lightweight continuous feed of consolidated sensor payloads.
# Frontend subscribes via EventSource("/api/sensors/stream") and updates KPI elements
# without maintaining multiple polling intervals. Falls back to legacy /api/sensors polling
# automatically if the stream errors out.
@app.get("/api/sensors/stream")
async def api_sensors_stream():
    import json, asyncio
    from app.sensors_core import read_all_sensors  # cached / lock-aware read

    async def _gen():
        logger.info("[SSE] /api/sensors/stream client connected")
        # Initial retry/backoff parameters (simple linear fallback on errors)
        backoff_s = 0
        while True:
            try:
                if backoff_s > 0:
                    await asyncio.sleep(backoff_s)
                payload = read_all_sensors()  # {temperature_c, ph, ec_mscm, online, ts, errors, cal?, original_*?}
                data = json.dumps(payload, separators=(",", ":"))
                # SSE format: optional event name for filtering
                yield f"event: sensors\ndata: {data}\n\n"
                backoff_s = 0  # reset after success
                await asyncio.sleep(2)  # stream cadence (was multi-interval polling)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # On error: send diagnostic event and apply bounded backoff
                err = json.dumps({"error": str(e)[:160]})
                yield f"event: sensors_error\ndata: {err}\n\n"
                backoff_s = min(10, (backoff_s or 1) * 2)
                await asyncio.sleep(backoff_s)
        # Optional final event (client usually closed already)
        yield "event: sensors_end\ndata: {}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")

# Handle favicon to avoid 404 noise in browser console
@app.get("/favicon.ico", include_in_schema=False)
def favicon_placeholder():
    return Response(status_code=204)

# Mount static files directory for serving CSS/JS
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

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
# Sensor diagnostics for UI popover and troubleshooting
_sensor_diag = {
    "restarts": 0,              # watchdog-triggered restarts
    "last_watchdog_ts": None,   # epoch seconds when watchdog restarted loop
    "last_error": None,         # last exception string from sensor_loop
    "last_error_ts": None       # epoch seconds for last error
}
START_TS = time.time()
sensor_task = None
watchdog_task = None

def _sensor_loop():
    global _last, _last_t
    while True:
        try:
            from app.sensor_controller import read_sensors
            data = read_sensors()
            _last = {
                "temp_c": data.get("temperature_c"),
                "ph": data.get("ph"),
                "ec_ms_cm": data.get("ec_mscm"),
                "errors": data.get("errors", {})
            }
            _last_t = time.time()
            # Always log to preserve history; NULLs allowed when some sensors are offline
            log_reading(_last["temp_c"], _last["ph"], _last["ec_ms_cm"])
        except Exception as e:
            _last = {"temp_c": None, "ph": None, "ec_ms_cm": None, "errors": {"loop": str(e)}}
        time.sleep(10)

async def sensor_loop():
    """Async version of sensor loop for proper startup management"""
    global _last, _last_t, _sensor_diag
    while True:
        try:
            from app.sensor_controller import read_sensors
            data = read_sensors()
            _last = {
                "temp_c": data.get("temperature_c"),
                "ph": data.get("ph"),
                "ec_ms_cm": data.get("ec_mscm"),
                "errors": data.get("errors", {})
            }
            _last_t = time.time()
            # Always log to preserve history; NULLs allowed when some sensors are offline
            log_reading(_last["temp_c"], _last["ph"], _last["ec_ms_cm"])
        except Exception as e:
            _last = {"temp_c": None, "ph": None, "ec_ms_cm": None, "errors": {"loop": str(e)}}
            # Record diagnostics for UI popover
            try:
                _sensor_diag["last_error"] = str(e)
                _sensor_diag["last_error_ts"] = time.time()
            except Exception:
                pass
        await asyncio.sleep(10)

@app.on_event("startup")
async def _start_tasks():
    global sensor_task, watchdog_task
    # Initialize system mode tables
    from app.unified_mode import _init_tables
    _init_tables()
    
    # Initialize relay guard (shadow state tracking + structured logging)
    try:
        from app.relay_guard import init_safe
        init_safe()
        print("[RelayGuard] Initialized with shadow state tracking")
    except Exception as e:
        print(f"[RelayGuard] WARNING: Failed to initialize: {e}")
    
    # E-STOP persisted state: honor before any auto-restore
    estop_persisted = False
    try:
        from app.settings import get_setting_key
        val = (get_setting_key('estop_active', 'false') or 'false').lower()
        estop_persisted = (val == 'true')
    except Exception:
        estop_persisted = False

    if estop_persisted:
        try:
            from app.relays_core import engage_estop
            engage_estop()
        except Exception:
            pass
        print("E-STOP persisted: ACTIVE")
    else:
        print("E-STOP persisted: INACTIVE")
        # Smart restore relay states based on system_mode (auto/manual)
        # This replaces the old _load_state() with mode-aware restoration
        from app.relays_core import smart_restore_critical_relays
        smart_restore_critical_relays()
    
    # Sync relay_guard shadow state from actual pin levels after restoration
    try:
        from app.relay_guard import sync_from_actual
        sync_from_actual()
        print("[RelayGuard] Synced shadow state from actual pin levels")
    except Exception as e:
        print(f"[RelayGuard] WARNING: Failed to sync from actual: {e}")
    
    # Start async sensor loop (single reader) - DISABLED by default in production
    # (standalone sensor poller runs as rdwc-sensors.service)
    SENSOR_LOOP_ENABLED = os.environ.get("SENSOR_LOOP_ENABLED", "false").lower() == "true"
    if SENSOR_LOOP_ENABLED:
        sensor_task = asyncio.create_task(sensor_loop(), name="sensor_loop")
        print("Web sensor_loop ENABLED (legacy mode)")
        
        # Start sensors watchdog (auto-heal if stale) - only when sensor_loop is enabled
        async def sensors_watchdog():
            global sensor_task, _last_t, _sensor_diag
            STALE_SEC = int(os.environ.get("RDWC_SENSORS_STALE_SEC", "120"))
            INTERVAL = int(os.environ.get("RDWC_SENSORS_WATCHDOG_INTERVAL", "30"))
            while True:
                try:
                    age = time.time() - _last_t
                    if age > STALE_SEC:
                        # Attempt auto-heal: reset I2C and restart sensor task
                        try:
                            from app.infra.i2c_bus import close_bus
                            close_bus()
                        except Exception:
                            pass
                        # Restart sensor task
                        with suppress(Exception):
                            if sensor_task:
                                sensor_task.cancel()
                        await asyncio.sleep(0.1)
                        sensor_task = asyncio.create_task(sensor_loop(), name="sensor_loop")
                        # Update diagnostics
                        try:
                            _sensor_diag["restarts"] = int(_sensor_diag.get("restarts", 0)) + 1
                            _sensor_diag["last_watchdog_ts"] = time.time()
                        except Exception:
                            pass
                    await asyncio.sleep(INTERVAL)
                except Exception:
                    await asyncio.sleep(INTERVAL)
        watchdog_task = asyncio.create_task(sensors_watchdog(), name="sensors_watchdog")
    else:
        print("Web sensor_loop DISABLED (using standalone poller)")
    _scheduler.start()
    # Start alert monitoring
    start_monitoring()
    # Initialize camera (non-blocking; will gracefully stay unavailable if drivers missing)
    try:
        from app.camera import CameraManager
        CameraManager.init()
    except Exception:
        pass

    # Finalize and activate chiller automatic control with safe defaults
    try:
        from app.settings import upsert_settings
        # Ensure compressor safety and a slightly wider deadband to reduce cycling
        upsert_settings({
            'chiller.target_temp': '19.0',
            'chiller.hysteresis': '0.7',
            'chiller.min_on_seconds': '300',
            'chiller.min_off_seconds': '600',
            'chiller.control_interval_s': '30',
            'chiller.auto_enabled': '1'
        })
        from app.temperature_control import start_auto_control
        start_auto_control()
    except Exception as e:
        # Non-fatal: start control loop even if auto_enable fails
        try:
            from app.temperature_control import start_auto_control
            start_auto_control()
        except Exception as e2:
            print(f"[Temperature] Failed to start control loop: {e2}")

    # Start relay watchdog (detect unexpected relay energization)
    async def relay_watchdog():
        """250ms watchdog: detect unexpected LOW (ON) states and force safe"""
        from app.relay_guard import get_pin_levels, get_shadow_state, force_off
        import logging
        logger = logging.getLogger("relay_watchdog")
        
        while True:
            try:
                await asyncio.sleep(0.25)  # 250ms polling
                
                # Read actual pin levels
                actual_levels = get_pin_levels()
                shadow_state = get_shadow_state()
                
                # Check for unexpected LOW (active-low: LOW = ON/energized)
                for relay_name, shadow_is_on in shadow_state.items():
                    actual_level = actual_levels.get(relay_name)

                    # Determine expected pin level per wiring (NO vs NC)
                    try:
                        from app.relay_guard import NC_RELAYS
                        is_nc = relay_name in NC_RELAYS
                    except Exception:
                        is_nc = False
                    # For NO: ON->LOW, OFF->HIGH; For NC: ON->HIGH, OFF->LOW
                    if is_nc:
                        expected_level = "HIGH" if shadow_is_on else "LOW"
                    else:
                        expected_level = "LOW" if shadow_is_on else "HIGH"

                    if actual_level != expected_level:
                        # ANOMALY: Actual pin state doesn't match shadow state
                        anomaly_reason = f"watchdog_anomaly:expected={expected_level},actual={actual_level}"
                        logger.error(f"[RelayWatchdog] ANOMALY on {relay_name}: {anomaly_reason}")
                        force_off(relay_name, anomaly_reason)
                        
            except Exception as e:
                logger.error(f"[RelayWatchdog] Error in watchdog loop: {e}")
                await asyncio.sleep(1.0)  # Back off on error
    
    relay_watchdog_task = asyncio.create_task(relay_watchdog(), name="relay_watchdog")
    print("[RelayWatchdog] Started 250ms polling for unexpected relay energization")

@app.on_event("shutdown")  
async def _stop_tasks():
    global sensor_task, watchdog_task
    with suppress(Exception):
        if sensor_task:
            sensor_task.cancel()
    with suppress(Exception):
        if watchdog_task:
            watchdog_task.cancel()
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

@app.get("/api/system/info")
def get_system_info():
    """
    Comprehensive system information for System tab.
    Returns Pi hardware stats, software versions, environment details,
    database statistics, network info, and process status.
    """
    import platform
    import socket
    import subprocess
    from pathlib import Path
    
    try:
        import psutil
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"error": "psutil not installed - run: pip install psutil>=5.9.0"}
        )
    
    info = {}
    
    # ===== RASPBERRY PI INFO =====
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_freq = psutil.cpu_freq()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Try to read Pi temperature
        pi_temp = None
        try:
            temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
            if temp_path.exists():
                temp_raw = int(temp_path.read_text().strip())
                pi_temp = round(temp_raw / 1000.0, 1)
        except Exception:
            pass
        
        # Uptime
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        uptime_str = str(timedelta(seconds=uptime_seconds))
        
        info["pi_info"] = {
            "cpu_percent": round(cpu_percent, 1),
            "cpu_freq_mhz": round(cpu_freq.current, 0) if cpu_freq else None,
            "cpu_count": psutil.cpu_count(),
            "temperature_c": pi_temp,
            "load_avg": os.getloadavg() if hasattr(os, "getloadavg") else None,
            "memory_total_mb": round(mem.total / 1024 / 1024, 0),
            "memory_used_mb": round(mem.used / 1024 / 1024, 0),
            "memory_percent": round(mem.percent, 1),
            "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
            "disk_percent": round(disk.percent, 1),
            "uptime_seconds": uptime_seconds,
            "uptime_human": uptime_str,
            "platform": platform.platform()
        }

        # Pi power/voltage/throttle (measured via vcgencmd when available)
        try:
            # Core voltage
            vres = subprocess.run(["vcgencmd", "measure_volts"], capture_output=True, text=True, timeout=2)
            core_v = None
            if vres.returncode == 0 and "volt=" in vres.stdout:
                # Example: volt=0.86V
                out = vres.stdout.strip()
                try:
                    core_v = float(out.split("=")[1].replace("V", ""))
                except Exception:
                    core_v = None

            # Throttled flags
            tres = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2)
            throttled_raw = None
            flags = 0
            if tres.returncode == 0 and "throttled=" in tres.stdout:
                raw = tres.stdout.strip().split("=")[1]
                throttled_raw = raw
                try:
                    flags = int(raw, 16) if raw.startswith("0x") else int(raw)
                except Exception:
                    flags = 0

            # Interpret flags per Raspberry Pi docs
            def has(bit):
                return bool(flags & (1 << bit))

            info["pi_info"].update({
                "core_voltage_v": core_v,
                "throttled_raw": throttled_raw,
                "under_voltage": has(0),
                "freq_capped": has(1),
                "throttled": has(2),
                "soft_temp_limit": has(3),
                "under_voltage_has_occurred": has(16),
                "freq_capped_has_occurred": has(17),
                "throttled_has_occurred": has(18),
                "soft_temp_limit_has_occurred": has(19),
            })
        except Exception:
            # vcgencmd not available or failed; skip gracefully
            pass

        # CPU governor (best-effort)
        try:
            gov_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
            if gov_path.exists():
                info["pi_info"]["cpu_governor"] = gov_path.read_text().strip()
        except Exception:
            pass
    except Exception as e:
        info["pi_info"] = {"error": str(e)}
    
    # ===== SOFTWARE INFO =====
    try:
        # RDWC version
        version_file = Path(__file__).parent.parent / "VERSION"
        rdwc_version = version_file.read_text().strip() if version_file.exists() else "unknown"
        
        # Git info
        git_info = {}
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=Path(__file__).parent.parent,
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                git_info["commit"] = result.stdout.strip()
            
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=Path(__file__).parent.parent,
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                git_info["branch"] = result.stdout.strip()
        except Exception:
            git_info = {"error": "git not available"}
        
        # Python version
        python_version = platform.python_version()
        
        # Service status (systemd)
        services = {}
        for service_name in ["rdwc", "rdwc-sensors"]:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service_name],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                services[service_name] = result.stdout.strip()
            except Exception:
                services[service_name] = "unknown"
        
        info["software_info"] = {
            "rdwc_version": rdwc_version,
            "python_version": python_version,
            "fastapi_version": "installed",  # Could import to get exact version
            "git": git_info,
            "services": services
        }
    except Exception as e:
        info["software_info"] = {"error": str(e)}
    
    # ===== ENVIRONMENT INFO =====
    try:
        # I²C devices - DO NOT SCAN DIRECTLY; use sensor_controller status
        i2c_devices = []
        try:
            # Get device status from sensor_controller instead of direct I2C access
            # This respects the locks and doesn't interfere with calibration
            from app.sensor_controller import get_sensor_status
            status = get_sensor_status()
            if status and status.get("online"):
                i2c_devices = [
                    {"address": "0x66", "name": "RTD", "online": True},
                    {"address": "0x63", "name": "pH", "online": True},
                    {"address": "0x64", "name": "EC", "online": True}
                ]
            else:
                i2c_devices = [
                    {"address": "0x66", "name": "RTD", "online": False},
                    {"address": "0x63", "name": "pH", "online": False},
                    {"address": "0x64", "name": "EC", "online": False}
                ]
        except Exception as e:
            i2c_devices = [{"error": f"Could not get sensor status: {str(e)}"}]
        
        # Relay GPIO pins
        relay_pins = {}
        try:
            from app.relays_core import RELAY_PINS
            relay_pins = RELAY_PINS
        except Exception:
            pass
        
        # Sensor power pin
        sensor_power_pin = os.environ.get("RDWC_SENSOR_POWER_PIN", "not configured")
        
        info["environment_info"] = {
            "i2c_devices": i2c_devices,
            "relay_pins": relay_pins,
            "sensor_power_pin": sensor_power_pin,
            "i2c_bus": "/dev/i2c-1"
        }
    except Exception as e:
        info["environment_info"] = {"error": str(e)}

    # ===== ELECTRICAL INFO (optional, computed; single source from settings + relay states) =====
    try:
        electrical = {
            "voltage_v": None,
            "total_watts": None,
            "total_amps": None,
            "breakdown": [],
            "configured_watts": {},
        }

        # Read namespaced settings for voltage and per-relay wattage
        try:
            from app.settings import get_all_settings
            s = get_all_settings()
        except Exception:
            s = {}

        # Voltage (optional)
        try:
            v_str = s.get("electrical.voltage_v")
            voltage_v = float(v_str) if v_str else None
        except Exception:
            voltage_v = None

        electrical["voltage_v"] = voltage_v

        # Per-relay wattage mapping: keys like electrical.watts.main_pump = 35
        watts_map = {}
        for k, v in s.items():
            if k.startswith("electrical.watts."):
                name = k.split(".", 2)[2]
                try:
                    watts_map[name] = float(v)
                except Exception:
                    continue
        electrical["configured_watts"] = watts_map

        # Current relay states (read-only)
        try:
            from app.relays_core import get_relay_status
            relay_status = get_relay_status()  # {name: {state: bool, ...}}
        except Exception:
            relay_status = {}

        # Compute totals from active relays that have configured wattage
        total_watts = 0.0
        breakdown = []
        for name, st in (relay_status or {}).items():
            is_on = bool(st.get("state", False))
            if not is_on:
                continue
            w = watts_map.get(name)
            if w is None:
                # Skip relays without configured wattage
                continue
            total_watts += w
            breakdown.append({
                "relay": name,
                "watts": w
            })

        electrical["breakdown"] = breakdown
        electrical["total_watts"] = round(total_watts, 1) if breakdown else None
        electrical["total_amps"] = (round(total_watts / voltage_v, 2) if (voltage_v and total_watts and total_watts > 0) else None)
        electrical["computed_from_config"] = bool(breakdown)

        info["electrical_info"] = electrical
    except Exception as e:
        info["electrical_info"] = {"error": str(e)}
    
    # ===== DATABASE INFO =====
    try:
        import sqlite3
        db_path = Path(DB_PATH)
        
        if db_path.exists():
            db_size_mb = round(db_path.stat().st_size / 1024 / 1024, 2)

            # Disk free/health
            disk_free_gb = None
            disk_free_percent = None
            smart_health = None
            try:
                disk_usage = psutil.disk_usage('/')
                disk_free_gb = round(disk_usage.free / 1024 / 1024 / 1024, 2)
                disk_free_percent = round(100 - disk_usage.percent, 1)
            except Exception:
                pass

            # SMART overall health (best-effort; skips if smartctl missing)
            try:
                candidates = ["/dev/mmcblk0", "/dev/sda", "/dev/sdb"]
                for dev in candidates:
                    if Path(dev).exists():
                        res = subprocess.run(["smartctl", "-H", dev], capture_output=True, text=True, timeout=3)
                        if res.returncode == 0 and "overall-health" in res.stdout:
                            for ln in res.stdout.splitlines():
                                if "overall-health" in ln.lower():
                                    smart_health = ln.split(":")[-1].strip()
                                    break
                        if smart_health:
                            break
            except Exception:
                smart_health = None
            
            # Get record counts
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            tables = {}
            for table in ["readings", "ph_dose_log", "ec_dose_log", "dose_events", "nutrient_schedule", "system_state"]:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    tables[table] = count
                except Exception:
                    tables[table] = "N/A"
            
            # Get oldest and newest reading timestamps
            try:
                cursor.execute("SELECT MIN(ts), MAX(ts) FROM readings")
                min_ts, max_ts = cursor.fetchone()
                oldest = datetime.fromtimestamp(min_ts).isoformat() if min_ts else "N/A"
                newest = datetime.fromtimestamp(max_ts).isoformat() if max_ts else "N/A"
            except Exception:
                oldest = newest = "N/A"
            
            conn.close()
            
            info["database_info"] = {
                "path": str(db_path),
                "size_mb": db_size_mb,
                "tables": tables,
                "oldest_reading": oldest,
                "newest_reading": newest,
                "disk_free_gb": disk_free_gb,
                "disk_free_percent": disk_free_percent,
                "smart_health": smart_health
            }
        else:
            info["database_info"] = {"error": "Database file not found"}
    except Exception as e:
        info["database_info"] = {"error": str(e)}
    
    # ===== NETWORK INFO =====
    try:
        hostname = socket.gethostname()
        
        # Get all IP addresses
        ip_addresses = []
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:  # IPv4
                    ip_addresses.append({
                        "interface": interface,
                        "address": addr.address,
                        "netmask": addr.netmask
                    })

        # Interface stats (rx/tx/errors)
        iface_stats = {}
        try:
            stats = psutil.net_io_counters(pernic=True)
            for name, st in stats.items():
                iface_stats[name] = {
                    "bytes_sent": st.bytes_sent,
                    "bytes_recv": st.bytes_recv,
                    "errin": st.errin,
                    "errout": st.errout,
                    "dropin": st.dropin,
                    "dropout": st.dropout
                }
        except Exception:
            iface_stats = {}

        # WLAN signal/quality (measured via iwconfig/iwgetid when available)
        wifi = None
        try:
            # Get SSID
            ssid = None
            try:
                ssid_res = subprocess.run(["iwgetid", "-r"], capture_output=True, text=True, timeout=2)
                if ssid_res.returncode == 0:
                    ssid = ssid_res.stdout.strip() or None
            except Exception:
                ssid = None

            # Parse iwconfig for signal/bitrate
            iw_res = subprocess.run(["iwconfig"], capture_output=True, text=True, timeout=2)
            if iw_res.returncode == 0:
                lines = iw_res.stdout.splitlines()
                cur_if = None
                signal_dbm = None
                bitrate = None
                quality = None
                for ln in lines:
                    if not ln.strip():
                        continue
                    if not ln.startswith(' '):
                        cur_if = ln.split()[0]
                    if 'Signal level=' in ln:
                        try:
                            part = ln.split('Signal level=')[1].split()[0]
                            if 'dBm' in part:
                                part = part.replace('dBm','')
                            signal_dbm = float(part)
                        except Exception:
                            signal_dbm = None
                    if 'Bit Rate=' in ln:
                        try:
                            bitrate = ln.split('Bit Rate=')[1].split()[0]
                        except Exception:
                            bitrate = None
                    if 'Link Quality=' in ln:
                        try:
                            qpart = ln.split('Link Quality=')[1].split()[0]  # e.g., 70/70
                            if '/' in qpart:
                                num, den = qpart.split('/')
                                quality = round((float(num)/float(den))*100,1)
                        except Exception:
                            quality = None
                    # Stop once we have a wifi interface with signal
                    if signal_dbm is not None and cur_if:
                        wifi = {
                            "interface": cur_if,
                            "ssid": ssid,
                            "signal_dbm": signal_dbm,
                            "bitrate": bitrate,
                            "quality_pct": quality
                        }
                        break
        except Exception:
            wifi = None
        
        info["network_info"] = {
            "hostname": hostname,
            "ip_addresses": ip_addresses,
            "wifi": wifi,
            "iface_stats": iface_stats
        }
    except Exception as e:
        info["network_info"] = {"error": str(e)}
    
    # ===== PROCESS INFO =====
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent', 'cpu_percent', 'create_time']):
            try:
                pinfo = proc.info
                # Only include RDWC-related processes
                if 'rdwc' in pinfo['name'].lower() or 'uvicorn' in pinfo['name'].lower() or 'python' in pinfo['name'].lower():
                    # Runtime in seconds
                    runtime = None
                    try:
                        if pinfo.get('create_time'):
                            runtime = int(time.time() - pinfo['create_time'])
                    except Exception:
                        runtime = None
                    processes.append({
                        "pid": pinfo['pid'],
                        "name": pinfo['name'],
                        "user": pinfo['username'],
                        "memory_percent": round(pinfo['memory_percent'], 2) if pinfo['memory_percent'] else 0,
                        "cpu_percent": round(pinfo['cpu_percent'], 1) if pinfo.get('cpu_percent') is not None else 0,
                        "runtime_seconds": runtime
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        info["process_info"] = {
            "rdwc_processes": processes[:10]  # Limit to 10 most relevant
        }
    except Exception as e:
        info["process_info"] = {"error": str(e)}
    
    return info

@app.get("/health/db")
def health_db():
    """Database health check with freshness validation"""
    import sqlite3
    from datetime import datetime, timezone
    from pathlib import Path
    
    try:
        db_path = Path("data/rdwc.db")
        if not db_path.exists():
            return JSONResponse(
                status_code=503,
                content={
                    "ok": False,
                    "error": "Database file not found",
                    "age_seconds": None,
                    "recent_rows_5min": 0,
                    "latest_ts_iso": None
                }
            )
        
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            # Get latest timestamp (stored as Unix timestamp integer)
            cursor.execute("SELECT MAX(ts) as max_ts FROM readings")
            row = cursor.fetchone()
            max_ts = row[0] if row else None
            
            # Get recent row count (last 5 minutes = 300 seconds)
            now_unix = int(time.time())
            cursor.execute("""
                SELECT COUNT(*) FROM readings 
                WHERE ts >= ?
            """, (now_unix - 300,))
            recent_rows = cursor.fetchone()[0]
            
            # Calculate age and convert to ISO
            age_seconds = None
            latest_ts_iso = None
            if max_ts:
                try:
                    # ts is Unix timestamp integer
                    now_unix = int(time.time())
                    age_seconds = now_unix - max_ts
                    # Convert to ISO for display
                    latest_ts_iso = datetime.fromtimestamp(max_ts, tz=timezone.utc).isoformat()
                except Exception:
                    # Timestamp parsing failed, age_seconds will remain None
                    pass
            
            # Health check: data should be < 3 minutes old
            ok = age_seconds is not None and age_seconds < 180
            
            response = {
                "ok": ok,
                "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
                "recent_rows_5min": recent_rows,
                "latest_ts_iso": latest_ts_iso
            }
            
            if ok:
                return response
            else:
                return JSONResponse(status_code=503, content=response)
                
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": str(e),
                "age_seconds": None,
                "recent_rows_5min": 0,
                "latest_ts_iso": None
            }
        )

@app.get("/api/sensors/status")
def api_sensors_status():
    """
    Sensor poller status endpoint - reports on headless background polling.
    
    Returns:
        running: bool - is poller loop active
        last_sample_ts: float - Unix timestamp of last sensor sample
        last_heartbeat_ts: float - Unix timestamp of last heartbeat update
        interval_sec: int - polling interval
        i2c_device: str - I2C bus device path
        poll_count: int - total polls since start
        lock_file: str - PID lock file path
        lock_exists: bool - does lock file exist
        lock_pid: int - PID from lock file (if exists)
    """
    from app.sensor_poller import get_status
    return get_status()

@app.get("/api/health")
def api_health():
    """
    Application health summary endpoint.
    
    Returns:
        ok: bool - overall health status
        app_version: str - ASSET_VERSION token
        git_commit: str - short git SHA (if available)
        uptime_seconds: float - time since app start
        sensor_poller: dict - sensor poller status
        database: dict - database connectivity check
    """
    import subprocess
    from pathlib import Path
    
    # Get git commit
    git_commit = None
    try:
        repo_root = Path(__file__).parent.parent
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except Exception:
        pass
    
    # Check database
    db_ok = False
    try:
        import sqlite3
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("SELECT 1").fetchone()
            db_ok = True
    except Exception:
        pass
    
    # Get sensor poller status
    from app.sensor_poller import get_status
    poller_status = get_status()
    
    uptime = time.time() - START_TS
    
    return {
        "ok": db_ok,
        "app_version": ASSET_VERSION,
        "git_commit": git_commit,
        "uptime_seconds": uptime,
        "sensor_poller": poller_status,
        "database": {
            "ok": db_ok,
            "path": DB_PATH
        }
    }

@app.get("/api/version")
def asset_version():
    """Expose asset version and build commit marker for cache-busting and deployment verification."""
    build_commit = None
    idx = os.path.join(os.path.dirname(__file__), "static", "index.html")
    try:
        with open(idx, 'r', encoding='utf-8', errors='ignore') as f:
            head = f.read(600)
        marker_prefix = "BUILD_COMMIT:";
        for line in head.splitlines():
            if marker_prefix in line:
                parts = line.strip().split(marker_prefix)
                if len(parts) > 1:
                    build_commit = parts[1].split('-->')[0].strip()
                break
    except Exception:
        pass
    return {"version": ASSET_VERSION, "build_commit": build_commit, "ts": int(time.time())}

@app.get("/api/relays/status")
def api_relays_status():
    """Wrapper endpoint for UI/verify tools: returns mode, estop, and relay map.
    Shape: {"mode":"manual|auto","estop":bool,"relays":{ name: {pin_bcm, active_low, is_on, label} }}
    """
    from app.relays_core import get_relay_status, RELAY_PINS, get_estop_status, get_last_restore_event, ACTIVE_HIGH
    from app.unified_mode import get_mode as get_system_mode
    status = get_relay_status()
    mode = get_system_mode() or 'manual'
    estop = bool(get_estop_status())
    # Labels mapping (keep backend keys: lights/chiller_power)
    LABELS = {
        'dosing_ph_up': 'pH Up Pump',
        'dosing_grow': 'Grow Pump',
        'dosing_micro': 'Micro Pump',
        'dosing_bloom': 'Bloom Pump',
        'main_pump': 'Main Pump',
        'chiller_pump': 'Chiller Pump',
        'chiller_power': 'Water Chiller (AC)',
        'lights': 'Grow Lights (AC)',
    }
    # Prefer actual pin levels translated via NO/NC wiring; fallback to guard shadow/state
    try:
        from app.relay_guard import get_pin_levels, NC_RELAYS, get_shadow_state
        _levels = get_pin_levels() or {}
        _shadow = get_shadow_state() or {}
    except Exception:
        _levels = {}
        _shadow = {}
    rel = {}
    for name, pin in RELAY_PINS.items():
        info = status.get(name, {})
        level = _levels.get(name)
        if level is not None:
            is_nc = name in (_locals := locals()).get('NC_RELAYS', set()) if False else False  # safety default
        try:
            from app.relay_guard import NC_RELAYS as _NC
            is_nc = name in _NC
        except Exception:
            is_nc = False
        if level in ("HIGH","LOW"):
            is_on = (level == "HIGH") if is_nc else (level == "LOW")
        else:
            is_on = bool(_shadow.get(name, info.get("state", False)))
        rel[name] = {
            "pin_bcm": pin,
            "active_low": (not bool(ACTIVE_HIGH.get(name, False))),
            "is_on": is_on,
            "label": LABELS.get(name, name)
        }
    restore = get_last_restore_event() if mode == 'auto' else {"restored": False}
    return {"mode": mode, "estop": estop, "restored": bool(restore.get("restored", False)), "relays": rel}

@app.get("/api/relays/events")
def api_relay_events(name: str = Query("main_pump", description="Relay name (e.g., main_pump, chiller_pump)"), 
                     last: int = Query(50, description="Number of recent events")):
    """Get recent relay state change events for timeline/analytics."""
    try:
        events = get_relay_event_log(name, last=last)
        return events
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/sensors/power_cycle")
def api_sensors_power_cycle(off_ms: int = 2000, post_wait_ms: int = 4000, validate: int = 1):
    """Power-cycle the EZO sensor power rail via optional relay 'sensor_power'.

    Requirements:
      - Set env RDWC_SENSOR_POWER_PIN=<BCM pin>
      - (Optional) RDWC_SENSOR_POWER_ACTIVE_LOW=1 (default) or 0 if active-high.

    Steps:
      1. Acquire calibration lock to quiesce I2C activity.
      2. Turn sensor_power relay OFF (de-energize rail) for off_ms.
      3. Turn sensor_power relay ON (re-energize).
      4. Wait post_wait_ms for boards to boot.
      5. (Optional validate) attempt identify/read to confirm recovery.

    Returns JSON: {ok, off_ms, post_wait_ms, validate_attempts, ids?, sample?}
    """
    from app.relays_core import RELAY_PINS, set as relay_set
    import time as _time
    import fcntl
    if "sensor_power" not in RELAY_PINS:
        return JSONResponse(status_code=400, content={"ok": False, "error": "sensor_power_pin_not_configured"})
    lock_path = "/tmp/rdwc_calib.lock"
    lock_fd = None
    try:
        # Exclusive lock (block sensor poll loop & calibration operations)
        lock_fd = open(lock_path, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        # Small grace period for any in-flight read
        _time.sleep(0.6)
        off_ms = max(500, min(15000, int(off_ms)))
        post_wait_ms = max(1000, min(15000, int(post_wait_ms)))
        # Power OFF
        relay_set("sensor_power", False, reason="sensor_power_cycle_off", force=True)
        _time.sleep(off_ms / 1000.0)
        # Power ON
        relay_set("sensor_power", True, reason="sensor_power_cycle_on", force=True)
        _time.sleep(post_wait_ms / 1000.0)
        out = {"ok": True, "off_ms": off_ms, "post_wait_ms": post_wait_ms}
        if int(validate):
            try:
                # Route validation through sensor_controller (single I2C manager)
                from app.sensor_controller import validate_sensor_presence
                validation_result = validate_sensor_presence()
                out.update(validation_result)
            except Exception as ex:
                out["validate_error"] = str(ex)
        return out
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass

@app.post("/api/relay/{key}/toggle")
def api_relay_toggle(key: str):
    """Toggle a relay by key, honoring system mode and protections via relays_core.
    In manual mode, 'force' is enabled; in auto, protections apply and UI should be disabled.
    """
    from app.relays_core import get_relay_status, RELAY_PINS
    if key not in RELAY_PINS:
        return JSONResponse(status_code=400, content={"ok": False, "error": f"invalid_relay:{key}"})
    cur = get_relay_status().get(key, {})
    desired = not bool(cur.get("state", False))
    # Reuse existing /relay/set POST path for centralized logic and tracing
    try:
        return relay_set_new({"name": key, "on": desired})  # type: ignore[arg-type]
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@app.post("/api/relays/mode")
def api_relays_mode(body: dict = Body(...)):
    """Set system mode using existing system_mode endpoint."""
    mode = (body.get("mode") or "").lower()
    if mode not in ("manual", "auto"):
        return JSONResponse(status_code=422, content={"ok": False, "error": "invalid_mode"})
    # Prefer new fast path endpoint that uses settings upsert (avoids potential DB lock in legacy path).
    try:
        fast_res = api_system_mode_fast({"mode": mode})  # type: ignore[arg-type]
        # If fast path returns a JSONResponse with error status, or a dict without success, fall back.
        try:
            from fastapi.responses import JSONResponse as _JR  # local import to avoid top-level coupling
            if isinstance(fast_res, _JR):
                if getattr(fast_res, "status_code", 200) != 200:
                    logger.warning(f"Fast system_mode set returned status {getattr(fast_res, 'status_code', None)}; falling back to legacy")
                    return set_system_mode_api({"mode": mode})  # type: ignore[arg-type]
                return fast_res
        except Exception:
            # If JSONResponse import/type-check fails, continue with dict checks
            pass
        if isinstance(fast_res, dict):
            if fast_res.get("success"):
                return fast_res
            # If fast path indicates failure, fall back
            logger.warning(f"Fast system_mode set indicated failure: {fast_res}")
            return set_system_mode_api({"mode": mode})  # type: ignore[arg-type]
        # Unknown type, fall back conservatively
        logger.warning("Fast system_mode set returned unknown type; falling back to legacy")
        return set_system_mode_api({"mode": mode})  # type: ignore[arg-type]
    except Exception as e:  # Fallback to legacy if fast path fails
        logger.warning(f"Fast system_mode set failed, falling back: {e}")
        return set_system_mode_api({"mode": mode})  # type: ignore[arg-type]

@app.post("/api/relays/estop/toggle")
def api_relays_estop_toggle():
    """Toggle E-STOP latch using existing /api/estop endpoints."""
    from app.relays_core import get_estop_status
    active = bool(get_estop_status())
    return api_estop_set({"active": (not active)})

@app.get("/api/relays/guard/status")
def api_relays_guard_status():
    """
    Relay guard status endpoint for monitoring and soak test verification.
    Returns:
      shadow_state: {relay_name: bool (logical ON/OFF)}
      pin_levels: {relay_name: "HIGH"|"LOW" (actual GPIO level)}
      anomalies: {count: int, anomalies: [...]}
    """
    try:
        from app.relay_guard import get_shadow_state, get_pin_levels, get_anomalies
        
        shadow = get_shadow_state()
        levels = get_pin_levels()
        anomalies = get_anomalies()
        
        return {
            "ok": True,
            "shadow_state": shadow,
            "pin_levels": levels,
            "anomalies": anomalies,
            "active_low_note": "LOW=energized/ON, HIGH=safe/OFF"
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "ok": False,
            "error": str(e)
        })

@app.get("/api/relays/guard/recent")
def api_relays_guard_recent(limit: int = 50):
    """Return recent RelayGuard events (ring buffer)."""
    try:
        from app.relay_guard import get_recent_guard_events
        return get_recent_guard_events(limit)
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

# === Intelligent Chiller Control (Hailea HS-52A) ===

@app.get("/api/temperature/status")
def api_chiller_status():
    """Get current chiller state, temperature, and automation status."""
    import logging
    log = logging.getLogger(__name__)
    
    try:
        log.debug("api_chiller_status: Starting")
        
        try:
            log.debug("api_chiller_status: Importing temperature_control")
            from app.temperature_control import get_temperature_state, get_current_water_temp
        except Exception as e:
            log.error(f"api_chiller_status: Import failed: {e}", exc_info=True)
            raise
        
        try:
            log.debug("api_chiller_status: Calling get_temperature_state()")
            state = get_temperature_state()
            log.debug(f"api_chiller_status: get_temperature_state returned: {type(state)}")
        except Exception as e:
            log.error(f"api_chiller_status: get_temperature_state failed: {e}", exc_info=True)
            raise
        
        try:
            log.debug("api_chiller_status: Calling get_current_water_temp()")
            state['current_temp'] = get_current_water_temp()
            log.debug(f"api_chiller_status: get_current_water_temp returned: {state['current_temp']}")
        except Exception as e:
            log.error(f"api_chiller_status: get_current_water_temp failed: {e}", exc_info=True)
            raise
        
        log.debug("api_chiller_status: Success")
        return state
        
    except Exception as e:
        log.exception("/api/temperature/status failed")
        error_response = {
            "ok": False,
            "error": str(e),
            "current_temp": None,
            "is_running": False,
            "auto_enabled": False
        }
        log.debug(f"api_chiller_status: Returning error response: {error_response}")
        return JSONResponse(status_code=200, content=error_response)

@app.post("/api/temperature/auto/enable")
def api_chiller_auto_enable():
    """Enable automatic chiller control based on temperature."""
    from app.temperature_control import start_auto_control, get_temperature_state
    start_auto_control()
    status = get_temperature_state()
    return {"ok": True, "auto_enabled": status.get('auto_enabled', False)}

@app.post("/api/temperature/auto/disable")
def api_chiller_auto_disable():
    """Disable automatic chiller control."""
    from app.temperature_control import stop_auto_control, get_temperature_state
    stop_auto_control()
    status = get_temperature_state()
    return {"ok": True, "auto_enabled": status.get('auto_enabled', False)}

@app.post("/api/temperature/force")
def api_chiller_force(req: dict):
    """
    Force chiller ON or OFF for specified duration (emergency/maintenance override).
    Body: {"on": true/false, "duration_minutes": 60} (duration optional)
    """
    from app.temperature_control import force_temperature_state
    desired_on = bool(req.get("on", False))
    duration = req.get("duration_minutes")  # None = indefinite
    result = force_temperature_state(desired_on, duration)
    return result

@app.post("/api/temperature/settings")
def api_chiller_settings_update(req: dict):
    """
    Update chiller settings (target temp, hysteresis, stage, etc.).
    Body: {"target_temp": 19.0, "hysteresis": 0.5, "stage": "veg"}
    """
    from app.settings import upsert_settings, validate_partial
    
    # Map incoming keys to settings keys
    settings_map = {
        'target_temp': 'chiller.target_temp',
        'hysteresis': 'chiller.hysteresis',
        'stage': 'chiller.stage',
        'min_on_seconds': 'chiller.min_on_seconds',
        'min_off_seconds': 'chiller.min_off_seconds',
        'control_interval_s': 'chiller.control_interval_s',
    }
    
    updates = {}
    for key, setting_key in settings_map.items():
        if key in req:
            updates[setting_key] = str(req[key])

    # Keep legacy target in sync for older UI components
    if 'target_temp' in req:
        updates['targets.temp_target_c'] = str(req['target_temp'])
    
    # Validate
    ok, error = validate_partial(updates)
    if not ok:
        return JSONResponse(status_code=422, content={"ok": False, "error": error})
    
    # Apply
    upsert_settings(updates)
    return {"ok": True, "updated": updates}

@app.get("/api/controllers/status")
def api_controllers_status():
    """Consolidated atomic snapshot of all controller states, modes, guards, and holding reasons.
    Used by UI for unified status display and mode synchronization.
    
    NOTE: Mode fields are deprecated. Use auto_enabled instead (from unified auto-enable system).
    
    Returns: {
        system_mode: str (deprecated),
        global_auto: bool (NEW),
        maintenance_override: bool,
        estop: bool,
        controllers: {
            ph: {auto_enabled, will_automate, holding_reason, guards, learned_ml_per_pH, ...},
            ec: {auto_enabled, will_automate, holding_reason, guards, learned_ml_per_mScm, ...},
            chiller: {auto_enabled, will_automate, current_temp, state, ...},
            lights: {is_on, schedule_active, ...},
            circulation: {pumps: {...}}
        }
    }
    """
    import time
    from app.auto_control import get_auto_status, should_automate, is_controller_auto_enabled
    from app.settings import get_setting_key
    from app.relays_core import get_estop_status, get_relay_status
    
    # NEW: Use unified auto-enable system
    auto_status = get_auto_status()
    global_auto = auto_status["global_auto"]
    
    try:
        maint_override = (get_setting_key("safety.maintenance_override", "false") or "false").lower() == "true"
    except Exception:
        maint_override = False
    estop = get_estop_status()
    
    # Build controller details
    controllers = {}
    
    # pH Controller
    try:
        from app.ph_control import ph_status
        ph_data = ph_status()
        will_automate = should_automate("ph")
        controllers["ph"] = {
            "mode": "auto" if will_automate else "manual",  # For backward compatibility
            "auto_enabled": is_controller_auto_enabled("ph"),  # Use unified auto-enable system
            "will_automate": will_automate,
            "holding_reason": ph_data.get("auto", {}).get("holding_reason"),
            "learned_ml_per_pH": ph_data.get("auto", {}).get("learned_ml_per_pH"),
            "guards": ph_data.get("guards", {}),
            "ph": ph_data.get("ph"),
            "ts": ph_data.get("ts"),
            "targets": ph_data.get("targets", {}),
            "remaining_cooldown_s": ph_data.get("remaining_cooldown_s", 0),
        }
    except Exception as e:
        logger.error(f"Failed to get pH status: {e}")
        controllers["ph"] = {"auto_enabled": False, "will_automate": False, "error": str(e)}
    
    # EC Controller
    try:
        from app.ec_control import get_ec_status
        ec_data = get_ec_status()
        will_automate = should_automate("ec")
        controllers["ec"] = {
            "mode": "auto" if will_automate else "manual",  # For backward compatibility
            "auto_enabled": is_controller_auto_enabled("ec"),  # Use unified auto-enable system
            "will_automate": will_automate,
            "holding_reason": ec_data.get("auto", {}).get("holding_reason"),
            "learned_ml_per_mScm": ec_data.get("auto", {}).get("learned_ml_per_mScm"),
            "guards": ec_data.get("guards", {}),
            "ec_ms_cm": ec_data.get("ec_ms_cm"),
            "ec_ts": ec_data.get("ec_ts"),
            "targets": ec_data.get("targets", {}),
            "today_ml": ec_data.get("today_ml", 0),
        }
    except Exception as e:
        logger.error(f"Failed to get EC status: {e}")
        controllers["ec"] = {"auto_enabled": False, "will_automate": False, "error": str(e)}
    
    # Chiller Controller
    try:
        from app.temperature_control import get_temperature_state, get_current_water_temp
        chiller_state = get_temperature_state()
        will_automate = should_automate("chiller")
        controllers["chiller"] = {
            "mode": "auto" if will_automate else "manual",  # For backward compatibility
            "auto_enabled": is_controller_auto_enabled("chiller"),  # Use unified auto-enable system
            "will_automate": will_automate,
            "current_temp": get_current_water_temp(),
            "target_temp": float(get_setting_key("chiller.target_temp", "19.0") or "19.0"),
            # Updated default hysteresis per brief (0.7°C)
            "hysteresis": float(get_setting_key("chiller.hysteresis", "0.7") or "0.7"),
            "is_running": chiller_state.get("is_running", False),
            "in_cooldown": chiller_state.get("in_cooldown", False),
        }
    except Exception as e:
        logger.error(f"Failed to get chiller status: {e}")
        controllers["chiller"] = {"auto_enabled": False, "error": str(e)}
    
    # Lights Controller
    try:
        relay_status = get_relay_status()
        # get_relay_status() returns key 'state' for ON/OFF
        lights_on = relay_status.get("lights", {}).get("state", False)
        # Lights use unified auto-enable system (global + lights controller auto)
        will_automate = should_automate("lights")
        controllers["lights"] = {
            "mode": "auto" if will_automate else "manual",  # For backward compatibility
            "auto_enabled": is_controller_auto_enabled("lights"),
            "will_automate": will_automate,
            "is_on": lights_on,
            "schedule_active": will_automate,
        }
    except Exception as e:
        logger.error(f"Failed to get lights status: {e}")
        controllers["lights"] = {"mode": "manual", "auto_enabled": False, "will_automate": False, "is_on": False, "error": str(e)}
    
    # Circulation Controller (pumps)
    try:
        relay_status = get_relay_status()
        will_automate = should_automate("circulation")
        controllers["circulation"] = {
            "mode": "auto" if will_automate else "manual",  # For backward compatibility
            "auto_enabled": is_controller_auto_enabled("circulation"),
            "will_automate": will_automate,
            # get_relay_status() uses 'state' for ON/OFF
            "main_pump": relay_status.get("main_pump", {}).get("state", False),
            "chiller_pump": relay_status.get("chiller_pump", {}).get("state", False),
        }
    except Exception as e:
        logger.error(f"Failed to get circulation status: {e}")
        controllers["circulation"] = {"mode": "manual", "auto_enabled": False, "will_automate": False, "error": str(e)}
    
    return {
        "system_mode": "auto" if global_auto else "manual",  # Deprecated, use global_auto
        "global_auto": global_auto,
        "maintenance_override": maint_override,
        "estop": estop,
        "controllers": controllers,
        "timestamp": int(time.time()),
    }

@app.get("/api/temperature/events")
def api_chiller_events(limit: int = Query(200, ge=1, le=1000)):
    """Return recent chiller state transition events (newest first).
    Each event: {ts_utc:int, prev_state:str, new_state:str, reason:str|null}
    """
    try:
        from app.temperature_control import get_temperature_events
        events = get_temperature_events(limit)
        return {"events": events, "count": len(events)}
    except Exception as e:
        logger.error(f"/api/temperature/events failed: {e}")
        return JSONResponse(status_code=500, content={"error": "events_failed"})

# --- Unified dosing endpoints ------------------------------------------------
@app.post("/api/dose/grow")
def dose_grow(body: dict = Body(...)):
    """DEPRECATED: Manual Grow nutrient dose (time-based). Use /api/ec/dose instead."""
    return _dose_pump("grow", body)

@app.post("/api/dose/micro")
def dose_micro(body: dict = Body(...)):
    """DEPRECATED: Manual Micro nutrient dose (time-based). Use /api/ec/dose instead."""
    return _dose_pump("micro", body)

@app.post("/api/dose/bloom")
def dose_bloom(body: dict = Body(...)):
    """DEPRECATED: Manual Bloom nutrient dose (time-based). Use /api/ec/dose instead."""
    return _dose_pump("bloom", body)

@app.post("/api/dose/ph_up")
def dose_ph_up(body: dict = Body(...)):
    """Manual pH Up dose with centralized safety caps."""
    return _dose_pump("ph_up", body)

def _dose_pump(pump: str, body: dict) -> dict:
    """Centralized dose handler for all pumps."""
    from app.dosing import (
        check_dosing_guards, log_dose_event, actuate_pump, _get_latest_readings
    )
    
    # Validate payload
    seconds = body.get("seconds")
    reason = body.get("reason", "manual")
    actor = body.get("actor", "ui")
    
    if seconds is None:
        return JSONResponse(status_code=400, content={
            "ok": False, "error": "Missing 'seconds' field"
        })
    
    try:
        seconds = float(seconds)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={
            "ok": False, "error": "Invalid 'seconds' value"
        })
    
    if seconds <= 0:
        return JSONResponse(status_code=400, content={
            "ok": False, "error": "seconds must be > 0"
        })
    
    # Get KPIs before
    readings_before = _get_latest_readings()
    kpis_before = {
        "ph": readings_before.get("ph"),
        "ec_ms_cm": readings_before.get("ec_ms_cm"),
        "temp_c": readings_before.get("temp_c")
    }
    
    # Check guards
    ok, blocked_by, caps_info = check_dosing_guards(pump, seconds)
    
    if not ok:
        # Log blocked event
        log_dose_event(
            pump=pump,
            seconds=seconds,
            reason=reason,
            actor=actor,
            ph_before=kpis_before.get("ph"),
            ec_before=kpis_before.get("ec_ms_cm"),
            temp_c=kpis_before.get("temp_c"),
            blocked_by=blocked_by
        )
        
        # Human-readable messages
        messages = {
            "press_cap": f"Press limit exceeded (max: {caps_info['max_press']}s)",
            "daily_cap": f"Daily cap reached (max: {caps_info['daily_cap']}s per 24h)",
            "min_off": f"Min off window not met (wait: {caps_info['min_off']}s)",
            "stale": "Sensor readings are stale (>60s old)",
            "estop": "Emergency stop is active",
            "safeoff": "System in safe-off mode",
            "mix_lock": "Another pump is currently active",
            "ph_guard": "pH too high for pH Up dosing",
            "ec_guard": "EC too high for nutrient dosing"
        }
        
        return JSONResponse(status_code=409, content={
            "ok": False,
            "blocked_by": blocked_by,
            "message": messages.get(blocked_by, f"Blocked by {blocked_by}"),
            "caps": caps_info
        })
    
    # Actuate pump
    success, error_msg = actuate_pump(pump, seconds)
    
    if not success:
        # Log error
        log_dose_event(
            pump=pump,
            seconds=seconds,
            reason=reason,
            actor=actor,
            ph_before=kpis_before.get("ph"),
            ec_before=kpis_before.get("ec_ms_cm"),
            temp_c=kpis_before.get("temp_c"),
            blocked_by=f"error:{error_msg}"
        )
        return JSONResponse(status_code=500, content={
            "ok": False,
            "error": f"Actuation failed: {error_msg}"
        })
    
    # Wait for readings to settle (5s)
    time.sleep(5)
    
    # Get KPIs after
    readings_after = _get_latest_readings()
    kpis_after = {
        "ph": readings_after.get("ph"),
        "ec_ms_cm": readings_after.get("ec_ms_cm"),
        "temp_c": readings_after.get("temp_c")
    }
    
    # Log successful event
    log_dose_event(
        pump=pump,
        seconds=seconds,
        reason=reason,
        actor=actor,
        ph_before=kpis_before.get("ph"),
        ph_after=kpis_after.get("ph"),
        ec_before=kpis_before.get("ec_ms_cm"),
        ec_after=kpis_after.get("ec_ms_cm"),
        temp_c=kpis_after.get("temp_c"),
        blocked_by=None
    )
    
    # Build guards status for response
    guards_status = {
        "ec_guard": False,
        "ph_guard": False,
        "stale": False
    }
    
    return {
        "ok": True,
        "pump": pump,
        "seconds": seconds,
        "ts": int(time.time()),
        "caps": caps_info,
        "guards": guards_status,
        "kpis_before": kpis_before,
        "kpis_after": kpis_after,
        "note": "executed"
    }

@app.get("/api/dose/recent")
def dose_recent(limit: int = Query(50), hours: Optional[int] = Query(None)):
    """Get recent dose events, optionally filtered by hours."""
    from app.dosing import get_recent_dose_events, get_doses_since
    
    if hours is not None:
        ts_start = int(time.time()) - (hours * 3600)
        events = get_doses_since(ts_start)
    else:
        events = get_recent_dose_events(limit)
    
    return {"events": events, "count": len(events)}

@app.get("/")
def ui():
    path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    build_commit = None
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            head = f.read(600)
        marker_prefix = "BUILD_COMMIT:";
        for line in head.splitlines():
            if marker_prefix in line:
                parts = line.strip().split(marker_prefix)
                if len(parts) > 1:
                    build_commit = parts[1].split('-->')[0].strip()
                break
    except Exception:
        pass
    headers = {"Cache-Control":"no-store, must-revalidate"}
    if build_commit:
        headers["X-Build-Commit"] = build_commit
    return FileResponse(path, media_type="text/html", headers=headers)

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
    to: Optional[str] = Query(None),
    gran: Optional[int] = Query(300),      # granularity in seconds (default 5min)
    max_param: Optional[int] = Query(2000, alias="max")  # max points per series
):
    """
    Trends API endpoint with server-side bucketing and capping.
    Returns: { "series": { "ph": [{ts, value}], "ec": [...], "temp": [...] } }
    Timestamps are Unix epoch seconds (not ISO strings) for Chart.js compatibility.
    
    ?gran=<sec> - Time bucket size in seconds (avg values per bucket)
    ?max=<n>    - Maximum points per series (downsample if exceeded)
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
        except Exception as e:
            print(f"[Trends API] Failed to parse timestamp '{s}': {e}")
            return None
    
    # Parse and validate parameters
    from_ts = parse_iso(from_param)
    to_ts = parse_iso(to)
    
    # Default to last 7 days if no range specified
    if not from_ts:
        from_ts = int(time.time()) - (7 * 24 * 3600)
    if not to_ts:
        to_ts = int(time.time())
    
    # Validate gran and max_param
    gran_val = max(1, int(gran or 300))
    max_points = max(100, int(max_param or 2000))
    
    print(f"[Trends API] from={from_ts}, to={to_ts}, gran={gran_val}s, max={max_points}")
    
    # Fetch historical data
    try:
        rows = fetch_history_since(from_ts)
        print(f"[Trends API] Fetched {len(rows)} rows from DB")
    except Exception as e:
        print(f"[Trends API] Error fetching history: {e}")
        return {
            "series": {"ph": [], "ec": [], "temp": []},
            "error": str(e)
        }
    
    # Filter by end time
    rows_filtered = [r for r in rows if r.get("ts") and r["ts"] <= to_ts]
    print(f"[Trends API] After time filter: {len(rows_filtered)} rows")
    
    # Bucket data by time granularity
    buckets = {}  # key: bucket start epoch (int seconds)
    
    for row in rows_filtered:
        ts = row.get("ts")
        if not ts:
            continue
        
        # Calculate bucket
        bucket = (ts // gran_val) * gran_val
        
        if bucket not in buckets:
            buckets[bucket] = {'count': 0, 'ph_sum': 0.0, 'ph_count': 0, 
                              'ec_sum': 0.0, 'ec_count': 0, 
                              'temp_sum': 0.0, 'temp_count': 0}
        
        obj = buckets[bucket]
        
        # Accumulate pH
        if row.get("ph") is not None:
            try:
                obj['ph_sum'] += float(row["ph"])
                obj['ph_count'] += 1
            except (ValueError, TypeError):
                pass
        
        # Accumulate EC
        if row.get("ec_ms_cm") is not None:
            try:
                obj['ec_sum'] += float(row["ec_ms_cm"])
                obj['ec_count'] += 1
            except (ValueError, TypeError):
                pass
        
        # Accumulate Temp
        if row.get("temp_c") is not None:
            try:
                obj['temp_sum'] += float(row["temp_c"])
                obj['temp_count'] += 1
            except (ValueError, TypeError):
                pass
    
    # Build series from buckets (sorted by time)
    ph_series = []
    ec_series = []
    temp_series = []
    
    for bucket in sorted(buckets.keys()):
        obj = buckets[bucket]
        
        if obj['ph_count'] > 0:
            ph_series.append({
                "ts": bucket,
                "value": round(obj['ph_sum'] / obj['ph_count'], 3)
            })
        
        if obj['ec_count'] > 0:
            ec_series.append({
                "ts": bucket,
                "value": round(obj['ec_sum'] / obj['ec_count'], 3)
            })
        
        if obj['temp_count'] > 0:
            temp_series.append({
                "ts": bucket,
                "value": round(obj['temp_sum'] / obj['temp_count'], 2)
            })
    
    print(f"[Trends API] After bucketing: ph={len(ph_series)}, ec={len(ec_series)}, temp={len(temp_series)}")
    
    # Downsample if still too many points (even stride)
    def cap(arr, max_pts):
        n = len(arr)
        if n <= max_pts:
            return arr
        step = max(1, n // max_pts)
        result = [arr[i] for i in range(0, n, step)][:max_pts]
        return result
    
    ph_series = cap(ph_series, max_points)
    ec_series = cap(ec_series, max_points)
    temp_series = cap(temp_series, max_points)
    
    print(f"[Trends API] After capping: ph={len(ph_series)}, ec={len(ec_series)}, temp={len(temp_series)}")
    
    result: dict[str, Any] = {
        "series": {
            "ph": ph_series,
            "ec": ec_series,
            "temp": temp_series
        }
    }
    
    # Add diagnostic info if no data
    if not (ph_series or ec_series or temp_series):
        result["note"] = "No data in selected range"
    
    return result

@app.get("/api/grow/start")
def grow_start():
    """
    Returns the earliest timestamp available in the database for the "Grow" preset.
    This allows the trends chart to span from grow start → now.
    """
    from datetime import timezone
    
    now = datetime.now(timezone.utc)
    start_iso = now.isoformat().replace('+00:00', 'Z')
    
    try:
        # Fetch the earliest timestamp from the database
        rows = fetch_history_since(0)  # Fetch from epoch 0 to get earliest
        
        if rows and len(rows) > 0:
            # Get the first row's timestamp
            earliest_ts = rows[0].get("ts")
            if earliest_ts:
                earliest_dt = datetime.fromtimestamp(earliest_ts, tz=timezone.utc)
                start_iso = earliest_dt.isoformat().replace('+00:00', 'Z')
                print(f"[Grow API] Earliest timestamp: {start_iso} (ts={earliest_ts})")
                return {"start": start_iso}
        
        # Fallback: 30 days ago if no data
        fallback_ts = int(time.time()) - (30 * 24 * 3600)
        fallback_dt = datetime.fromtimestamp(fallback_ts, tz=timezone.utc)
        start_iso = fallback_dt.isoformat().replace('+00:00', 'Z')
        print(f"[Grow API] No data found, using 30d fallback: {start_iso}")
        return {"start": start_iso, "note": "no_data_fallback"}
        
    except Exception as e:
        print(f"[Grow API] Error: {e}")
        # Fallback: 30 days ago on error
        fallback_ts = int(time.time()) - (30 * 24 * 3600)
        fallback_dt = datetime.fromtimestamp(fallback_ts, tz=timezone.utc)
        start_iso = fallback_dt.isoformat().replace('+00:00', 'Z')
        return {"start": start_iso, "error": str(e)}

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

# ---------------- New Namespaced Settings API ------------------------------
@app.get("/api/settings")
def api_settings_get():
    """Return grouped settings by namespace.
    Secrets are not included; email credentials must live outside this table.
    """
    from app.settings import get_settings_grouped
    try:
        result = get_settings_grouped()
        if result is None:
            result = {}
        return result
    except Exception as e:
        import traceback
        logger.error(f"Settings fetch error: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "settings_fetch_failed", "detail": str(e)},
        )


@app.put("/api/settings")
def api_settings_put(body: dict = Body(...)):
    """Accept partial updates; validate; persist; return summary.
    Response: {ok: true, updated: {k:v}, requires_restart: false}
    """
    from app.settings import validate_partial, upsert_settings
    ok, err = validate_partial(body or {})
    if not ok:
        return JSONResponse(status_code=422, content={"ok": False, **(err or {})})
    updated = upsert_settings(body or {})
    # Inform other modules (e.g., relays_core) to refresh lockouts if needed
    try:
        from app.relays_core import MIN_OFF as _X  # noqa
        from app.relays_core import _refresh_lockouts_from_settings  # type: ignore
        _refresh_lockouts_from_settings()
    except Exception:
        pass
    return {"ok": True, "updated": updated, "requires_restart": False}


@app.get("/api/settings/export")
def api_settings_export():
    from app.settings import export_all
    return export_all()


@app.post("/api/settings/import")
def api_settings_import(payload: dict = Body(...)):
    from app.settings import import_all
    res = import_all(payload or {})
    status = 200 if res.get("ok") else 422
    return JSONResponse(status_code=status, content=res)

@app.get("/api/health/override")
def health_override():
    """Quick endpoint to reflect current maintenance override and related safety switches.
    Returns: { maintenance_override: bool, allow_stale_on_override: bool, estop_persist: bool }
    """
    try:
        from app.settings import get_setting_key
        maint = (get_setting_key("safety.maintenance_override", "false") or "false").lower() == "true"
        allow_stale = (get_setting_key("safety.allow_stale_on_override", "false") or "false").lower() == "true"
        estop_persist = (get_setting_key("estop_active", "false") or "false").lower() == "true"
    except Exception:
        maint = False
        allow_stale = False
        estop_persist = False
    return {"maintenance_override": bool(maint), "allow_stale_on_override": bool(allow_stale), "estop_persist": bool(estop_persist)}

# System Mode endpoints (Auto/Manual)
@app.get("/api/system_mode")
def get_system_mode_api():
    """Get current system mode - UNIFIED"""
    from app.unified_mode import get_mode
    mode = get_mode()
    return {"mode": mode}

@app.post("/api/system_mode")
def set_system_mode_api(body: dict = Body(...)):
    """Set system mode - UNIFIED (sets mode for ALL controllers)"""
    from app.unified_mode import set_mode, VALID_MODES
    from app.relays_core import smart_restore_critical_relays
    
    mode = body.get("mode")
    
    if mode not in VALID_MODES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid mode '{mode}'. Must be one of: {', '.join(VALID_MODES)}"}
        )
    
    success = set_mode(mode)
    
    if success:
        logger.info(f"✅ System mode changed to: {mode}")
        # If switched to AUTO, restore critical relays (like main_pump)
        if mode == "auto":
            try:
                smart_restore_critical_relays()
            except Exception as e:
                logger.error(f"Failed to restore relays on auto mode switch: {e}")
        return {"mode": mode, "success": True}
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to set system mode"}
        )

@app.post("/api/system_mode/fast")
def api_system_mode_fast(body: dict = Body(...)):
    """Fast system mode setter - UNIFIED"""
    from app.unified_mode import set_mode
    from app.relays_core import smart_restore_critical_relays
    mode = (body.get("mode") or "").lower()
    if mode not in ("auto", "manual", "maintenance"):
        return JSONResponse(status_code=400, content={"error": "invalid_mode"})
    success = set_mode(mode)
    if success and mode == "auto":
        try:
            smart_restore_critical_relays()
        except:
            pass
    return {"mode": mode, "success": success, "fast": True}

@app.get("/api/system_mode/set")
def api_system_mode_set(mode: str = Query("manual")):
    """GET fallback for system mode - UNIFIED"""
    from app.unified_mode import set_mode
    from app.relays_core import smart_restore_critical_relays
    m = (mode or "").lower()
    if m not in ("auto", "manual", "maintenance"):
        return JSONResponse(status_code=400, content={"error": "invalid_mode"})
    success = set_mode(m)
    if success and m == "auto":
        try:
            smart_restore_critical_relays()
        except:
            pass
    return {"mode": m, "ok": success, "method": "GET"}

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

    # Apply thermostat control with compressor-safe min ON/OFF times
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
    
    # Determine if manual mode should bypass protections
    try:
        from app.unified_mode import get_mode as get_system_mode
        force_flag = (get_system_mode() == 'manual')
    except Exception:
        force_flag = False

    func = relay_funcs.get(name)
    if func:
        result = func(bool(on), reason="override", force=force_flag)
    else:
        # Fallback for any other relays
        from app.relays_core import set_relay
        result = set_relay(name, bool(on), reason="override", force=force_flag)
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

@app.get("/api/estop")
def api_estop_status():
    """Return E-Stop latch status and persisted flag."""
    from app.relays_core import get_estop_status
    try:
        from app.settings import get_setting_key
        persisted = (get_setting_key('estop_active', 'false') or 'false').lower() == 'true'
    except Exception:
        persisted = False
    return {"active": get_estop_status(), "persisted": persisted}

@app.post("/api/estop")
def api_estop_set(body: dict = Body(...)):
    """Engage or release E-Stop latch. When engaged, all relays are forced OFF immediately and persisted."""
    from app.relays_core import engage_estop, release_estop
    from app.settings import set_setting_key
    active = bool(body.get("active", False))
    result = engage_estop() if active else release_estop()
    try:
        # Only persist if safety.estop_persist == true
        from app.settings import get_setting_key
        persist_flag = (get_setting_key('safety.estop_persist', 'false') or 'false').lower() == 'true'
        if persist_flag:
            set_setting_key('estop_active', 'true' if active else 'false')
        else:
            # ensure cleared if disabling persistence
            if not active:
                set_setting_key('estop_active', 'false')
    except Exception:
        pass
    # Attach persisted info
    result["persisted"] = active
    return result

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
    
    # Determine if manual mode should bypass protections
    try:
        from app.unified_mode import get_mode as get_system_mode
        force_flag = (get_system_mode() == 'manual')
    except Exception:
        force_flag = False

    func = relay_funcs.get(name)
    if func:
        result = func(desired, reason="override", force=force_flag)
    else:
        # Fallback for any other relays
        from app.relays_core import set_relay
        result = set_relay(name, desired, reason="override", force=force_flag)
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

@app.get("/debug/ec_check")
def debug_ec_check():
    """Verify EC units are in mS/cm throughout the system."""
    import sqlite3
    from pathlib import Path
    
    status = {"all_in_mscm": True, "checks": {}, "status": "OK"}
    
    # Check 1: Current sensor reading
    try:
        sensor_data = read_all_sensors()
        ec_value = sensor_data.get("ec_mscm")
        status["checks"]["current_sensor"] = {
            "ec_mscm": ec_value,
            "in_expected_range": (0.1 <= ec_value <= 5.0) if ec_value else False,
            "note": "Expected range: 0.1-5.0 mS/cm for typical hydroponic systems"
        }
        if ec_value and (ec_value < 0.1 or ec_value > 5.0):
            status["all_in_mscm"] = False
            status["status"] = "WARNING"
    except Exception as e:
        status["checks"]["current_sensor"] = {"error": str(e)}
    
    # Check 2: Recent database readings
    try:
        db_path = Path("data/rdwc.db")
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get 10 most recent readings
            cursor.execute("SELECT ec_ms_cm FROM readings WHERE ec_ms_cm IS NOT NULL ORDER BY ts DESC LIMIT 10")
            rows = cursor.fetchall()
            
            if rows:
                ec_values = [row[0] for row in rows]
                avg_ec = sum(ec_values) / len(ec_values)
                min_ec = min(ec_values)
                max_ec = max(ec_values)
                
                status["checks"]["database_readings"] = {
                    "sample_size": len(ec_values),
                    "avg_ec_mscm": round(avg_ec, 3),
                    "min_ec": round(min_ec, 3),
                    "max_ec": round(max_ec, 3),
                    "in_expected_range": (0.1 <= avg_ec <= 5.0)
                }
                
                if avg_ec < 0.1 or avg_ec > 5.0:
                    status["all_in_mscm"] = False
                    status["status"] = "WARNING"
            
            conn.close()
    except Exception as e:
        status["checks"]["database_readings"] = {"error": str(e)}
    
    # Check 3: API trends endpoint
    try:
        from_ts = int(time.time()) - 3600  # Last hour
        rows = fetch_history_since(from_ts)
        
        if rows:
            ec_values = [r.get("ec_ms_cm") for r in rows if r.get("ec_ms_cm") is not None]
            if ec_values:
                avg_ec = sum(ec_values) / len(ec_values)
                status["checks"]["trends_api"] = {
                    "sample_size": len(ec_values),
                    "avg_ec_mscm": round(avg_ec, 3),
                    "in_expected_range": (0.1 <= avg_ec <= 5.0)
                }
                
                if avg_ec < 0.1 or avg_ec > 5.0:
                    status["all_in_mscm"] = False
                    status["status"] = "WARNING"
    except Exception as e:
        status["checks"]["trends_api"] = {"error": str(e)}
    
    return status

@app.post("/debug/lights_hold")
def debug_lights_hold(seconds: int = Body(..., embed=True)):
    """Set temporary hold on lights for debugging (blocks all changes)."""
    result = set_lights_hold(seconds)
    return {"ok": True, "message": f"Lights held for {seconds} seconds", **result}

@app.get("/status")
def status():
    age = time.time() - _last_t
    return {"age_s": round(age, 2), **_last}

@app.get("/api/sensors/health")
def api_sensors_health():
    """Sensor health summary for UI badges and monitoring."""
    age = max(0.0, time.time() - _last_t)
    fresh = (_last.get("temp_c") is not None) and (age < 60.0)
    # Get DB last reading age
    db_age = None
    db_ts = None
    try:
        from app.services.sensors_fallback import get_last_reading
        last = get_last_reading()
        if last:
            db_ts = last.get("ts")
            db_age = last.get("stale_seconds")
    except Exception:
        pass
    # Build diagnostics
    diag = {
        "restarts": _sensor_diag.get("restarts", 0),
        "last_watchdog_ts": _sensor_diag.get("last_watchdog_ts"),
        "last_error": _sensor_diag.get("last_error"),
        "last_error_ts": _sensor_diag.get("last_error_ts"),
        "last_cache_ts": _last_t,
    }
    return {
        "cache_age_s": round(age, 1),
        "cache_fresh": bool(fresh),
        "cache_has_data": _last.get("temp_c") is not None,
        "db_ts": db_ts,
        "db_age_s": db_age,
        "diag": diag,
    }

@app.get("/sensors/read")
def sensors_read():
    """
    Get sensor readings.
    Default: return latest database sample (no I2C access).
    If query param mode=direct is provided, perform a one-off direct probe
    against the I2C bus and return that value.
    """
    from fastapi import Request
    from fastapi import Request as _Req  # type: ignore
    # FastAPI injects Request if declared; but keep fallback for safety
    try:
        # When FastAPI calls us, it will pass Request automatically
        pass
    except Exception:
        pass
    # Parse query directly from environment since we're not declaring Request param
    # Use starlette request if available via context (not strictly required)
    mode = None
    try:
        # Use global request available via FastAPI context (best-effort)
        # If unavailable, default to DB mode
        from starlette.requests import Request as _StarReq  # type: ignore
    except Exception:
        _StarReq = None  # type: ignore

    # Simple query parsing via os.environ isn't reliable here; instead, provide a sibling endpoint
    # Implement behavior identical to /api/sensors/read below.
    from app.services.sensors_fallback import get_last_reading
    # Always DB for this legacy endpoint to avoid bus contention
    last = get_last_reading()
    return last or {
        "temperature_c": None,
        "ec_mscm": None,
        "ph": None,
        "ts": None,
        "source": "db",
        "online": False,
        "temp_comp_applied": False,
        "temp_comp_reason": "fallback-empty"
    }

@app.get("/sensors/last")
def sensors_last():
    """
    GET /sensors/last
    Returns the most recent sensor reading from database (stale fallback).
    Used when live sensors are offline to show last known values.
    """
    from app.services.sensors_fallback import get_last_reading
    data = get_last_reading()
    return data or {
        "temperature_c": None,
        "ec_mscm": None,
        "ph": None,
        "ts": None,
        "source": "db",
        "stale_seconds": None,
        "online": False,
        "temp_comp_applied": False,
        "temp_comp_reason": "fallback-empty"
    }

@app.get("/api/sensors/last")
def api_sensors_last():
    """Alias of /sensors/last that always returns latest DB sample."""
    from app.services.sensors_fallback import get_last_reading
    data = get_last_reading()
    return data or {
        "temperature_c": None,
        "ec_mscm": None,
        "ph": None,
        "ts": None,
        "source": "db",
        "stale_seconds": None,
        "online": False,
        "temp_comp_applied": False,
        "temp_comp_reason": "fallback-empty"
    }

@app.get("/api/sensors/read")
def api_sensors_read(mode: str = Query(default="db")):
    """
    Read sensors with selectable mode.
    - mode=db (default): return latest DB sample, no I2C access
    - mode=direct: perform one-off I2C probe and return live values
    """
    if mode != "direct":
        from app.services.sensors_fallback import get_last_reading
        data = get_last_reading()
        if data:
            data["source"] = "db"
        return data or {
            "temperature_c": None,
            "ec_mscm": None,
            "ph": None,
            "ts": None,
            "source": "db",
            "online": False,
            "temp_comp_applied": False,
            "temp_comp_reason": "fallback-empty"
        }
    # Direct mode: lazy import to avoid opening bus at module import time
    try:
        from app.sensors_core import read_all_sensors
        live = read_all_sensors()
        if isinstance(live, dict):
            live["source"] = "i2c"
        return live
    except Exception as e:
        return {
            "temperature_c": None,
            "ec_mscm": None,
            "ph": None,
            "ts": datetime.utcnow().isoformat() + "Z",
            "source": "i2c",
            "online": False,
            "temp_comp_applied": False,
            "temp_comp_reason": f"direct-error: {e}",
            "errors": {"read": str(e)}
        }

@app.get("/api/sensors")
def api_sensors():
    """
    Sensors endpoint for UI - ALWAYS reads from DB cache (written by sensor_poller).
    Never hits I²C bus directly to prevent contention.
    Returns most recent DB reading with online flag based on freshness.
    """
    import sys
    print("▬▬ API_SENSORS CALLED ▬▬", file=sys.stderr, flush=True)
    
    from app.sensors_core import read_sensors_from_db
    from app.settings import get_all_settings
    from app.logger import get_logger
    logger = get_logger(__name__)
    # Read cached (max 60s)
    data = read_sensors_from_db(max_age_sec=60)

    # Check actual calibration state from database  
    settings = get_all_settings()
    
    # pH: check for mid OR low point (2-point calibration typical)
    ph_mid = settings.get("cal.ph.mid")
    ph_low = settings.get("cal.ph.low")
    ph_calibrated = bool(ph_mid or ph_low)
    
    # EC: check for low calibration value (stored as µS/cm, "0" = not calibrated)
    ec_low_us = settings.get("ec.cal_low_us", "0")
    ec_calibrated = (ec_low_us != "0" and ec_low_us != "" and ec_low_us is not None)
    
    # Force output for debugging
    import sys
    print(f"DEBUG API_SENSORS: pH={ph_calibrated} (mid={ph_mid}, low={ph_low}), EC={ec_calibrated} (low_us={ec_low_us})", file=sys.stderr, flush=True)
    
    logger.info(f"Calibration check: pH mid={settings.get('cal.ph.mid')}, low={settings.get('cal.ph.low')}, ph_calibrated={ph_calibrated}")
    logger.info(f"Calibration check: EC low_us={settings.get('ec.cal_low_us')}, ec_calibrated={ec_calibrated}")
    
    cal_state = {
        "temp": {"is_calibrated": False, "detail": "db"},
        "ec": {"is_calibrated": ec_calibrated, "detail": "db"},
        "ph": {"is_calibrated": ph_calibrated, "detail": "db"}
    }
    age_sec = data.get("age_sec")
    stale = bool(age_sec is not None and age_sec > 60)
    online = data.get("online", False)
    # Health state based on age regardless of online flag:
    # green: <60s, yellow: 60-300s (stale but recent), red: >=300s or None
    if age_sec is not None and age_sec < 60:
        health_state = "green"
    elif age_sec is not None and age_sec < 300:
        health_state = "yellow"
    else:
        health_state = "red"

    overrides = data.get("overrides", {})
    mode = data.get("mode")
    result = {
        "temperature_c": data.get("temperature_c"),
        "ec_mscm": data.get("ec_mscm"),
        "ph": data.get("ph"),
        "online": online,
        "ts": data.get("ts"),
        "age_seconds": age_sec,
        "stale": stale,
        "health_state": health_state,
        "temp_comp_applied": data.get("online", False),
        "temp_comp_reason": "sensor_poller" if data.get("online") else f"stale (age:{data.get('age_sec', '?')}s)",
        "cal": cal_state,
        "errors": data.get("errors", {}),
        "mode": mode,
        "overrides": overrides,
        "original_temperature_c": data.get("original_temperature_c"),
        "original_ph": data.get("original_ph"),
        "original_ec_mscm": data.get("original_ec_mscm"),
        "effective_temperature_c": data.get("temperature_c"),
        "effective_ph": data.get("ph"),
        "effective_ec_mscm": data.get("ec_mscm")
    }
    return result

@app.get("/api/sensors/mode")
def api_sensors_mode():
    from app.unified_mode import get_sensor_mode, VALID_MODES
    m = get_sensor_mode()
    return {"mode": m, "valid_modes": sorted(list(VALID_MODES))}

@app.post("/api/sensors/mode")
def api_sensors_mode_set(payload: dict):
    from app.unified_mode import set_sensor_mode, get_sensor_mode, VALID_MODES
    mode = payload.get("mode") if isinstance(payload, dict) else None
    ok = set_sensor_mode(mode) if mode in VALID_MODES else False
    return {"ok": ok, "mode": get_sensor_mode()}

@app.get("/api/sensors/override")
def api_sensors_override_get():
    from app.unified_mode import get_overrides, overrides_effective_age
    o = get_overrides()
    age = overrides_effective_age()
    return {"overrides": o, "age_seconds": age}

@app.post("/api/sensors/override")
def api_sensors_override_set(payload: dict):
    from app.unified_mode import set_overrides
    if not isinstance(payload, dict):
        payload = {}
    updated = set_overrides(payload)
    return {"overrides": updated}

@app.delete("/api/sensors/override/{field}")
def api_sensors_override_clear(field: str):
    from app.unified_mode import clear_override_field, get_overrides
    ok = clear_override_field(field)
    return {"ok": ok, "overrides": get_overrides()}

@app.get("/diag/sensors/once")
def diag_sensors_once():
    """
    Diagnostic endpoint: read each sensor once with timing.
    Uses unified sensor_controller (which handles locking internally).
    Returns raw values and millisecond timing for each step.
    """
    import time as _t
    import datetime as _dt
    from app.sensor_controller import read_sensors

    try:
        t0 = _t.time()
        steps = {}

        def stamp(k):
            steps[k] = round((_t.time() - t0) * 1000, 1)

        data = read_sensors()
        stamp("read_done_ms")

        return {
            "temperature_c": data.get("temperature_c"),
            "ec_mscm": data.get("ec_mscm"),
            "ph": data.get("ph"),
            "ts": data.get("ts", _dt.datetime.utcnow().isoformat() + "Z"),
            "steps": steps,
            "online": data.get("online", False),
            "errors": data.get("errors", {})
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/diag/sensors/leds")
def diag_sensors_leds(on: int = 1):
    """
    Toggle EZO LEDs on/off for RTD(0x66) / EC(0x64) / pH(0x63).
    /diag/sensors/leds?on=1  -> ON
    /diag/sensors/leds?on=0  -> OFF
    """
    try:
        from app.sensor_controller import set_sensor_leds
        result = set_sensor_leds(bool(on))
        return {"on": bool(on), "result": result}
    except Exception as e:
        return {"on": bool(on), "result": {"ok": False, "error": str(e)}}

@app.get("/diag/sensors/flash")
def diag_sensors_flash(count: int = 8, period_ms: int = 250):
    """Flash all EZO LEDs for visual confirmation.
    Query: count (blinks), period_ms (on/off per half-cycle); leaves LEDs ON at end.
    """
    try:
        from app.sensor_controller import flash_sensor_leds
        period_s = max(0.05, period_ms/1000.0)
        result = flash_sensor_leds(count=count, period_s=period_s)
        return {"requested": {"count": int(count), "period_ms": int(period_ms)}, "result": result}
    except Exception as e:
        return {"requested": {"count": int(count), "period_ms": int(period_ms)}, "result": {"ok": False, "error": str(e)}}

@app.post("/read_now")
def read_now():
    """
    Force immediate sensor read via unified controller.
    WARNING: This temporarily contends with sensor_poller on I²C bus.
    Use sparingly - prefer /api/sensors for normal reads.
    """
    try:
        from app.sensor_controller import read_sensors
        data = read_sensors()
        return JSONResponse({"ok": True, "data": data})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

@app.post("/fix_ezo")
def fix_ezo():
    """
    Identify and test all EZO sensors via unified controller.
    """
    try:
        from app.sensor_controller import read_sensors, identify_devices
        ids_result = identify_devices()
        data = read_sensors()
        return JSONResponse({
            "ok": True,
            "ids": ids_result.get("ids", {}),
            "data": data
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

# DEPRECATED: Legacy mode endpoints - use /api/auto/* instead
# These endpoints are kept for backward compatibility but are deprecated.
# New code should use:
#   GET /api/auto/status - Get global and per-controller auto status
#   POST /api/auto/global - Set global auto-enable
#   POST /api/auto/{controller} - Set controller-specific auto-enable

@app.get("/api/controller/modes")
def api_controller_modes():
    """DEPRECATED: Get all controller modes.
    
    Use GET /api/auto/status instead for the new auto-enable system.
    """
    from app.auto_control import get_auto_status, CONTROLLERS
    status = get_auto_status()
    # Return in legacy format for backward compatibility
    return {
        "system_mode": "auto" if status["global_auto"] else "manual",
        "modes": {c: "auto" if status["controllers"][c]["will_automate"] else "hold" for c in CONTROLLERS},
        "unified": True,
        "_deprecated": "Use GET /api/auto/status instead"
    }

@app.get("/api/controller/{name}/mode")
def api_controller_mode_get(name: str):
    """DEPRECATED: Get controller mode.
    
    Use GET /api/auto/status instead for the new auto-enable system.
    """
    from app.auto_control import should_automate, CONTROLLERS
    if name not in CONTROLLERS:
        return {"ok": False, "error": "unknown_controller", "controller": name}
    will_auto = should_automate(name)
    return {
        "ok": True,
        "controller": name,
        "mode": "auto" if will_auto else "hold",
        "_deprecated": "Use GET /api/auto/status instead"
    }

@app.post("/api/controller/{name}/mode")
def api_controller_mode_set(name: str, body: dict = Body(...)):
    """DEPRECATED: Set controller mode.
    
    Use POST /api/auto/{controller} instead for the new auto-enable system.
    """
    from app.auto_control import set_controller_auto_enabled, set_global_auto_enabled, should_automate, CONTROLLERS
    if name not in CONTROLLERS:
        return {"ok": False, "error": "unknown_controller", "controller": name}
    
    mode = body.get("mode") if isinstance(body, dict) else None
    
    # Map legacy modes to new auto-enable system
    if mode == "auto":
        # Enable both global and controller auto
        set_global_auto_enabled(True)
        set_controller_auto_enabled(name, True)
        ok = True
    elif mode in ("manual", "hold", "maintenance"):
        # Disable controller auto (keep global as is)
        set_controller_auto_enabled(name, False)
        ok = True
    else:
        ok = False
    
    return {
        "ok": ok,
        "controller": name,
        "mode": "auto" if should_automate(name) else "hold",
        "_deprecated": "Use POST /api/auto/{controller} instead"
    }

# === NEW CLEAN AUTO-ENABLE ENDPOINTS ===

@app.get("/api/auto/status")
def api_auto_status():
    """Get global and per-controller auto-enable status"""
    import logging
    log = logging.getLogger(__name__)
    try:
        log.debug("/api/auto/status: start")
        try:
            from app.auto_control import get_auto_status
        except Exception as e:
            log.error("/api/auto/status: import auto_control failed", exc_info=True)
            raise
        try:
            status = get_auto_status()
            log.debug("/api/auto/status: success %s", status)
            return status
        except Exception:
            log.error("/api/auto/status: get_auto_status failed", exc_info=True)
            raise
    except Exception as e:
        log.exception("/api/auto/status failed")
        return JSONResponse(status_code=200, content={
            "ok": False,
            "error": str(e),
            "global_auto": None,
            "controllers": {}
        })

@app.post("/api/auto/global")
def api_auto_global_set(body: dict = Body(...)):
    """Set global automation master switch
    
    Body: {"enabled": true/false}
    """
    from app.auto_control import set_global_auto_enabled, get_auto_status
    
    if not isinstance(body, dict) or "enabled" not in body:
        return {"ok": False, "error": "missing_enabled_field"}
    
    enabled = bool(body.get("enabled"))
    ok = set_global_auto_enabled(enabled)
    
    return {
        "ok": ok,
        "global_auto": enabled,
        "status": get_auto_status() if ok else None
    }

@app.post("/api/auto/{controller}")
def api_auto_controller_set(controller: str, body: dict = Body(...)):
    """Set controller-specific auto-enable
    
    Body: {"enabled": true/false}
    """
    from app.auto_control import set_controller_auto_enabled, get_auto_status, CONTROLLERS
    
    if controller not in CONTROLLERS:
        return {"ok": False, "error": "unknown_controller", "controller": controller}
    
    if not isinstance(body, dict) or "enabled" not in body:
        return {"ok": False, "error": "missing_enabled_field"}
    
    enabled = bool(body.get("enabled"))
    ok = set_controller_auto_enabled(controller, enabled)
    
    return {
        "ok": ok,
        "controller": controller,
        "auto_enabled": enabled,
        "status": get_auto_status() if ok else None
    }

@app.post("/api/controller/hold/all")
def api_controller_hold_all(body: dict = None):
    """DEPRECATED: Set or toggle hold state for all controllers.
    
    Use POST /api/auto/global instead for the new auto-enable system.
    
    Body can be:
      - {"hold": true} - Disable global auto
      - {"hold": false} - Enable global auto
    """
    from app.auto_control import set_global_auto_enabled, get_auto_status
    
    body = body or {}
    if "hold" not in body:
        return {"ok": False, "error": "must_specify_hold", "message": "Body must include 'hold' field (true or false)"}
    
    hold_state = bool(body.get("hold"))
    # hold=true means disable auto, hold=false means enable auto
    ok = set_global_auto_enabled(not hold_state)
    status = get_auto_status()
    
    return {
        "ok": ok,
        "hold": hold_state,
        "modes": {c: "hold" if hold_state else "auto" for c in ["ph", "ec", "chiller"]},
        "_deprecated": "Use POST /api/auto/global instead"
    }

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

# --- Calibration (pH) endpoints ---
# All pH calibration logic is now in sensor_controller.py for single source of truth.


def _calib_enabled() -> bool:
    return os.environ.get("CALIB_ENABLE", "0") == "1"


@app.get("/calib/ph/caps")
def calib_ph_caps():
    return {"enabled": _calib_enabled()}

@app.get("/calib/ph/read")
def calib_ph_read():
    """Single pH read for calibration UI - delegated to sensor_controller."""
    from app.sensor_controller import read_ph_single
    return read_ph_single()

@app.get("/calib/ph/status")
def calib_ph_status():
    """Get pH calibration status - delegated to sensor_controller."""
    from app.sensor_controller import get_ph_calibration_status
    return get_ph_calibration_status()

@app.get("/calib/ph/read_stable")
def calib_ph_read_stable(timeout_s: float = 25.0, delta: float = 0.03, min_samples: int = 4, poll_s: float = 2.0):
    """Wait for pH reading to stabilize - delegated to sensor_controller."""
    from app.sensor_controller import read_ph_stable
    return read_ph_stable(timeout_s, delta, min_samples, poll_s)

@app.post("/calib/leds/on")
def calib_leds_on():
    from app.sensor_controller import set_sensor_leds
    return set_sensor_leds(True)

@app.post("/calib/leds/off")
def calib_leds_off():
    from app.sensor_controller import set_sensor_leds
    return set_sensor_leds(False)

@app.post("/calib/leds/blink")
def calib_leds_blink(count: int = 8, period_s: float = 0.25):
    from app.sensor_controller import flash_sensor_leds
    return flash_sensor_leds(count, period_s)

# ---------------- Dosing Calibration ------------------------------
_PUMP_MAP = {
    "ph_up": "dosing_ph_up",
    "grow": "dosing_grow",
    "micro": "dosing_micro",
    "bloom": "dosing_bloom",
}

_RATE_KEY = {
    "ph_up": "dosing.ph_up_ml_per_sec",
    "grow": "dosing.grow_ml_per_sec",
    "micro": "dosing.micro_ml_per_sec",
    "bloom": "dosing.bloom_ml_per_sec",
}

def _pump_label(k: str) -> str:
    return {
        "ph_up": "pH Up Pump",
        "grow": "Grow",
        "micro": "Micro",
        "bloom": "Bloom",
    }.get(k, k)

@app.get("/calib/dose/pumps")
def calib_dose_pumps():
    from app.settings import get_all_settings
    s = get_all_settings()
    rates = {k: float(s.get(_RATE_KEY[k], "0") or 0) for k in _PUMP_MAP.keys()}
    return {"ok": True, "pumps": [{"key": k, "relay": _PUMP_MAP[k], "label": _pump_label(k), "ml_per_sec": rates.get(k, 0.0)} for k in _PUMP_MAP.keys()]}

def _pulse_pump(pump_key: str, seconds: float):
    name = _PUMP_MAP.get(pump_key)
    if not name:
        return {"ok": False, "note": "invalid_pump"}
    if not _calib_enabled():
        return {"ok": False, "note": "Calibration writes disabled. Set CALIB_ENABLE=1 and restart."}
    if get_estop_status():
        return {"ok": False, "note": "estop_active"}
    dur = max(0.2, min(10.0, float(seconds)))
    def _worker():
        try:
            relay_set(name, True, reason="calib_dose", force=True)
            time.sleep(dur)
        finally:
            relay_set(name, False, reason="calib_dose", force=True)
    threading.Thread(target=_worker, daemon=True).start()
    return {"ok": True, "scheduled_s": dur}

def _auto_stop_after(name: str, after_s: float):
    """Safety watchdog: turn pump OFF after after_s unless already off."""
    def _w():
        try:
            time.sleep(max(1.0, float(after_s)))
        except Exception:
            return
        # Best-effort: if still ON, turn OFF
        try:
            status = get_relay_status().get(name, {})
            if status and bool(status.get("state")):
                relay_set(name, False, reason="calib_prime_timeout", force=True)
        except Exception:
            pass
    threading.Thread(target=_w, daemon=True).start()

# --- Relay verification endpoint -------------------------------------------
@app.get("/api/relays/verify")
def api_relays_verify():
    """One-shot relay verification: compare shadow vs actual pin levels (active-low)."""
    from app.relay_guard import get_shadow_state, get_pin_levels, RELAY_PINS as GUARD_PINS
    shadow = get_shadow_state()
    levels = get_pin_levels()
    results = []
    all_ok = True
    for rname, shadow_on in shadow.items():
        level = levels.get(rname)
        actual_on = (level == 'LOW')
        ok = (shadow_on == actual_on)
        if not ok:
            all_ok = False
        results.append({"name": rname, "bcm": GUARD_PINS.get(rname), "shadow": shadow_on, "level": level, "ok": ok})
    return {"ok_all": all_ok, "relays": results, "count": len(results)}

@app.post("/calib/dose/prime")
def calib_dose_prime(pump: str = Query(...), seconds: float = Query(0.5)):
    seconds = max(0.2, min(2.0, float(seconds)))
    return _pulse_pump(pump, seconds)

@app.post("/calib/dose/run")
def calib_dose_run(pump: str = Query(...), seconds: float = Query(5.0)):
    seconds = max(0.2, min(10.0, float(seconds)))
    return _pulse_pump(pump, seconds)

@app.post("/calib/dose/commit")
def calib_dose_commit(pump: str = Query(...), seconds: float = Query(...), measured_ml: float = Query(...)):
    chk = _require_enabled()
    if chk:
        return chk
    try:
        sec = max(0.1, float(seconds))
        ml = max(0.1, float(measured_ml))
        rate = ml / sec
    except Exception:
        return {"ok": False, "note": "invalid_inputs"}
    key = _RATE_KEY.get(pump)
    if not key:
        return {"ok": False, "note": "invalid_pump"}
    # Persist via settings API
    from app.settings import validate_partial, upsert_settings
    payload = {key: f"{rate:.3f}"}
    ok, err = validate_partial(payload)
    if not ok:
        return JSONResponse(status_code=422, content={"ok": False, **(err or {})})
    changed = upsert_settings(payload)
    return {"ok": True, "rate_ml_per_sec": rate, "updated": changed}

@app.get("/calib/dose/status")
def calib_dose_status():
    try:
        st = get_relay_status()
        out = {}
        for k, relay_name in _PUMP_MAP.items():
            out[k] = bool((st.get(relay_name) or {}).get("state", False))
        return {"ok": True, "states": out}
    except Exception as ex:
        return {"ok": False, "note": type(ex).__name__}

@app.post("/calib/dose/start")
def calib_dose_start(pump: str = Query(...)):
    if not _calib_enabled():
        return {"ok": False, "note": "Calibration writes disabled. Set CALIB_ENABLE=1 and restart."}
    if get_estop_status():
        return {"ok": False, "note": "estop_active"}
    name = _PUMP_MAP.get(pump)
    if not name:
        return {"ok": False, "note": "invalid_pump"}
    res = relay_set(name, True, reason="calib_prime", force=True)
    # Safety watchdog (auto-stop) — default 600s; override via env CALIB_PRIME_MAX_S
    try:
        max_s = float(os.environ.get("CALIB_PRIME_MAX_S", "600"))
        _auto_stop_after(name, max_s)
    except Exception:
        _auto_stop_after(name, 600)
    return {"ok": True, "state": bool(res.get("state"))}

@app.post("/calib/dose/stop")
def calib_dose_stop(pump: str = Query(...)):
    if not _calib_enabled():
        return {"ok": False, "note": "Calibration writes disabled. Set CALIB_ENABLE=1 and restart."}
    name = _PUMP_MAP.get(pump)
    if not name:
        return {"ok": False, "note": "invalid_pump"}
    res = relay_set(name, False, reason="calib_prime_stop", force=True)
    return {"ok": True, "state": bool(res.get("state"))}

def _require_enabled():
    if not _calib_enabled():
        return {"ok": False, "note": "Calibration writes disabled. Set CALIB_ENABLE=1 and restart."}
    return None

@app.post("/calib/ph/clear")
def calib_ph_clear():
    chk = _require_enabled()
    if chk:
        return chk
    from app.sensor_controller import clear_ph_calibration
    return clear_ph_calibration()

@app.post("/calib/ph/mid")
def calib_ph_mid(value: float = 7.00):
    chk = _require_enabled()
    if chk:
        return chk
    from app.sensor_controller import calibrate_ph_point
    return calibrate_ph_point("mid", value)

@app.post("/calib/ph/low")
def calib_ph_low(value: float = 4.00):
    chk = _require_enabled()
    if chk:
        return chk
    from app.sensor_controller import calibrate_ph_point
    return calibrate_ph_point("low", value)

@app.post("/calib/ph/high")
def calib_ph_high(value: float = 10.00):
    chk = _require_enabled()
    if chk:
        return chk
    from app.sensor_controller import calibrate_ph_point
    return calibrate_ph_point("high", value)


# EC Calibration Endpoints (unified via sensor_controller)
@app.post("/api/ec/cal/clear")
def ec_cal_clear():
    from app.sensor_controller import clear_ec_calibration
    return clear_ec_calibration()


@app.post("/api/ec/cal/dry")
def ec_cal_dry():
    """
    Apply EC dry calibration (zero point in air).
    Required for K=0.1 probes before low/high calibration.
    """
    from app.sensor_controller import calibrate_ec_dry
    return calibrate_ec_dry()


@app.post("/api/ec/cal/low")
async def ec_cal_low(request: Request):
    """
    Apply EC low-point calibration.
    Automatically selects default based on K value, or pass custom value via {"us_cm": value}
    K=0.1: 84 µS/cm, K=1.0: 1413 µS/cm, K=10.0: 12880 µS/cm
    """
    from app.sensor_controller import calibrate_ec_low
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    # Use None to trigger K-based auto-selection, or allow override
    us_cm = payload.get("us_cm", None)
    return calibrate_ec_low(us_cm)


@app.post("/api/ec/cal/high")
async def ec_cal_high(request: Request):
    """
    Apply EC high-point calibration.
    Automatically selects default based on K value, or pass custom value via {"us_cm": value}
    K=0.1: 1413 µS/cm, K=1.0: 12880 µS/cm, K=10.0: 80000 µS/cm
    """
    from app.sensor_controller import calibrate_ec_high
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    # Use None to trigger K-based auto-selection, or allow override
    us_cm = payload.get("us_cm", None)
    return calibrate_ec_high(us_cm)


@app.post("/api/ec/k")
def ec_set_k(body: dict = Body(...)):
    from app.sensor_controller import set_ec_k_factor
    k = body.get("k", 1.0)
    return set_ec_k_factor(k)


@app.get("/api/ec/cal/status")
def ec_cal_status():
    from app.sensor_controller import get_ec_calibration_status
    return get_ec_calibration_status()


