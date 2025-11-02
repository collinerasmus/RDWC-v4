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
    "targets.ph_low": "5.8",
    "targets.ph_high": "6.2",
    "targets.ec_target": "1.8",
    "targets.ec_tolerance": "0.2",
    "targets.temp_target_c": "20",

    # dosing
    "dosing.pulse_ml_grow": "0",
    "dosing.pulse_ml_micro": "0",
    "dosing.pulse_ml_bloom": "0",
    "dosing.max_ml_hour_": "0",
    "dosing.max_ml_day_": "0",
    "dosing.mix_delay_s": "0",
    # pH Up dosing controls
    "dosing.ph_up_ml_per_sec": "25",
    # Nutrient pump calibration (ml/s)
    "dosing.grow_ml_per_sec": "20",
    "dosing.micro_ml_per_sec": "20",
    "dosing.bloom_ml_per_sec": "20",
    "dosing.ph_up_max_ml_per_day": "50",
    "dosing.ph_up_max_single_ml": "5",
    "dosing.ph_min_interval_s": "300",
    # Observe window after dose (extended for automation stability)
    "dosing.observe_s_after_dose": "600",

    # pH Up automation (production defaults)
    "ph.auto_enabled": "false",
    "dosing.poll_interval_s": "30",
    "dosing.ph_up_step_min_ml": "0.5",
    "dosing.ph_up_step_max_ml": "5.0",
    "dosing.ph_up_safety_factor": "0.6",
    # EC below this baseline holds automation (mS/cm)
    "dosing.ec_baseline_min": "0.2",

    # safety
    "safety.main_pump_min_off_s": "5",
    "safety.chiller_pump_min_off_s": "5",
    "safety.chiller_min_off_s": "300",
    "safety.chiller_min_on_s": "60",
    "safety.estop_persist": "false",
    # allow force-bypass of cooldown/daily cap for testing only
    "safety.allow_force": "false",
    # maintenance override (global test mode)
    "safety.maintenance_override": "false",
    # TEST-ONLY: allow dosing when sensors are stale, but only when maintenance_override is also true
    # Defaults to OFF for production safety
    "safety.allow_stale_on_override": "false",

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
}

def _ensure_table_seed_defaults() -> None:
    """Ensure settings table exists and DEFAULTS are present (without overriding)."""
    _init_settings_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        for key, val in DEFAULTS.items():
            cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, val))
        conn.commit()

def get_all_settings() -> Dict[str, str]:
    """Return flat dict of all settings (string values)."""
    _ensure_table_seed_defaults()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM settings")
        return {k: (v if v is not None else "") for k, v in cur.fetchall()}

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
    _ensure_table_seed_defaults()
    changed: Dict[str, Any] = {}
    with sqlite3.connect(str(DB_PATH)) as conn:
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

    # EC 0.0–4.0 mS/cm
    for k in ("targets.ec_target", "targets.ec_tolerance"):
        if k in final:
            v = f(final[k])
            if v is None or not (0.0 <= v <= 4.0):
                return False, {"field": k, "message": "Must be in 0.0–4.0"}

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
    for k in ("safety.main_pump_min_off_s", "safety.chiller_pump_min_off_s",
              "safety.chiller_min_off_s", "safety.chiller_min_on_s"):
        if k in final:
            v = i(final[k])
            if v is None or not (0 <= v <= 3600):
                return False, {"field": k, "message": "Must be 0–3600"}

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
        if v is None or not (0 <= v <= 3600):
            return False, {"field": "dosing.observe_s_after_dose", "message": "Must be 0–3600"}

    # --- Cross-field checks ---
    ph_lo = f(final.get("targets.ph_low"), f(current.get("targets.ph_low", 5.8)))
    ph_hi = f(final.get("targets.ph_high"), f(current.get("targets.ph_high", 6.2)))
    if ph_lo is not None and ph_hi is not None and not (ph_lo < ph_hi):
        return False, {"field": "targets.ph_low", "message": "Must be < ph_high"}

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
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        
        # Create settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Insert defaults if missing (production defaults)
        defaults = {
            'system_volume_liters': '25.0',
            'lights_on_time': '20:00',
            'lights_duration_hours': '16'
        }
        
        for key, default_value in defaults.items():
            cursor.execute("""
                INSERT OR IGNORE INTO settings (key, value) 
                VALUES (?, ?)
            """, (key, default_value))
        
        conn.commit()

def get_setting_key(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a raw setting value by key (string), or default if missing."""
    _init_settings_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        if row and row[0] is not None:
            return str(row[0])
        return default

def set_setting_key(key: str, value: str) -> None:
    """Set a raw setting value by key (string)."""
    _init_settings_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()


def _load_settings_from_db() -> Settings:
    """Load settings from database"""
    _init_settings_table()
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT key, value FROM settings")
        rows = cursor.fetchall()
        
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
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        
        updates = {}
        if system_volume_liters is not None:
            updates['system_volume_liters'] = str(system_volume_liters)
        if lights_on_time is not None:
            updates['lights_on_time'] = lights_on_time
        if lights_duration_hours is not None:
            updates['lights_duration_hours'] = str(lights_duration_hours)
        
        for key, value in updates.items():
            cursor.execute("""
                INSERT OR REPLACE INTO settings (key, value) 
                VALUES (?, ?)
            """, (key, value))
        
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