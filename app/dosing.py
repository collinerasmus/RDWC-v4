"""
Unified dosing system with safety caps and event logging.
Provides canonical POST /api/dose/{pump} endpoints with centralized guards.
"""
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any
from threading import Lock

# --- DB path -----------------------------------------------------------------
DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

# --- Global mixing lock (shared across pH/EC/nutrients) ----------------------
_dose_lock = Lock()

# --- Schema migration --------------------------------------------------------
def ensure_dose_events_table():
    """Create dose_events table if it doesn't exist (idempotent)."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dose_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                pump TEXT CHECK(pump IN ('grow','micro','bloom','ph_up')) NOT NULL,
                seconds REAL NOT NULL,
                reason TEXT,
                actor TEXT,
                ph_before REAL,
                ph_after REAL,
                ec_before REAL,
                ec_after REAL,
                temp_c REAL,
                blocked_by TEXT,
                controller_state_json TEXT
            )
        """)
        # Add index for recent queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_dose_events_ts 
            ON dose_events(ts DESC)
        """)
        conn.commit()

# Call at module load to ensure table exists
ensure_dose_events_table()

# --- Settings helpers --------------------------------------------------------
def _get_settings_dict() -> Dict[str, str]:
    """Get all settings as string dict."""
    try:
        from app.settings import get_all_settings
        return get_all_settings()
    except Exception:
        return {}

def _s(key: str, default: str = "") -> str:
    """Get setting value or default."""
    sett = _get_settings_dict()
    return sett.get(key, default)

def _f(key: str, default: float = 0.0) -> float:
    """Get setting as float."""
    try:
        return float(_s(key, str(default)))
    except Exception:
        return default

def _i(key: str, default: int = 0) -> int:
    """Get setting as int."""
    try:
        return int(float(_s(key, str(default))))
    except Exception:
        return default

def _b(key: str, default: bool = False) -> bool:
    """Get setting as bool."""
    val = _s(key, "false" if not default else "true").strip().lower()
    return val in ("true", "1", "yes", "on")

# --- Sensor helpers ----------------------------------------------------------
def _get_latest_readings() -> Dict[str, Optional[float]]:
    """Return latest pH, EC, temp_c, and timestamp from readings table."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT ts, ph, ec_ms_cm, temp_c 
                FROM readings 
                ORDER BY ts DESC 
                LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                return {
                    "ts": int(row[0]),
                    "ph": float(row[1]) if row[1] is not None else None,
                    "ec_ms_cm": float(row[2]) if row[2] is not None else None,
                    "temp_c": float(row[3]) if row[3] is not None else None
                }
    except Exception:
        pass
    return {"ts": None, "ph": None, "ec_ms_cm": None, "temp_c": None}

