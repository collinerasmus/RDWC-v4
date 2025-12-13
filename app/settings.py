"""
RDWC-v4 Settings Management
Handles persistent settings storage in SQLite with validation and caching.

Extended with a namespaced key/value model used by the new System Settings UI.
Keeps backward compatibility with the legacy Settings dataclass and /settings
endpoints (system_volume_liters, lights_on_time, lights_duration_hours).
"""
import sqlite3
import re
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import pytz

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

# South African timezone
SA_TZ = pytz.timezone('Africa/Johannesburg')

@dataclass
class Settings:
    """System settings dataclass"""
    system_volume_liters: float
    lights_on_time: str  # "HH:MM" format
    lights_duration_hours: int
    
    def __post_init__(self):
        """Validate settings after initialization"""
        if self.system_volume_liters <= 0:
            raise ValueError("System volume must be greater than 0")
        if not re.match(r'^\d{2}:\d{2}$', self.lights_on_time):
            raise ValueError("Lights on time must be in HH:MM format")
        if not (1 <= self.lights_duration_hours <= 24):
            raise ValueError("Lights duration must be between 1 and 24 hours")


# Cache for settings
_settings_cache: Optional[Settings] = None

# -----------------------------
# Namespaced settings extension
# -----------------------------

# Defaults per spec
DEFAULTS: Dict[str, str] = {
    # general
    "general.grow_name": "RDWC v4",
    "general.timezone": "Africa/Johannesburg",
    "general.reservoir_liters": "25",
    "general.grow_start_date": "",  # YYYY-MM-DD or empty string

    # targets
    # WARNING: These are STATIC defaults. In production, targets MUST be set based on grow stage from scheduler.
    # For seedlings: 0.4-0.6 mS/cm. For veg: 0.8-1.2 mS/cm. For flower: 1.2-1.8 mS/cm.
    # If scheduler is broken, EC auto MUST NOT RUN. Use safe seedling defaults here.
    "targets.ph_low": "5.8",
    "targets.ph_high": "6.2",
    "targets.ec_low": "0.4",
    "targets.ec_high": "0.6",
    "targets.ec_target": "1.8",
    "targets.ec_tolerance": "0.2",
    "targets.temp_target_c": "20",
    
    # EC sensor calibration (persisted to survive power cycles)
    "ec.k_value": "1.0",  # EC probe K factor (probe constant) - must match physical probe label
    "ec.cal_dry": "0",  # Dry calibration point (0 = not calibrated, 1 = calibrated)
    "ec.cal_low_us": "0",  # Low calibration point in µS/cm (0 = not calibrated)
    "ec.cal_high_us": "0",  # High calibration point in µS/cm (0 = not calibrated)

    # dosing
    "dosing.pulse_ml_grow": "0",
    "dosing.pulse_ml_micro": "0",
    "dosing.pulse_ml_bloom": "0",
    "dosing.max_ml_hour_": "0",
    "dosing.max_ml_day_": "0",
    "dosing.mix_delay_s": "0",
    # pH Up dosing controls
    # Calibrated pH Up pump flow rate (ml/s) updated from commissioning (was placeholder 25)
    "dosing.ph_up_ml_per_sec": "0.758",
    # Nutrient pump calibration (ml/s)
    "dosing.grow_ml_per_sec": "20",
    "dosing.micro_ml_per_sec": "20",
    "dosing.bloom_ml_per_sec": "20",
    # Daily pH Up cap (approx. 500s * 0.758 ml/s ≈ 380 ml)
    "dosing.ph_up_max_ml_per_day": "380",
    # Max single pH Up dose (ml)
    "dosing.ph_up_max_single_ml": "5",
    # Minimum interval between pH Up doses (seconds)
    "dosing.ph_min_interval_s": "300",
    # Post‑dose stabilization observation window (seconds) before recording final reading
    "dosing.ph_stabilization_window_s": "300",
    # Delta threshold for considering pH stable (absolute change over final window)
    "dosing.ph_stabilization_delta_threshold": "0.02",
    # Safety: maximum predicted delta pH allowed for a single dose (blocks if exceeded)
    "dosing.ph_max_predicted_delta_ph": "0.5",
    # Observe window after dose (7 hours based on real-world stabilization data)
    "dosing.observe_s_after_dose": "25200",

    # pH Up automation (production defaults)
    # NOTE: ph.auto_enabled is DEPRECATED - use controls.ph_auto via auto_control.py
    "dosing.poll_interval_s": "30",
    "dosing.ph_up_step_min_ml": "0.5",
    "dosing.ph_up_step_max_ml": "5.0",
    "dosing.ph_up_safety_factor": "0.6",
    # EC below this baseline holds automation (mS/cm)
    "dosing.ec_baseline_min": "0.2",
    # Initial micro-dose used when learner has not produced a refined ml/pH estimate yet
    # Ensures first automated correction is a very small, safe amount
    "dosing.ph_up_initial_ml": "0.1",  # Start with 0.1ml, let learning build up gradually (0.1, 0.2, etc)

    # EC automation
    # NOTE: ec.auto_enabled is DEPRECATED - use controls.ec_auto via auto_control.py
    # Conservative step sizes for smooth, gradual nutrient delivery (not shocking plants)
    "dosing.ec_step_ml_min": "5",
    "dosing.ec_step_ml_max": "30",
    "dosing.ec_safety_factor": "0.6",
    "dosing.ec_min_interval_s": "300",
    "dosing.ec_max_ml_day": "0",

    # safety
    "safety.main_pump_min_off_s": "5",
    "safety.temperature_pump_min_off_s": "5",
    "safety.temperature_min_off_s": "300",
    "safety.temperature_min_on_s": "60",
    "safety.estop_persist": "false",
    # allow force-bypass of cooldown/daily cap for testing only
    "safety.allow_force": "false",
    # maintenance override (global test mode)
    "safety.maintenance_override": "false",
    # manual dosing safety caps (server-side enforced)
    # Updated safety caps from commissioning
    "safety.max_seconds_per_press": "10",
    "safety.max_total_seconds_per_24h": "500",
    "safety.min_off_window_sec": "2",
    # TEST-ONLY: allow dosing when sensors are stale, but only when maintenance_override is also true
    # Defaults to OFF for production safety
    "safety.allow_stale_on_override": "false",

    # temperature (Hailea HS-52A intelligent control)
    "temperature.target_temp": "19.0",           # °C - optimal for cannabis DWC/RDWC
    "temperature.hysteresis": "0.5",             # °C - deadband (turn on at 19.5, off at 18.5)
    "temperature.min_on_seconds": "300",         # 5 min minimum runtime (compressor protection)
    "temperature.min_off_seconds": "600",        # 10 min minimum off time (cooldown)
    # NOTE: temperature.auto_enabled is DEPRECATED - use controls.temperature_auto via auto_control.py
    "temperature.control_interval_s": "30",      # Check temperature every 30s
    "temperature.max_temp_alarm": "24.0",        # Alert if water exceeds this (°C)
    "temperature.min_temp_alarm": "16.0",        # Alert if water below this (°C)
    "temperature.stage": "default",              # veg, flower, or default

    # alerts
    "alerts.email_to": "",
    "alerts.ph_hi_alert": "0",
    "alerts.ph_lo_alert": "0",
    "alerts.ec_hi_alert": "0",
    "alerts.ec_lo_alert": "0",
    "alerts.temp_hi_alert": "0",
    "alerts.temp_lo_alert": "0",
    "alerts.alert_cooldown_s": "600",

    # ui
    "ui.default_sensor_range": "24h",
    "ui.relays_poll_ms": "1000",
    "ui.sensors_poll_ms": "5000",
    # sensors
    'sensors.leds_enabled': '1',  # default: keep EZO LEDs ON for visual diagnostics
}

