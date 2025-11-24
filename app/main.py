from fastapi import FastAPI, Body, Query, APIRouter
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
        from app.chiller_control import get_chiller_state
        ch = get_chiller_state()
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
        from app.ezo_i2c_stabilized import EZO, PH_ADDR, EC_ADDR, RTD_ADDR
        s = get_all_settings()
        # Seed default if missing (should already be in DEFAULTS but guard anyway)
        if "sensors.leds_enabled" not in s:
            upsert_settings({"sensors.leds_enabled": "1"})
            s["sensors.leds_enabled"] = "1"
        want_on = s.get("sensors.leds_enabled", "1") in ("1", "true", "True")
        cmd = "L,1" if want_on else "L,0"
        for addr, name in ((PH_ADDR, "pH"), (EC_ADDR, "EC"), (RTD_ADDR, "RTD")):
            try:
                dev = EZO(1, addr, name)
                dev.cmd(cmd, read_len=0, settle=0.05)
            except Exception:
                continue
    except Exception:
        # Non-fatal: service continues even if LEDs can't be set
        pass

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
        from app.ezo_i2c_stabilized import EZO, PH_ADDR, EC_ADDR, RTD_ADDR
        upsert_settings({"sensors.leds_enabled": "1" if enable else "0"})
        cmd = "L,1" if enable else "L,0"
        applied = []
        for addr, name in ((PH_ADDR, "pH"), (EC_ADDR, "EC"), (RTD_ADDR, "RTD")):
            try:
                dev = EZO(1, addr, name)
                dev.cmd(cmd, read_len=0, settle=0.05)
                applied.append(name)
            except Exception:
                continue
        return {"ok": True, "enabled": enable, "applied": applied}
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
            body_preview = ""
            try:
                body_bytes = await request.body()
                # Restore body for downstream handlers
                request._body = body_bytes
                if len(body_bytes) > 0:
                    preview_len = min(256, len(body_bytes))
                    body_preview = body_bytes[:preview_len].decode('utf-8', errors='replace')
                    if len(body_bytes) > 256:
                        body_preview += f"... ({len(body_bytes)} bytes total)"
            except Exception as e:
                body_preview = f"[body read error: {e}]"

            # Structured audit line
            log_msg = f"request_audit method={method} path={path} actor={client}"
            if query:
                log_msg += f" query={query}"
            if body_preview:
                log_msg += f" body={body_preview}"
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
            # read_all() returns {"temperature": <float>, "ph": <float>, "ec_ms": <float>}
            from app.ezo_i2c_stabilized import read_all
            vals = read_all()
            _last = {
                "temp_c": vals.get("temperature"),
                "ph": vals.get("ph"),
                "ec_ms_cm": vals.get("ec_ms"),
                "errors": {}
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
            from app.ezo_i2c_stabilized import read_all
            vals = read_all()
            _last = {
                "temp_c": vals.get("temperature"),
                "ph": vals.get("ph"), 
                "ec_ms_cm": vals.get("ec_ms"),
                "errors": {}
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
    from app.system_mode import _init_tables
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
        from app.chiller_control import start_auto_control
        start_auto_control()
    except Exception:
        # Non-fatal: UI can still enable manually
        pass

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
        for service_name in ["rdwc-api", "rdwc-sensors"]:
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
        # I²C devices
        i2c_devices = []
        try:
            from app.infra.i2c_bus import get_bus
            bus = get_bus()
            if bus:
                # Scan common EZO addresses
                for addr in [0x63, 0x64, 0x66]:  # pH, EC, RTD
                    try:
                        bus.read_byte(addr)
                        device_name = {0x63: "pH", 0x64: "EC", 0x66: "RTD"}.get(addr, "unknown")
                        i2c_devices.append({"address": hex(addr), "name": device_name, "online": True})
                    except Exception:
                        device_name = {0x63: "pH", 0x64: "EC", 0x66: "RTD"}.get(addr, "unknown")
                        i2c_devices.append({"address": hex(addr), "name": device_name, "online": False})
        except Exception as e:
            i2c_devices = [{"error": str(e)}]
        
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
    
    # ===== DATABASE INFO =====
    try:
        import sqlite3
        db_path = Path(DB_PATH)
        
        if db_path.exists():
            db_size_mb = round(db_path.stat().st_size / 1024 / 1024, 2)
            
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
                "newest_reading": newest
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
        
        info["network_info"] = {
            "hostname": hostname,
            "ip_addresses": ip_addresses
        }
    except Exception as e:
        info["network_info"] = {"error": str(e)}
    
    # ===== PROCESS INFO =====
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent']):
            try:
                pinfo = proc.info
                # Only include RDWC-related processes
                if 'rdwc' in pinfo['name'].lower() or 'uvicorn' in pinfo['name'].lower() or 'python' in pinfo['name'].lower():
                    processes.append({
                        "pid": pinfo['pid'],
                        "name": pinfo['name'],
                        "user": pinfo['username'],
                        "memory_percent": round(pinfo['memory_percent'], 2) if pinfo['memory_percent'] else 0
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
    from app.system_mode import get_system_mode
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
            v_attempts = []
            try:
                from app import ezo_i2c as _ezo
                from app.infra.i2c_bus import get_bus as _get_bus
                bus = _get_bus()
                # Attempt identify each board (RTD/EC/pH)
                for addr, name in ((_ezo.ADDR_RTD, "rtd"), (_ezo.ADDR_EC, "ec"), (_ezo.ADDR_PH, "ph")):
                    try:
                        _ezo._send_cmd(bus, addr, "i")
                        _time.sleep(0.35)
                        st, payload = _ezo._poll_until_ready(bus, addr, timeout_s=4.0)
                        v_attempts.append({"board": name, "status": st, "id": payload})
                    except Exception as ex:
                        v_attempts.append({"board": name, "error": str(ex)})
                # Try one pH read single 'R'
                sample = None
                try:
                    _ezo._send_cmd(bus, _ezo.ADDR_PH, "R")
                    _time.sleep(1.2)
                    st, payload = _ezo._poll_until_ready(bus, _ezo.ADDR_PH, timeout_s=5.0)
                    if st == _ezo.EZO_STATUS_SUCCESS and payload:
                        try:
                            sample = float(payload.split(',')[0])
                        except Exception:
                            sample = None
                except Exception:
                    pass
                out["validate_attempts"] = v_attempts
                out["ph_sample"] = sample
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

@app.get("/api/chiller/status")
def api_chiller_status():
    """Get current chiller state, temperature, and automation status."""
    from app.chiller_control import get_chiller_state, get_current_water_temp
    state = get_chiller_state()
    state['current_temp'] = get_current_water_temp()
    return state

@app.post("/api/chiller/auto/enable")
def api_chiller_auto_enable():
    """Enable automatic chiller control based on temperature."""
    from app.chiller_control import start_auto_control
    start_auto_control()
    return {"ok": True, "auto_enabled": True}

@app.post("/api/chiller/auto/disable")
def api_chiller_auto_disable():
    """Disable automatic chiller control."""
    from app.chiller_control import stop_auto_control
    stop_auto_control()
    return {"ok": True, "auto_enabled": False}

@app.post("/api/chiller/force")
def api_chiller_force(req: dict):
    """
    Force chiller ON or OFF for specified duration (emergency/maintenance override).
    Body: {"on": true/false, "duration_minutes": 60} (duration optional)
    """
    from app.chiller_control import force_chiller_state
    desired_on = bool(req.get("on", False))
    duration = req.get("duration_minutes")  # None = indefinite
    result = force_chiller_state(desired_on, duration)
    return result

@app.post("/api/chiller/settings")
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
    Returns: {
        system_mode: str,
        maintenance_override: bool,
        estop: bool,
        controllers: {
            ph: {mode, auto_enabled, holding_reason, guards, learned_ml_per_pH, ...},
            ec: {mode, auto_enabled, holding_reason, guards, learned_ml_per_mScm, ...},
            chiller: {mode, auto_enabled, current_temp, state, ...},
            lights: {mode, is_on, schedule_active, ...},
            circulation: {mode, pumps: {...}}
        }
    }
    """
    import time
    from app.controller_modes import get_all_modes
    from app.system_mode import get_system_mode
    from app.settings import get_setting_key
    from app.relays_core import get_estop_status, get_relay_status
    
    # System-wide state
    system_mode = get_system_mode()
    try:
        maint_override = (get_setting_key("safety.maintenance_override", "false") or "false").lower() == "true"
    except Exception:
        maint_override = False
    estop = get_estop_status()
    
    # Controller modes
    controller_modes = get_all_modes()
    def _to_legacy_mode(m: str) -> str:
        if m == "hold":
            return "maintenance" if maint_override else "manual"
        return m if m in ("auto", "manual", "maintenance") else "auto"
    controller_modes = {k: _to_legacy_mode(v) for k, v in controller_modes.items()}
    
    # Build controller details
    controllers = {}
    
    # pH Controller
    try:
        from app.ph_control import ph_status
        ph_data = ph_status()
        controllers["ph"] = {
            "mode": controller_modes.get("ph", "auto"),
            "auto_enabled": ph_data.get("auto", {}).get("enabled", False),
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
        controllers["ph"] = {"mode": controller_modes.get("ph", "auto"), "error": str(e)}
    
    # EC Controller
    try:
        from app.ec_control import get_ec_status
        ec_data = get_ec_status()
        controllers["ec"] = {
            "mode": controller_modes.get("ec", "auto"),
            "auto_enabled": ec_data.get("auto", {}).get("enabled", False),
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
        controllers["ec"] = {"mode": controller_modes.get("ec", "auto"), "error": str(e)}
    
    # Chiller Controller
    try:
        from app.chiller_control import get_chiller_state, get_current_water_temp
        chiller_state = get_chiller_state()
        controllers["chiller"] = {
            "mode": controller_modes.get("chiller", "auto"),
            "auto_enabled": chiller_state.get("auto_enabled", False),
            "current_temp": get_current_water_temp(),
            "target_temp": float(get_setting_key("chiller.target_temp", "19.0") or "19.0"),
            # Updated default hysteresis per brief (0.7°C)
            "hysteresis": float(get_setting_key("chiller.hysteresis", "0.7") or "0.7"),
            "is_running": chiller_state.get("is_running", False),
            "in_cooldown": chiller_state.get("in_cooldown", False),
        }
    except Exception as e:
        logger.error(f"Failed to get chiller status: {e}")
        controllers["chiller"] = {"mode": controller_modes.get("chiller", "auto"), "error": str(e)}
    
    # Lights Controller
    try:
        relay_status = get_relay_status()
        # get_relay_status() returns key 'state' for ON/OFF
        lights_on = relay_status.get("lights", {}).get("state", False)
        # Check if schedule is active (lights controller in auto means schedule active)
        schedule_active = controller_modes.get("lights", "auto") == "auto"
        controllers["lights"] = {
            "mode": controller_modes.get("lights", "auto"),
            "is_on": lights_on,
            "schedule_active": schedule_active,
        }
    except Exception as e:
        logger.error(f"Failed to get lights status: {e}")
        controllers["lights"] = {"mode": controller_modes.get("lights", "auto"), "error": str(e)}
    
    # Circulation Controller (pumps)
    try:
        relay_status = get_relay_status()
        controllers["circulation"] = {
            "mode": controller_modes.get("circulation", "auto"),
            # get_relay_status() uses 'state' for ON/OFF
            "main_pump": relay_status.get("main_pump", {}).get("state", False),
            "chiller_pump": relay_status.get("chiller_pump", {}).get("state", False),
        }
    except Exception as e:
        logger.error(f"Failed to get circulation status: {e}")
        controllers["circulation"] = {"mode": controller_modes.get("circulation", "auto"), "error": str(e)}
    
    return {
        "system_mode": system_mode,
        "maintenance_override": maint_override,
        "estop": estop,
        "controllers": controllers,
        "timestamp": int(time.time()),
    }

@app.get("/api/chiller/events")
def api_chiller_events(limit: int = Query(200, ge=1, le=1000)):
    """Return recent chiller state transition events (newest first).
    Each event: {ts_utc:int, prev_state:str, new_state:str, reason:str|null}
    """
    try:
        from app.chiller_control import get_chiller_events
        events = get_chiller_events(limit)
        return {"events": events, "count": len(events)}
    except Exception as e:
        logger.error(f"/api/chiller/events failed: {e}")
        return JSONResponse(status_code=500, content={"error": "events_failed"})

# --- Unified dosing endpoints ------------------------------------------------
@app.post("/api/dose/grow")
def dose_grow(body: dict = Body(...)):
    """Manual Grow nutrient dose with centralized safety caps."""
    return _dose_pump("grow", body)

@app.post("/api/dose/micro")
def dose_micro(body: dict = Body(...)):
    """Manual Micro nutrient dose with centralized safety caps."""
    return _dose_pump("micro", body)

@app.post("/api/dose/bloom")
def dose_bloom(body: dict = Body(...)):
    """Manual Bloom nutrient dose with centralized safety caps."""
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
    return get_settings_grouped()


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
    """Get current system mode (auto or manual)"""
    from app.system_mode import get_system_mode
    mode = get_system_mode()
    return {"mode": mode}

@app.post("/api/system_mode")
def set_system_mode_api(body: dict = Body(...)):
    """Set system mode (auto, manual, or maintenance)"""
    from app.system_mode import set_system_mode, VALID_MODES
    
    mode = body.get("mode")
    
    if mode not in VALID_MODES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid mode '{mode}'. Must be one of: {', '.join(VALID_MODES)}"}
        )
    
    success = set_system_mode(mode)
    
    if success:
        return {"mode": mode, "success": True}
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to set system mode"}
        )

@app.post("/api/system_mode/fast")
def api_system_mode_fast(body: dict = Body(...)):
    """Lightweight system mode setter using settings upsert to avoid long DB locks.
    Returns {mode, success}. Falls back handled by caller if needed."""
    from app.settings import upsert_settings
    mode = (body.get("mode") or "").lower()
    if mode not in ("auto", "manual", "maintenance"):
        return JSONResponse(status_code=400, content={"error": "invalid_mode"})
    try:
        upsert_settings({"system_mode": mode})
        # Also propagate to controllers
        try:
            from app.controller_modes import set_mode, CONTROLLERS
            for controller in CONTROLLERS:
                set_mode(controller, mode)
        except Exception:
            pass  # Best effort
        return {"mode": mode, "success": True, "fast": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "fast_set_failed", "detail": str(e)})

@app.get("/api/system_mode/set")
def api_system_mode_set(mode: str = Query("manual")):
    """GET fallback to set system mode quickly without POST (UI workaround)."""
    m = (mode or "").lower()
    if m not in ("auto", "manual"):
        return JSONResponse(status_code=400, content={"error": "invalid_mode"})
    try:
        from app.settings import upsert_settings
        upsert_settings({"system_mode": m})
    except Exception:
        pass
    return {"mode": m, "ok": True, "method": "GET"}

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
        from app.system_mode import get_system_mode
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
        from app.system_mode import get_system_mode
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
    from app.sensors_core import read_sensors_from_db
    # Read cached (max 60s)
    data = read_sensors_from_db(max_age_sec=60)

    # Calibration placeholder (future real state)
    cal_state = {
        "temp": {"is_calibrated": False, "detail": "fallback"},
        "ec": {"is_calibrated": False, "detail": "fallback"},
        "ph": {"is_calibrated": False, "detail": "fallback"}
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
    from app.sensors_mode import get_sensor_mode, VALID_MODES
    m = get_sensor_mode()
    return {"mode": m, "valid_modes": sorted(list(VALID_MODES))}

@app.post("/api/sensors/mode")
def api_sensors_mode_set(payload: dict):
    from app.sensors_mode import set_sensor_mode, get_sensor_mode, VALID_MODES
    mode = payload.get("mode") if isinstance(payload, dict) else None
    ok = set_sensor_mode(mode) if mode in VALID_MODES else False
    return {"ok": ok, "mode": get_sensor_mode()}

@app.get("/api/sensors/override")
def api_sensors_override_get():
    from app.sensors_mode import get_overrides, overrides_effective_age
    o = get_overrides()
    age = overrides_effective_age()
    return {"overrides": o, "age_seconds": age}

@app.post("/api/sensors/override")
def api_sensors_override_set(payload: dict):
    from app.sensors_mode import set_overrides
    if not isinstance(payload, dict):
        payload = {}
    updated = set_overrides(payload)
    return {"overrides": updated}

@app.delete("/api/sensors/override/{field}")
def api_sensors_override_clear(field: str):
    from app.sensors_mode import clear_override_field, get_overrides
    ok = clear_override_field(field)
    return {"ok": ok, "overrides": get_overrides()}

@app.get("/diag/sensors/once")
def diag_sensors_once():
    """
    Diagnostic endpoint: read each sensor once with timing.
    Acquires calibration lock to prevent collision with sensor_poller.
    Returns raw values and millisecond timing for each step.
    """
    import time as _t
    import datetime as _dt
    import fcntl
    from app import ezo_i2c as _ezo
    
    lock_path = "/tmp/rdwc_calib.lock"
    lock_fd = None
    
    try:
        # Acquire lock to signal poller to skip
        lock_fd = open(lock_path, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        
        t0 = _t.time()
        steps = {}
        
        def stamp(k):
            steps[k] = round((_t.time() - t0) * 1000, 1)
        
        t, ec, ph = None, None, None
        
        # RTD (temperature)
        try:
            v = _ezo.read_single(0x66)
            t = float(v) if v is not None else None
        except Exception:
            pass
        stamp("rtd_done_ms")
        
        # EC
        try:
            v = _ezo.read_single(0x64)
            if v is not None:
                v = float(v)
                # Heuristic: if value > 10, assume µS/cm
                ec = v / 1000.0 if v > 10 else v
        except Exception:
            pass
        stamp("ec_done_ms")
        
        # pH
        try:
            v = _ezo.read_single(0x63)
            ph = float(v) if v is not None else None
        except Exception:
            pass
        stamp("ph_done_ms")
        
        return {
            "temperature_c": t,
            "ec_mscm": ec,
            "ph": ph,
            "ts": _dt.datetime.utcnow().isoformat() + "Z",
            "steps": steps
        }
    finally:
        if lock_fd:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()

@app.get("/diag/sensors/leds")
def diag_sensors_leds(on: int = 1):
    """
    Toggle EZO LEDs on/off for RTD(0x66) / EC(0x64) / pH(0x63).
    /diag/sensors/leds?on=1  -> ON
    /diag/sensors/leds?on=0  -> OFF
    """
    try:
        from app.ezo_i2c_stabilized import EZO, PH_ADDR, EC_ADDR, RTD_ADDR
        cmd = "L,1" if bool(on) else "L,0"
        for addr, name in ((PH_ADDR, "pH"), (EC_ADDR, "EC"), (RTD_ADDR, "RTD")):
            try:
                EZO(1, addr, name).cmd(cmd, read_len=0, settle=0.05)
            except Exception:
                pass
        return {"on": bool(on), "result": {"ok": True}}
    except Exception as e:
        return {"on": bool(on), "result": {"ok": False, "error": str(e)}}

@app.get("/diag/sensors/flash")
def diag_sensors_flash(count: int = 8, period_ms: int = 250):
    """Flash all EZO LEDs for visual confirmation.
    Query: count (blinks), period_ms (on/off per half-cycle); leaves LEDs ON at end.
    """
    try:
        from time import sleep
        from app.ezo_i2c_stabilized import EZO, PH_ADDR, EC_ADDR, RTD_ADDR
        period = max(0.05, period_ms/1000.0)
        cnt = max(1, int(count))
        for i in range(cnt):
            for addr, name in ((PH_ADDR, "pH"), (EC_ADDR, "EC"), (RTD_ADDR, "RTD")):
                try:
                    EZO(1, addr, name).cmd("L,1", read_len=0, settle=0.02)
                except Exception:
                    pass
            sleep(period)
            for addr, name in ((PH_ADDR, "pH"), (EC_ADDR, "EC"), (RTD_ADDR, "RTD")):
                try:
                    EZO(1, addr, name).cmd("L,0", read_len=0, settle=0.02)
                except Exception:
                    pass
            sleep(period)
        # Leave ON at end
        for addr, name in ((PH_ADDR, "pH"), (EC_ADDR, "EC"), (RTD_ADDR, "RTD")):
            try:
                EZO(1, addr, name).cmd("L,1", read_len=0, settle=0.02)
            except Exception:
                pass
        return {"requested": {"count": int(count), "period_ms": int(period_ms)}, "result": {"ok": True}}
    except Exception as e:
        return {"requested": {"count": int(count), "period_ms": int(period_ms)}, "result": {"ok": False, "error": str(e)}}

@app.post("/read_now")
def read_now():
    """
    Force immediate sensor read (bypasses DB cache).
    WARNING: This temporarily contends with sensor_poller on I²C bus.
    Use sparingly - prefer /api/sensors for normal reads.
    """
    import fcntl
    lock_path = "/tmp/rdwc_calib.lock"
    
    try:
        # Acquire calibration lock to signal poller to skip next cycle
        lock_fd = open(lock_path, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        
        try:
            from app.ezo_i2c_stabilized import read_all
            data = read_all()
            return JSONResponse({"ok": True, "data": data})
        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

@app.post("/fix_ezo")
def fix_ezo():
    """
    Identify and test all EZO sensors.
    Acquires calibration lock to prevent collision with sensor_poller.
    """
    import fcntl
    lock_path = "/tmp/rdwc_calib.lock"
    
    try:
        # Acquire lock
        lock_fd = open(lock_path, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        
        try:
            from app.ezo_i2c import identify, ADDR_PH, ADDR_EC, ADDR_RTD
            from app.ezo_i2c_stabilized import read_all
            id_ph  = identify(addr=ADDR_PH)
            id_ec  = identify(addr=ADDR_EC)
            id_rtd = identify(addr=ADDR_RTD)
            data   = read_all()
            return JSONResponse({"ok": True, "ids": {"ph": id_ph, "ec": id_ec, "rtd": id_rtd}, "data": data})
        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})

# Generic controller mode endpoints
@app.get("/api/controller/modes")
def api_controller_modes():
    from app.controller_modes import get_all_modes, VALID_MODES
    return {"modes": get_all_modes(), "valid": sorted(list(VALID_MODES))}

@app.get("/api/controller/{name}/mode")
def api_controller_mode_get(name: str):
    from app.controller_modes import get_mode, CONTROLLERS, VALID_MODES
    if name not in CONTROLLERS:
        return {"ok": False, "error": "unknown_controller", "controller": name}
    return {"ok": True, "controller": name, "mode": get_mode(name), "valid": sorted(list(VALID_MODES))}

@app.post("/api/controller/{name}/mode")
def api_controller_mode_set(name: str, body: dict):
    from app.controller_modes import set_mode, get_mode, CONTROLLERS, VALID_MODES, LEGACY_MODE_MAP
    if name not in CONTROLLERS:
        return {"ok": False, "error": "unknown_controller", "controller": name}
    mode = body.get("mode") if isinstance(body, dict) else None
    # Accept valid modes and legacy modes (which will be mapped internally)
    if mode and (mode in VALID_MODES or mode in LEGACY_MODE_MAP):
        ok = set_mode(name, mode)
    else:
        ok = False
    return {"ok": ok, "controller": name, "mode": get_mode(name)}

# Simplified Hold button endpoints
@app.post("/api/controller/{name}/hold")
def api_controller_hold_toggle(name: str, body: dict = None):
    """Toggle or set hold state for a controller.
    
    Body can be:
      - {"hold": true} - Set to hold
      - {"hold": false} - Resume (set to auto)
      - {} or null - Toggle current state
    """
    from app.controller_modes import set_hold, is_held, CONTROLLERS
    if name not in CONTROLLERS:
        return {"ok": False, "error": "unknown_controller", "controller": name}
    
    body = body or {}
    if "hold" in body:
        # Explicit set
        hold_state = bool(body.get("hold"))
    else:
        # Toggle
        hold_state = not is_held(name)
    
    ok = set_hold(name, hold_state)
    return {
        "ok": ok,
        "controller": name,
        "held": is_held(name),
        "mode": "hold" if is_held(name) else "auto"
    }

@app.post("/api/controller/hold/all")
def api_controller_hold_all(body: dict = None):
    """Set or toggle hold state for all controllers.
    
    Body can be:
      - {"hold": true} - Hold all
      - {"hold": false} - Resume all
      - {} or null - Not supported for all (must be explicit)
    """
    from app.controller_modes import set_all_hold, get_all_modes
    
    body = body or {}
    if "hold" not in body:
        return {"ok": False, "error": "must_specify_hold", "message": "Body must include 'hold' field (true or false)"}
    
    hold_state = bool(body.get("hold"))
    ok = set_all_hold(hold_state)
    
    return {
        "ok": ok,
        "hold": hold_state,
        "modes": get_all_modes()
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
 

def _calib_enabled() -> bool:
    return os.environ.get("CALIB_ENABLE", "0") == "1"

def _ph_cmd(cmd: str, settle: float = 0.35, timeout: float = 2.0):
    """Send a pH command using EZO class.
    Returns (status_code, payload_str). Status 1 = success, 0 = failure.
    Adds structured logging to aid calibration debugging.
    """
    import logging
    log = logging.getLogger("calib")
    try:
        from app.ezo_i2c_stabilized import EZO
        ph_dev = EZO(1, 0x63, "pH")  # I2C bus 1, address 0x63
        log.info(f"[PH CMD] send='{cmd}' settle={settle}s timeout={timeout}s")
        
        # Send command and read response
        payload = ph_dev.cmd(cmd, read_len=32, settle=settle)
        status = 1 if payload else 0  # EZO.cmd returns "" on failure
        payload = payload or ""
        
        log.info(f"[PH CMD] status={status} payload='{payload}'")
        return status, payload
    except Exception as ex:
        err = f"error:{type(ex).__name__}"
        logging.getLogger("calib").warning(f"[PH CMD] exception {err}")
        return 0, err

@app.get("/calib/ph/caps")
def calib_ph_caps():
    return {"enabled": _calib_enabled()}

@app.get("/calib/ph/read")
def calib_ph_read():
    """Robust, contention-safe single pH read for the Calibration UI.
    Uses the same I2C lock and direct EZO class to avoid collisions
    with the background poller. Retries once on transient errors.
    """
    import fcntl
    import time as _time
    from app.ezo_i2c_stabilized import EZO

    def _read_once(timeout: float = 3.0):
        try:
            ph_dev = EZO(1, 0x63, "pH")  # I2C bus 1, address 0x63
            # Disable continuous mode
            ph_dev.cmd("C,0", read_len=0, settle=0.3)
            # Read pH value with Atlas 'R' command
            value_str = ph_dev.read_value("R", timeout=timeout, poll=0.15)
            if value_str:
                # Parse first token (pH value)
                tok = value_str.split(",")[0].strip()
                return float(tok)
        except FileNotFoundError:
            # I2C device not available (test/dev environment)
            logger.debug(f"pH read_once failed: I2C device not found")
            raise  # Re-raise to signal hardware unavailable
        except Exception as e:
            logger.debug(f"pH read_once failed: {e}")
        return None

    lock_path = "/tmp/rdwc_calib.lock"
    # Quick hardware check first to avoid long waits when hardware is unavailable
    try:
        test_dev = EZO(1, 0x63, "pH")
        test_dev.cmd("C,0", read_len=0, settle=0.05)
    except FileNotFoundError:
        return {"ok": False, "note": "HardwareUnavailable"}
    except Exception:
        pass
    
    hardware_unavailable = False
    for attempt in (1, 2):
        if hardware_unavailable:
            break
        lock_fd = None
        try:
            lock_fd = open(lock_path, 'w')
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            # Wait longer for background poller to notice lock and skip its cycle
            # Poller checks lock every ~5s, so wait 6s to ensure it sees us
            _time.sleep(6.0)
            # Try up to 3 immediate reads under the same lock to get a payload
            for tries in range(3):
                try:
                    val = _read_once(timeout=3.0 if attempt == 1 else 5.0)
                    if val is not None:
                        return {"ok": True, "value": round(float(val), 3)}
                except FileNotFoundError:
                    # Hardware not available, exit immediately
                    hardware_unavailable = True
                    break
                _time.sleep(1.2)
        except Exception:
            pass
        finally:
            if lock_fd:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                except Exception:
                    pass
        if not hardware_unavailable:
            _time.sleep(0.5)  # brief backoff before retry

    return {"ok": False, "note": "NoData" if not hardware_unavailable else "HardwareUnavailable"}

@app.get("/calib/ph/status")
def calib_ph_status():
    import logging
    import fcntl
    import time as _time
    log = logging.getLogger("calib")
    lock_path = "/tmp/rdwc_calib.lock"
    lock_fd = None
    st = 0
    payload = ""
    try:
        lock_fd = open(lock_path, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        _time.sleep(0.6)
        st, payload = _ph_cmd("Cal,?", settle=1.0, timeout=4.0)
    except Exception as ex:
        log.warning(f"[CALIB] status query error: {ex}")
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass
    # Status 1 = success (from _ph_cmd using EZO class)
    ok = (st == 1)
    flags = []
    note = payload
    # Typical payloads include text like "?,mid,low" when points are set
    try:
        if payload:
            parts = [p.strip() for p in payload.split(",") if p.strip()]
            # Remove leading '?' if present
            if parts and parts[0] == '?':
                parts = parts[1:]
            flags = parts
    except Exception:
        pass
    # Derive points list from flags. Atlas pH 'Cal,?' responses vary by firmware:
    # Examples:
    #   '?CAL,mid,low' -> explicit names
    #   '?CAL,2'       -> numeric count only (mid+low assumed)
    # We map numeric forms to plausible point names for UI friendliness.
    points: list[str] = []
    try:
        if flags:
            # If any non-numeric tokens beyond first, treat them as explicit calibration points
            named = [f for f in flags if not f.isdigit() and f.lower() not in ("?cal",)]
            if named:
                points = named
            else:
                # Numeric-only form; first numeric token = count
                nums = [int(f) for f in flags if f.isdigit()]
                if nums:
                    cnt = nums[0]
                    if cnt == 1:
                        points = ["mid"]
                    elif cnt == 2:
                        points = ["mid", "low"]
                    elif cnt >= 3:
                        points = ["mid", "low", "high"]
    except Exception:
        points = []
    return {"ok": ok, "status": note, "flags": flags, "points": points}

@app.get("/calib/ph/read_stable")
def calib_ph_read_stable(timeout_s: float = 25.0, delta: float = 0.03, min_samples: int = 4, poll_s: float = 2.0):
    """Robust stabilization loop using the same locked single-read path as /calib/ph/read.

    Logic:
    1. Acquire calibration lock per sample to avoid contention.
    2. Perform an explicit 'R' read with EZO class (1.0s settle).
    3. Track moving window; declare stable when absolute delta between last two samples <= delta
       AND (optionally) variance across last 3 samples is small.
    4. Returns {ok, stable, value, samples, duration_s}.

    Parameters are relaxed slightly (delta=0.03) to reflect realistic probe micro-variance.
    """
    import fcntl
    import time as _time
    from app.ezo_i2c_stabilized import EZO
    start = _time.monotonic()
    readings = []

    def _locked_read(timeout: float = 4.5, fast_fail: bool = False):
        try:
            ph_dev = EZO(1, 0x63, "pH")  # I2C bus 1, address 0x63
            # Disable continuous mode
            ph_dev.cmd("C,0", read_len=0, settle=0.3)
            # Read pH value with Atlas 'R' command
            # Use shorter timeout for fast fail mode to avoid long hangs when hardware is unavailable
            actual_timeout = 0.5 if fast_fail else timeout
            value_str = ph_dev.read_value("R", timeout=actual_timeout, poll=0.15)
            if value_str:
                return float(value_str.split(',')[0].strip())
        except RuntimeError as e:
            # EZO raises RuntimeError when SMBus is not available (Windows/test env)
            # Re-raise to signal hardware unavailability
            raise
        except Exception:
            pass
        return None

    lock_path = "/tmp/rdwc_calib.lock"
    attempt = 0
    consecutive_failures = 0
    hardware_unavailable = False
    while _time.monotonic() - start < float(timeout_s):
        attempt += 1
        # Start with short timeout for first attempt, then use fast_fail for subsequent
        # This avoids long hangs when hardware is genuinely unavailable
        fast_fail = attempt > 1 or consecutive_failures > 0
        read_timeout = 1.0 if attempt == 1 else (0.5 if fast_fail else 4.5)
        lock_fd = None
        try:
            lock_fd = open(lock_path, 'w')
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            _time.sleep(0.3)
            val = _locked_read(timeout=read_timeout, fast_fail=fast_fail)
        except RuntimeError:
            # Hardware not available (e.g., SMBus unavailable in test env)
            hardware_unavailable = True
            val = None
        except Exception:
            val = None
        finally:
            if lock_fd:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                except Exception:
                    pass
        
        # Exit immediately if hardware is unavailable
        if hardware_unavailable:
            return {"ok": False, "stable": False, "value": None, "samples": len(readings), "duration_s": round(_time.monotonic() - start, 3), "error": "Hardware unavailable"}

        if val is not None:
            consecutive_failures = 0
            readings.append(val)
            if len(readings) >= int(min_samples):
                last = readings[-1]
                prev = readings[-2]
                recent = readings[-3:]
                max_dev = max(recent) - min(recent)
                if abs(last - prev) <= float(delta) and max_dev <= float(delta) * 1.5:
                    return {"ok": True, "stable": True, "value": round(last, 3), "samples": len(readings), "duration_s": round(_time.monotonic() - start, 3)}
        else:
            consecutive_failures += 1
            # Fail fast if hardware appears unavailable (3 consecutive failures)
            if consecutive_failures >= 3:
                return {"ok": False, "stable": False, "value": None, "samples": len(readings), "duration_s": round(_time.monotonic() - start, 3), "error": "Hardware unavailable"}
        # Use shorter sleep in fast fail mode
        sleep_time = 0.5 if fast_fail else float(poll_s)
        _time.sleep(sleep_time)

    return {"ok": True, "stable": False, "value": (round(readings[-1], 3) if readings else None), "samples": len(readings), "duration_s": round(_time.monotonic() - start, 3)}

@app.post("/calib/leds/on")
def calib_leds_on():
    try:
        from app import ezo_i2c as _ezo
        out = _ezo.enable_all_leds(True)
        return {"ok": True, **out}
    except Exception as ex:
        return {"ok": False, "note": type(ex).__name__}

@app.post("/calib/leds/off")
def calib_leds_off():
    try:
        from app import ezo_i2c as _ezo
        out = _ezo.enable_all_leds(False)
        return {"ok": True, **out}
    except Exception as ex:
        return {"ok": False, "note": type(ex).__name__}

@app.post("/calib/leds/blink")
def calib_leds_blink(count: int = 8, period_s: float = 0.25):
    try:
        from app import ezo_i2c as _ezo
        out = _ezo.blink_leds(count=count, period_s=period_s)
        return out
    except Exception as ex:
        return {"ok": False, "note": type(ex).__name__}

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
def calib_dose_prime(pump: str, seconds: float = 0.5):
    seconds = max(0.2, min(2.0, float(seconds)))
    return _pulse_pump(pump, seconds)

@app.post("/calib/dose/run")
def calib_dose_run(pump: str, seconds: float = 5.0):
    seconds = max(0.2, min(10.0, float(seconds)))
    return _pulse_pump(pump, seconds)

@app.post("/calib/dose/commit")
def calib_dose_commit(pump: str, seconds: float, measured_ml: float):
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
def calib_dose_start(pump: str):
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
def calib_dose_stop(pump: str):
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
    # Use same I2C lock and longer timeouts as calibration points
    import fcntl
    lock_path = "/tmp/rdwc_calib.lock"
    lock_fd = None
    try:
        lock_fd = open(lock_path, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        time.sleep(1.0)  # allow in-flight reads to finish
        st, payload = _ph_cmd("Cal,clear", settle=1.2, timeout=4.0)
        from app import ezo_i2c as _ezo
        ok = (st == _ezo.EZO_STATUS_SUCCESS)
        if not ok and st == _ezo.EZO_STATUS_SYNTAX_ERROR:
            # One retry on syntax error
            time.sleep(0.5)
            st, payload = _ph_cmd("Cal,clear", settle=1.6, timeout=5.0)
            ok = (st == _ezo.EZO_STATUS_SUCCESS)
        return {"ok": ok, "note": payload or ("Cleared" if ok else f"Status {st}")}
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass

def _apply_point(kind: str, value: float):
    import logging
    log = logging.getLogger("calib")
    log.info(f"[CALIB] apply kind={kind} raw_value={value}")
    chk = _require_enabled()
    if chk:
        log.warning(f"[CALIB] rejected (disabled): {chk}")
        return chk
    v = max(0.0, min(14.0, float(value)))
    log.info(f"[CALIB] normalized value={v:.2f}")
    
    # CRITICAL: Pause sensor polling to avoid I2C bus contention during calibration
    import fcntl
    lock_path = "/tmp/rdwc_calib.lock"
    lock_fd = None
    try:
        # Acquire exclusive lock to block sensor polling
        lock_fd = open(lock_path, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        
        # Wait for any in-flight sensor read to complete
        time.sleep(2.0)
        
        # Atlas Scientific EZO pH: Cal,mid,7.00 or Cal,low,4.00 or Cal,high,10.00
        # Calibration commands take 900ms-1600ms, use longer timeout
        # Attempt up to 3 times with progressively longer settle/timeout for transient 2/254/255 states
        from app import ezo_i2c as _ezo
        attempts = [
            (1.6, 5.0),
            (2.2, 6.5),
            (2.8, 8.0),
        ]
        last_st, last_payload = None, ""
        for idx, (settle_s, to_s) in enumerate(attempts, start=1):
            # Defensive: ensure continuous is off and device is ready between tries
            try:
                from app.infra.i2c_bus import get_bus as _get_bus
                bus = _get_bus()
                _ezo._send_cmd(bus, _ezo.ADDR_PH, "C,0")
                time.sleep(0.25)
                _ezo._poll_until_ready(bus, _ezo.ADDR_PH, timeout_s=2.0)
            except Exception:
                pass

            st, payload = _ph_cmd(f"Cal,{kind},{v:.2f}", settle=settle_s, timeout=to_s)
            last_st, last_payload = st, payload
            if st == _ezo.EZO_STATUS_SUCCESS:
                log.info(f"[CALIB] success on attempt {idx} settle={settle_s} timeout={to_s}")
                return {"ok": True, "note": payload or f"{kind.title()} calibrated at {v:.2f}"}

            # If syntax error (2), pending (254) or timeout/other (255/0), back off then retry
            log.warning(f"[CALIB] attempt {idx} non-success status={st} payload='{payload}', backing off")
            time.sleep(0.8 if idx == 1 else 1.2)

        log.error(f"[CALIB] all attempts failed, status={last_st} payload='{last_payload}'")
        return {"ok": False, "note": f"Status {last_st}, response: '{last_payload}'"}
    finally:
        # Always release lock
        if lock_fd:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass

@app.post("/calib/ph/mid")
def calib_ph_mid(value: float = 7.00):
    return _apply_point("mid", value)

@app.post("/calib/ph/low")
def calib_ph_low(value: float = 4.00):
    return _apply_point("low", value)

@app.post("/calib/ph/high")
def calib_ph_high(value: float = 10.00):
    return _apply_point("high", value)


# EC Calibration Endpoints
@app.post("/api/ec/cal/clear")
def ec_cal_clear():
    """Clear EC calibration"""
    try:
        from app.ezo_i2c_stabilized import EZO, EC_ADDR
        ec_dev = EZO(1, EC_ADDR, "EC")
        response = ec_dev.cmd("Cal,clear", read_len=32, settle=0.3)
        return {"ok": True, "response": response or "Calibration cleared"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/ec/cal/low")
def ec_cal_low(body: dict = Body(...)):
    """Apply low-point EC calibration (typically 1413 µS/cm)"""
    try:
        us_cm = body.get("us_cm", 1413)
        from app.ezo_i2c_stabilized import EZO, EC_ADDR
        ec_dev = EZO(1, EC_ADDR, "EC")
        # EZO EC expects calibration value in µS/cm
        response = ec_dev.cmd(f"Cal,low,{us_cm}", read_len=32, settle=0.9)
        return {"ok": True, "response": response or f"Low calibration applied at {us_cm} µS/cm"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/ec/cal/high")
def ec_cal_high(body: dict = Body(...)):
    """Apply high-point EC calibration (typically 12,880 µS/cm)"""
    try:
        us_cm = body.get("us_cm", 12880)
        from app.ezo_i2c_stabilized import EZO, EC_ADDR
        ec_dev = EZO(1, EC_ADDR, "EC")
        response = ec_dev.cmd(f"Cal,high,{us_cm}", read_len=32, settle=0.9)
        return {"ok": True, "response": response or f"High calibration applied at {us_cm} µS/cm"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/ec/k")
def ec_set_k(body: dict = Body(...)):
    """Set EC probe K factor (probe constant)"""
    try:
        k = body.get("k", 1.0)
        from app.ezo_i2c_stabilized import EZO, EC_ADDR
        ec_dev = EZO(1, EC_ADDR, "EC")
        response = ec_dev.cmd(f"K,{k:.1f}", read_len=32, settle=0.3)
        return {"ok": True, "response": response or f"K factor set to {k}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/ec/cal/status")
def ec_cal_status():
    """Get EC calibration status"""
    try:
        from app.ezo_i2c_stabilized import EZO, EC_ADDR
        ec_dev = EZO(1, EC_ADDR, "EC")
        
        # Query calibration status
        cal_response = ec_dev.cmd("Cal,?", read_len=32, settle=0.3)
        
        # Query K value
        k_response = ec_dev.cmd("K,?", read_len=32, settle=0.3)
        
        # Parse cal status: "?Cal,0" = uncalibrated, "?Cal,1" = one-point, "?Cal,2" = two-point
        cal_status = "unknown"
        if cal_response:
            if "0" in cal_response:
                cal_status = "none"
            elif "1" in cal_response:
                cal_status = "low"
            elif "2" in cal_response:
                cal_status = "two-point"
        
        # Parse K value
        k_value = None
        if k_response and "," in k_response:
            try:
                k_value = float(k_response.split(",")[1])
            except Exception:
                pass
        
        return {
            "ok": True,
            "cal": cal_status,
            "k": k_value,
            "cal_raw": cal_response,
            "k_raw": k_response
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