# --- Daily usage tracking ----------------------------------------------------
def _get_pump_usage_today(pump: str) -> float:
    """Return total seconds dosed for this pump today."""
    try:
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_ts = int(start_of_day.timestamp())
        
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COALESCE(SUM(seconds), 0) 
                FROM dose_events 
                WHERE pump = ? AND ts >= ? AND blocked_by IS NULL
            """, (pump, start_ts))
            row = cur.fetchone()
            return float(row[0]) if row else 0.0
    except Exception:
        return 0.0

def _get_last_dose_ts(pump: str) -> Optional[int]:
    """Return unix timestamp of last successful dose for this pump."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT ts FROM dose_events 
                WHERE pump = ? AND blocked_by IS NULL
                ORDER BY ts DESC 
                LIMIT 1
            """, (pump,))
            row = cur.fetchone()
            return int(row[0]) if row else None
    except Exception:
        return None

# --- Safety guard checker ----------------------------------------------------
def check_dosing_guards(pump: str, seconds: float) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Centralized safety guard checker for all manual dosing.
    
    Returns:
        (ok: bool, blocked_by: str|None, caps_info: dict)
    
    ALWAYS-ON Guards (enforced in both Auto and Manual modes):
        - ESTOP / Safe-off / Mixing lock
        - pH guard: pH Up blocked if pH >= high target (hard limit)
        - EC guard: Nutrients blocked if EC >= target + 0.2 (hard limit)
    
    AUTO-ONLY Guards (only enforced when global_auto is enabled):
        - Press cap: seconds <= max_seconds_per_press
        - Daily cap: today_usage + seconds <= max_total_seconds_per_24h
        - Min off window: time since last dose >= min_off_window_sec
        - Sensor stale: age < 60s
    
    Manual mode = unrestricted dosing (except always-on protections)
    """
    # Check if we're in auto mode
    is_auto_mode = False
    try:
        from app.auto_control import is_global_auto_enabled
        is_auto_mode = is_global_auto_enabled()
    except Exception:
        is_auto_mode = True  # Fail-safe: assume auto mode if can't check
    
    # Read caps from settings
    max_press = _f("safety.max_seconds_per_press", 1.5)
    daily_cap = _f("safety.max_total_seconds_per_24h", 120.0)
    min_off = _f("safety.min_off_window_sec", 2.0)
    
    caps_info = {
        "max_press": max_press,
        "daily_cap": daily_cap,
        "min_off": min_off,
        "is_auto_mode": is_auto_mode
    }
    
    # === ALWAYS-ON GUARDS (both Auto and Manual) ===
    
    # E-STOP (always enforced)
    if _b("safety.estop", False):
        return (False, "estop", caps_info)
    
    # Safe-off (always enforced)
    if _b("safety.safe_off_persist", False):
        return (False, "safeoff", caps_info)
    
    # Mix lock (always enforced - prevent concurrent dosing)
    if _dose_lock.locked():
        return (False, "mix_lock", caps_info)
    
    # Get latest sensor readings for hard guards
    readings = _get_latest_readings()
    
    # pH hard guard (always enforced - prevents dangerous pH spikes)
    if pump == "ph_up":
        ph = readings.get("ph")
        if ph is not None:
            ph_high = _f("targets.ph_high", 6.6)
            if ph >= ph_high:
                return (False, "ph_guard", caps_info)
    
    # EC hard guard (always enforced - prevents EC overdose)
    if pump in ["grow", "micro", "bloom"]:
        ec = readings.get("ec_ms_cm")
        if ec is not None:
            ec_target = _f("targets.ec_target", 0.0)
            ec_high = _f("targets.ec_high", 1.2)
            threshold = (ec_target + 0.2) if ec_target > 0 else ec_high
            if ec >= threshold:
                return (False, "ec_guard", caps_info)
    
    # === AUTO-ONLY GUARDS (only when global_auto is enabled) ===
    if is_auto_mode:
        # Press cap
        if seconds > max_press:
            return (False, "press_cap", caps_info)
        
        # Daily cap
        usage = _get_pump_usage_today(pump)
        if usage + seconds > daily_cap:
            return (False, "daily_cap", caps_info)
        
        # Min off window
        last_ts = _get_last_dose_ts(pump)
        if last_ts:
            elapsed = time.time() - last_ts
            if elapsed < min_off:
                return (False, "min_off", caps_info)
        
        # Stale sensor check (60s)
        now_ts = int(time.time())
        if readings["ts"] is None or (now_ts - readings["ts"]) > 60:
            return (False, "stale", caps_info)
    
    return (True, None, caps_info)

# --- DAO helpers -------------------------------------------------------------
def log_dose_event(
    pump: str,
    seconds: float,
    reason: str,
    actor: str,
    ph_before: Optional[float] = None,
    ph_after: Optional[float] = None,
    ec_before: Optional[float] = None,
    ec_after: Optional[float] = None,
    temp_c: Optional[float] = None,
    blocked_by: Optional[str] = None,
    controller_state_json: Optional[str] = None
) -> int:
    """Log a dose event to dose_events table. Returns rowid."""
    ts = int(time.time())
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO dose_events (
                ts, pump, seconds, reason, actor,
                ph_before, ph_after, ec_before, ec_after, temp_c,
                blocked_by, controller_state_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts, pump, seconds, reason, actor,
            ph_before, ph_after, ec_before, ec_after, temp_c,
            blocked_by, controller_state_json
        ))
        conn.commit()
        return cur.lastrowid