# Module-level flag to ensure we only seed defaults once per process
_defaults_seeded = False

def _ensure_table_seed_defaults() -> None:
    """Ensure settings table exists and seed DEFAULTS using the shared pooled connection.
    This avoids diverging DB paths when tests override app.db_pool.DB_PATH.
    Only runs once per process to minimize contention."""
    global _defaults_seeded
    if _defaults_seeded:
        return

    _init_settings_table()
    # Use pooled connection to respect any test overrides of DB_PATH in db_pool
    from app.db_pool import get_conn
    conn = get_conn()
    cur = conn.cursor()
    for key, val in DEFAULTS.items():
        cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, val))
    conn.commit()
    _defaults_seeded = True

def get_all_settings() -> Dict[str, str]:
    """Return flat dict of all settings (string values)."""
    _ensure_table_seed_defaults()
    from app.db_pool import get_conn
    conn = get_conn(readonly=True)
    cur = conn.execute("SELECT key, value FROM settings")
    result = {}
    for row in cur.fetchall():
        if row and len(row) >= 2:
            k, v = row[0], row[1]
            result[k] = v if v is not None else ""
    return result

def get_settings_grouped() -> Dict[str, Dict[str, Any]]:
    """Return grouped settings by namespace: {namespace: {key: value}}.
    Values are strings; UI/backend can cast/validate as needed.
    """
    flat = get_all_settings()
    grouped: Dict[str, Dict[str, Any]] = {}
    for k, v in flat.items():
        if "." in k:
            ns, leaf = k.split(".", 1)
        else:
            ns, leaf = "root", k
        grouped.setdefault(ns, {})[leaf] = v
    return grouped

def upsert_settings(partial: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert partial settings dict where keys are fully qualified (e.g. 'ui.relays_poll_ms').
    Returns dict of actually updated keys.
    """
    # DON'T call _ensure_table_seed_defaults() here - too slow on every save
    # Table initialization happens once at startup via get_all_settings
    changed: Dict[str, Any] = {}
    from app.db_pool import get_conn
    conn = get_conn()
    cur = conn.cursor()
    for key, val in partial.items():
        if not isinstance(key, str):
            continue
        sval = str(val)
        cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, sval))
        changed[key] = sval
    conn.commit()
    # bust legacy cache only for legacy dataclass keys
    global _settings_cache
    _settings_cache = None
    return changed

def validate_partial(partial: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, str]]]:
    """Validate incoming partial settings. Returns (ok, error) where error is
    {"field": key, "message": msg} on failure.
    Enforces ranges and cross-field checks required by acceptance criteria.
    """
    # Helper to get float/int safely
    def f(x, default=None):
        try:
            return float(x)
        except Exception:
            return default
    def i(x, default=None):
        try:
            return int(float(x))
        except Exception:
            return default

    # Build a view of final values = current DB with partial overrides
    current = get_all_settings()
    final = {**current, **{k: str(v) for k, v in partial.items()}}

    # --- Type/limits ---
    # pH 4.0–7.5
    if "targets.ph_low" in final:
        v = f(final["targets.ph_low"])
        if v is None or not (4.0 <= v <= 7.5):
            return False, {"field": "targets.ph_low", "message": "Must be in 4.0–7.5"}
    if "targets.ph_high" in final:
        v = f(final["targets.ph_high"])
        if v is None or not (4.0 <= v <= 7.5):
            return False, {"field": "targets.ph_high", "message": "Must be in 4.0–7.5"}

    # EC 0.0–4.0 mS/cm (support both low/high and target/tolerance models)
    for k in ("targets.ec_low", "targets.ec_high"):
        if k in final:
            v = f(final[k])
            if v is None or not (0.0 <= v <= 4.0):
                return False, {"field": k, "message": "Must be in 0.0–4.0"}
    if "targets.ec_target" in final:
        v = f(final["targets.ec_target"])
        if v is None or not (0.0 <= v <= 4.0):
            return False, {"field": "targets.ec_target", "message": "Must be in 0.0–4.0"}
    if "targets.ec_tolerance" in final:
        v = f(final["targets.ec_tolerance"])
        if v is None or not (0.0 <= v <= 1.0):
            return False, {"field": "targets.ec_tolerance", "message": "Must be in 0.0–1.0"}

    # Temp 15–28 °C
    if "targets.temp_target_c" in final:
        v = i(final["targets.temp_target_c"])
        if v is None or not (15 <= v <= 28):
            return False, {"field": "targets.temp_target_c", "message": "Must be 15–28"}

    # Volumes 1–1000 L
    if "general.reservoir_liters" in final:
        v = f(final["general.reservoir_liters"])
        if v is None or not (1 <= v <= 1000):
            return False, {"field": "general.reservoir_liters", "message": "Must be 1–1000"}

    # Grow start date (YYYY-MM-DD or empty)
    if "general.grow_start_date" in final:
        val = str(final["general.grow_start_date"]).strip()
        if val:
            # Validate format
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', val):
                return False, {"field": "general.grow_start_date", "message": "Must be YYYY-MM-DD or empty"}
            # Check it's a real date and not in the future
            try:
                date_obj = datetime.strptime(val, "%Y-%m-%d").date()
                # Get timezone from settings
                tz_str = final.get("general.timezone", "Africa/Johannesburg")
                try:
                    tz = pytz.timezone(tz_str)
                except Exception:
                    tz = SA_TZ
                today = datetime.now(tz).date()
                if date_obj > today:
                    return False, {"field": "general.grow_start_date", "message": "date_in_future"}
            except ValueError:
                return False, {"field": "general.grow_start_date", "message": "Invalid date"}

    # Min on/off 0–3600 s
    for k in ("safety.main_pump_min_off_s", "safety.temperature_pump_min_off_s",
              "safety.temperature_min_off_s", "safety.temperature_min_on_s"):
        if k in final:
            v = i(final[k])
            if v is None or not (0 <= v <= 3600):
                return False, {"field": k, "message": "Must be 0–3600"}

        # Manual dosing caps
        if "safety.max_seconds_per_press" in final:
            v = f(final["safety.max_seconds_per_press"])
            if v is None or not (0.1 <= v <= 10.0):
                return False, {"field": "safety.max_seconds_per_press", "message": "Must be 0.1–10.0 seconds"}
        if "safety.max_total_seconds_per_24h" in final:
            v = f(final["safety.max_total_seconds_per_24h"])
            if v is None or not (0.0 <= v <= 600.0):
                return False, {"field": "safety.max_total_seconds_per_24h", "message": "Must be 0–600 seconds"}
        if "safety.min_off_window_sec" in final:
            v = f(final["safety.min_off_window_sec"])
            if v is None or not (0.0 <= v <= 60.0):
                return False, {"field": "safety.min_off_window_sec", "message": "Must be 0–60 seconds"}
    
    # Temperature control (14–26°C safe range for cannabis)
    if "temperature.target_temp" in final or "chiller.target_temp" in final:  # Support legacy chiller.target_temp
        key = "temperature.target_temp" if "temperature.target_temp" in final else "chiller.target_temp"
        v = f(final[key])
        if v is None or not (14.0 <= v <= 26.0):
            return False, {"field": key, "message": "Must be 14.0–26.0°C"}
    
    if "temperature.hysteresis" in final or "chiller.hysteresis" in final:  # Support legacy
        key = "temperature.hysteresis" if "temperature.hysteresis" in final else "chiller.hysteresis"
        v = f(final[key])
        if v is None or not (0.1 <= v <= 3.0):
            return False, {"field": key, "message": "Must be 0.1–3.0°C"}
    
    # Temperature timing (0-3600s) - support both new and legacy keys
    for old_k, new_k in [("chiller.min_on_seconds", "temperature.min_on_seconds"), 
                          ("chiller.min_off_seconds", "temperature.min_off_seconds"),
                          ("chiller.control_interval_s", "temperature.control_interval_s")]:
        k = new_k if new_k in final else old_k
        if k in final:
            v = i(final[k])
            if v is None or not (0 <= v <= 3600):
                return False, {"field": k, "message": "Must be 0–3600 seconds"}
    
    # Temperature alarm temps - support both new and legacy keys
    if "temperature.max_temp_alarm" in final or "chiller.max_temp_alarm" in final:
        key = "temperature.max_temp_alarm" if "temperature.max_temp_alarm" in final else "chiller.max_temp_alarm"
        v = f(final[key])
        if v is None or not (20.0 <= v <= 30.0):
            return False, {"field": key, "message": "Must be 20.0–30.0°C"}
    
    if "temperature.min_temp_alarm" in final or "chiller.min_temp_alarm" in final:
        key = "temperature.min_temp_alarm" if "temperature.min_temp_alarm" in final else "chiller.min_temp_alarm"
        v = f(final[key])
        if v is None or not (10.0 <= v <= 18.0):
            return False, {"field": key, "message": "Must be 10.0–18.0°C"}

    # Dosing settings validation
    if "dosing.ph_up_ml_per_sec" in final:
        v = f(final["dosing.ph_up_ml_per_sec"])
        if v is None or not (0.1 <= v <= 200.0):
            return False, {"field": "dosing.ph_up_ml_per_sec", "message": "Must be 0.1–200"}
    for k in ("dosing.grow_ml_per_sec","dosing.micro_ml_per_sec","dosing.bloom_ml_per_sec"):
        if k in final:
            v = f(final[k])
            if v is None or not (0.1 <= v <= 200.0):
                return False, {"field": k, "message": "Must be 0.1–200"}
    if "dosing.ph_up_max_ml_per_day" in final:
        v = f(final["dosing.ph_up_max_ml_per_day"])
        if v is None or not (0.0 <= v <= 500.0):
            return False, {"field": "dosing.ph_up_max_ml_per_day", "message": "Must be 0–500"}
    if "dosing.ph_up_max_single_ml" in final:
        v = f(final["dosing.ph_up_max_single_ml"])
        if v is None or not (0.1 <= v <= 100.0):
            return False, {"field": "dosing.ph_up_max_single_ml", "message": "Must be 0.1–100"}
    if "dosing.ph_min_interval_s" in final:
        v = i(final["dosing.ph_min_interval_s"])
        if v is None or not (0 <= v <= 86400):
            return False, {"field": "dosing.ph_min_interval_s", "message": "Must be 0–86400"}
    if "dosing.observe_s_after_dose" in final:
        v = i(final["dosing.observe_s_after_dose"])
        if v is None or not (0 <= v <= 86400):
            return False, {"field": "dosing.observe_s_after_dose", "message": "Must be 0–86400"}

    # --- Cross-field checks ---
    ph_lo = f(final.get("targets.ph_low"), f(current.get("targets.ph_low", 5.8)))
    ph_hi = f(final.get("targets.ph_high"), f(current.get("targets.ph_high", 6.2)))
    if ph_lo is not None and ph_hi is not None and not (ph_lo < ph_hi):
        return False, {"field": "targets.ph_low", "message": "Must be < ph_high"}

    # Prefer low/high model when provided
    ec_lo = f(final.get("targets.ec_low"), f(current.get("targets.ec_low", 0.8)))
    ec_hi = f(final.get("targets.ec_high"), f(current.get("targets.ec_high", 1.2)))
    if ec_lo is not None and ec_hi is not None:
        if not (ec_lo < ec_hi):
            return False, {"field": "targets.ec_low", "message": "Must be < ec_high"}
        if not (0.0 <= ec_lo) or not (ec_hi <= 4.0):
            return False, {"field": "targets.ec_low", "message": "Range must be within 0–4"}
    else:
        # Fallback: target±tolerance model
        ec_tgt = f(final.get("targets.ec_target"), f(current.get("targets.ec_target", 1.8)))
        ec_tol = f(final.get("targets.ec_tolerance"), f(current.get("targets.ec_tolerance", 0.2)))
        if ec_tol is not None and ec_tol < 0:
            return False, {"field": "targets.ec_tolerance", "message": "Must be >= 0"}
        if ec_tgt is not None and ec_tol is not None:
            if not (0.0 <= ec_tgt - ec_tol) or not ((ec_tgt + ec_tol) <= 4.0):
                return False, {"field": "targets.ec_target", "message": "target±tolerance must be within 0–4"}

    # If we get here, validation passed
    return True, None

def export_all() -> Dict[str, Any]:
    """Return a JSON-safe export of all settings."""
    return get_all_settings()

def import_all(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Import settings from JSON-like dict; validate and upsert. Returns summary."""
    if not isinstance(payload, dict):
        return {"ok": False, "changed": 0, "warnings": ["invalid_payload"]}
    ok, err = validate_partial(payload)
    if not ok:
        # propagate field/message; the API layer will format status code
        return err or {"ok": False, "message": "validation_failed"}
    changed = upsert_settings(payload)
    return {"ok": True, "changed": len(changed), "warnings": []}


def _init_settings_table():
    """Initialize settings table if it doesn't exist"""
    DB_PATH.parent.mkdir(exist_ok=True)
    
    from app.db_pool import get_conn
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    defaults = {
        'system_volume_liters': '25.0',
        'lights_on_time': '20:00',
        'lights_duration_hours': '16'
    }
    for key, default_value in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, default_value))
    conn.commit()