def get_recent_dose_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent dose events."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    id, ts, pump, seconds, reason, actor,
                    ph_before, ph_after, ec_before, ec_after, temp_c,
                    blocked_by, controller_state_json
                FROM dose_events
                ORDER BY ts DESC
                LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "ts": r[1],
                    "ts_utc": datetime.fromtimestamp(r[1], tz=timezone.utc).isoformat(),
                    "pump": r[2],
                    "seconds": r[3],
                    "reason": r[4],
                    "actor": r[5],
                    "ph_before": r[6],
                    "ph_after": r[7],
                    "ec_before": r[8],
                    "ec_after": r[9],
                    "temp_c": r[10],
                    "blocked_by": r[11],
                    "controller_state_json": r[12]
                }
                for r in rows
            ]
    except Exception:
        return []

def get_doses_since(ts_start: int) -> List[Dict[str, Any]]:
    """Get dose events since given timestamp."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    id, ts, pump, seconds, reason, actor,
                    ph_before, ph_after, ec_before, ec_after, temp_c,
                    blocked_by
                FROM dose_events
                WHERE ts >= ?
                ORDER BY ts ASC
            """, (ts_start,))
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "ts": r[1],
                    "pump": r[2],
                    "seconds": r[3],
                    "reason": r[4],
                    "actor": r[5],
                    "ph_before": r[6],
                    "ph_after": r[7],
                    "ec_before": r[8],
                    "ec_after": r[9],
                    "temp_c": r[10],
                    "blocked_by": r[11]
                }
                for r in rows
            ]
    except Exception:
        return []

# --- Relay actuation helpers -------------------------------------------------
def actuate_pump(pump: str, seconds: float) -> Tuple[bool, str]:
    """
    Actuate a pump for given seconds using the global dose lock.
    Returns (success, error_msg).
    """
    try:
        from app.relays_core import (
            set_dosing_grow, set_dosing_micro, set_dosing_bloom, set_dosing_ph_up
        )
        
        with _dose_lock:
            if pump == "grow":
                set_dosing_grow(True, reason="dose_manual", force=True)
                time.sleep(seconds)
                set_dosing_grow(False, reason="dose_manual", force=True)
            elif pump == "micro":
                set_dosing_micro(True, reason="dose_manual", force=True)
                time.sleep(seconds)
                set_dosing_micro(False, reason="dose_manual", force=True)
            elif pump == "bloom":
                set_dosing_bloom(True, reason="dose_manual", force=True)
                time.sleep(seconds)
                set_dosing_bloom(False, reason="dose_manual", force=True)
            elif pump == "ph_up":
                set_dosing_ph_up(True, reason="dose_manual", force=True)
                time.sleep(seconds)
                set_dosing_ph_up(False, reason="dose_manual", force=True)
            else:
                return (False, f"Unknown pump: {pump}")
        
        return (True, "")
    except Exception as e:
        # Ensure pump is off on error
        try:
            from app.relays_core import (
                set_dosing_grow, set_dosing_micro, set_dosing_bloom, set_dosing_ph_up
            )
            if pump == "grow":
                set_dosing_grow(False, reason="dose_error", force=True)
            elif pump == "micro":
                set_dosing_micro(False, reason="dose_error", force=True)
            elif pump == "bloom":
                set_dosing_bloom(False, reason="dose_error", force=True)
            elif pump == "ph_up":
                set_dosing_ph_up(False, reason="dose_error", force=True)
        except Exception:
            pass
        return (False, str(e))