def get_setting_key(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a raw setting value by key (string), or default if missing."""
    _init_settings_table()
    from app.db_pool import get_conn
    conn = get_conn(readonly=True)
    cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    if row and row[0] is not None:
        return str(row[0])
    return default

def set_setting_key(key: str, value: str) -> None:
    """Set a raw setting value by key (string) with reduced busy wait.
    Fast path: short timeout & busy_timeout pragma to avoid long blocking on write contention.
    If database is locked, silently skip (callers treat persistence as best-effort).
    """
    _init_settings_table()
    from app.db_pool import get_conn
    try:
        conn = get_conn()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    except sqlite3.OperationalError:
        return


def _load_settings_from_db() -> Settings:
    """Load settings from database"""
    _init_settings_table()
    
    from app.db_pool import get_conn
    conn = get_conn(readonly=True)
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings_dict = {key: value for key, value in rows}
    return Settings(
        system_volume_liters=float(settings_dict.get('system_volume_liters', '25.0')),
        lights_on_time=settings_dict.get('lights_on_time', '20:00'),
        lights_duration_hours=int(settings_dict.get('lights_duration_hours', '16'))
    )


def get_settings() -> Settings:
    """Get current settings (cached)"""
    global _settings_cache
    
    if _settings_cache is None:
        _settings_cache = _load_settings_from_db()
    
    return _settings_cache


def update_settings(
    system_volume_liters: Optional[float] = None,
    lights_on_time: Optional[str] = None,
    lights_duration_hours: Optional[int] = None
) -> Settings:
    """Update settings in database and refresh cache"""
    global _settings_cache
    
    # Get current settings
    current = get_settings()
    
    # Create new settings with updates
    new_settings = Settings(
        system_volume_liters=system_volume_liters if system_volume_liters is not None else current.system_volume_liters,
        lights_on_time=lights_on_time if lights_on_time is not None else current.lights_on_time,
        lights_duration_hours=lights_duration_hours if lights_duration_hours is not None else current.lights_duration_hours
    )
    
    # Validation happens in __post_init__
    
    # Save to database
    from app.db_pool import get_conn
    conn = get_conn()
    updates = {}
    if system_volume_liters is not None:
        updates['system_volume_liters'] = str(system_volume_liters)
    if lights_on_time is not None:
        updates['lights_on_time'] = lights_on_time
    if lights_duration_hours is not None:
        updates['lights_duration_hours'] = str(lights_duration_hours)
    for key, value in updates.items():
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    
    # Update cache
    _settings_cache = new_settings
    
    return new_settings


def lights_window(today_date: datetime) -> Tuple[datetime, datetime]:
    """
    Calculate lights on/off times for a given date
    Returns (on_datetime, off_datetime) in local timezone (Africa/Johannesburg)
    """
    settings = get_settings()
    
    # Parse time string
    hour, minute = map(int, settings.lights_on_time.split(':'))
    
    # Normalize date to timezone-aware base in SA_TZ
    if today_date.tzinfo is None:
        base = SA_TZ.localize(today_date)
    else:
        base = today_date.astimezone(SA_TZ)

    # Create on time for the given date in SA_TZ
    on_dt = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # Calculate off time
    off_dt = on_dt + timedelta(hours=settings.lights_duration_hours)
    
    return on_dt, off_dt


def get_todays_lights_window() -> Tuple[datetime, datetime]:
    """Get today's lights window in local timezone"""
    now = datetime.now(SA_TZ)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return lights_window(today)
