"""
EC Control API v2

Endpoints:
- GET /api/ec/status
- POST /api/ec/dose
- POST /api/ec/auto
- POST /api/ec/auto/learn/reset
- GET /api/ec/auto/debug
- GET /api/ec/control/preview

Manual dosing with guards (G/M/B pumps in sequential mix) and unified dose_events logging.
Automation: background controller that raises EC when it falls below the target band.
It learns dose effect from prior dose logs (ml per 1.0 mS/cm) and respects all guards.

V2 Changes:
- Single source of truth: all EC dose activity logs to dose_events only
- Centralized guards: uses dosing.check_dosing_guards for EC dosing
- Schedule-driven ratios: G/M/B split computed from nutrient_schedule
- Dry-run default: dosing.dry_run_ec=true means no pump actuation, shadow events logged
- Settings canonicalization: dosing.ec_* and targets.ec_* with legacy ec.* fallback
"""
from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone, timedelta
import time
import sqlite3
import threading
import json
from pathlib import Path

router = APIRouter()

DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

# --- Automation state --------------------------------------------------------
_auto_thread: Optional[threading.Thread] = None
_auto_stop_evt: Optional[threading.Event] = None
_auto_lock = threading.Lock()
_auto_last_holding_reason: Optional[str] = None
_auto_enabled_at: Optional[float] = None
_auto_last_block: Optional[str] = None
_auto_last_block_count: int = 0
_auto_last_decision: Dict[str, Any] = {}  # For debug endpoint

# Learning estimator (ml per 1.0 mS/cm)
_learned_ml_per_mScm: Optional[float] = None

# Default ml per 1.0 mS/cm when no learned value is available
# Based on typical 3-part nutrient dosing: ~30ml per 0.1 mS/cm = 300ml per 1.0 mS/cm
DEFAULT_ML_PER_MSCM = 300.0

# Use global dose lock from dosing module for consistency
def _get_dose_lock():
    """Get the global dose lock from dosing module."""
    try:
        from app.dosing import _dose_lock
        return _dose_lock
    except ImportError:
        # Fallback to local lock if dosing module not available
        return threading.Lock()

_local_dose_lock = threading.Lock()  # Fallback

# --- DB helpers --------------------------------------------------------------
def _ensure_tables() -> None:
    """Ensure legacy ec_dose_log table exists (for read compatibility)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ec_dose_log(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts_utc TEXT NOT NULL,
              action TEXT NOT NULL,
              volume_ml REAL,
              mix_ratio TEXT,
              duration_ms INTEGER,
              pre_ec REAL,
              post_ec REAL,
              result TEXT NOT NULL,
              reason TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ec_dose_log_ts ON ec_dose_log(ts_utc)")
        conn.commit()

def _ensure_dose_events_table() -> None:
    """Ensure dose_events table exists for unified logging.
    
    Always creates table locally using current DB_PATH (for test isolation).
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dose_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                pump TEXT NOT NULL,
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dose_events_ts ON dose_events(ts DESC)")
        conn.commit()

def _log_dose_event(
    pump: str,
    seconds: float,
    reason: str,
    actor: str,
    ec_before: Optional[float] = None,
    ec_after: Optional[float] = None,
    blocked_by: Optional[str] = None,
    controller_state_json: Optional[str] = None
) -> int:
    """Log a dose event to dose_events table. Returns rowid."""
    _ensure_dose_events_table()
    ts = int(time.time())
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO dose_events (
                ts, pump, seconds, reason, actor,
                ec_before, ec_after, blocked_by, controller_state_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts, pump, seconds, reason, actor,
            ec_before, ec_after, blocked_by, controller_state_json
        ))
        conn.commit()
        return cur.lastrowid or 0

def _log_row(row: Dict[str, Any]) -> int:
    """DEPRECATED: Log to legacy ec_dose_log table. Use _log_dose_event for new code."""
    _ensure_tables()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ec_dose_log(ts_utc, action, volume_ml, mix_ratio, duration_ms, pre_ec, post_ec, result, reason)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                row.get("ts_utc"), row.get("action","dose"), row.get("volume_ml"),
                row.get("mix_ratio",""), row.get("duration_ms"), row.get("pre_ec"), row.get("post_ec"),
                row.get("result","ok"), row.get("reason")
            )
        )
        rowid = cur.lastrowid or 0
        conn.commit()
        return int(rowid)

def _update_post_ec(rowid: int, post_ec: Optional[float]) -> None:
    """Update post_ec in dose_events table."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("UPDATE dose_events SET ec_after=? WHERE id=?", (post_ec, rowid))
        conn.commit()

def _recent_doses(limit: int = 5) -> List[Dict[str, Any]]:
    """Get recent EC dose events from unified dose_events table.
    Returns format compatible with legacy ec_dose_log for backward compatibility.
    """
    _ensure_dose_events_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        # Read from dose_events for EC pumps (grow, micro, bloom)
        cur.execute(
            """
            SELECT id, ts, pump, seconds, reason, actor, ec_before, ec_after, blocked_by, controller_state_json
            FROM dose_events
            WHERE pump IN ('grow', 'micro', 'bloom')
            ORDER BY ts DESC
            LIMIT ?
            """,
            (int(limit),)
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        ts_unix = r[1]
        ts_utc = datetime.fromtimestamp(ts_unix, tz=timezone.utc).isoformat() if ts_unix else None
        pump = r[2]
        seconds = r[3]
        # Compute volume_ml from seconds using pump rate
        volume_ml = _compute_volume_ml(pump, seconds) if seconds else None
        out.append({
            "id": r[0],
            "ts_utc": ts_utc,
            "action": "dose",
            "volume_ml": volume_ml,
            "mix_ratio": f"{pump}:{seconds}s" if pump and seconds else "",
            "duration_ms": int(seconds * 1000) if seconds else 0,
            "pre_ec": r[6],
            "post_ec": r[7],
            "result": "blocked" if r[8] else "ok",
            "reason": r[4] or r[5]  # reason or actor
        })
    return out

def _compute_volume_ml(pump: str, seconds: float) -> Optional[float]:
    """Compute volume in ml from pump run time using pump rate from settings."""
    if not pump or seconds is None or seconds < 0:
        return None
    rate_key = f"dosing.{pump}_ml_per_sec"
    rate = _f(rate_key, 20.0)  # Default 20 ml/s for nutrient pumps
    return round(seconds * rate, 2)

def _dose_events_range(start: Optional[str] = None, end: Optional[str] = None, hours: Optional[int] = None, limit: int = 2000) -> List[Dict[str, Any]]:
    """Return dose events within a time range ordered ascending by ts.
    Reads from unified dose_events table.
    Each row: {ts, seconds, volume_ml, detail, ec_before, ec_after, guard_triggered}
    """
    _ensure_dose_events_table()
    # Determine time window as unix timestamps
    if start and end:
        try:
            start_ts = int(datetime.fromisoformat(start.replace('Z', '+00:00')).timestamp())
            end_ts = int(datetime.fromisoformat(end.replace('Z', '+00:00')).timestamp())
        except Exception:
            start_ts = int(time.time()) - 86400
            end_ts = int(time.time())
    elif hours:
        end_ts = int(time.time())
        start_ts = end_ts - (int(hours) * 3600)
    else:
        # Default last 24h
        end_ts = int(time.time())
        start_ts = end_ts - 86400
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts, pump, seconds, reason, actor, ec_before, ec_after, blocked_by
            FROM dose_events
            WHERE pump IN ('grow', 'micro', 'bloom') AND ts BETWEEN ? AND ?
            ORDER BY ts ASC
            LIMIT ?
            """,
            (start_ts, end_ts, int(limit))
        )
        rows = cur.fetchall()
    
    out: List[Dict[str, Any]] = []
    for r in rows:
        ts_unix = r[0]
        ts_iso = datetime.fromtimestamp(ts_unix, tz=timezone.utc).isoformat() if ts_unix else None
        pump = r[1]
        seconds = r[2]
        volume_ml = _compute_volume_ml(pump, seconds) if seconds else None
        out.append({
            "ts": ts_iso,
            "pump": pump,  # Added: pump name for chart markers
            "seconds": float(seconds) if seconds is not None else None,
            "volume_ml": volume_ml,
            "detail": r[3] or r[4] or pump,  # reason, actor, or pump name
            "ec_before": float(r[5]) if r[5] is not None else None,
            "ec_after": float(r[6]) if r[6] is not None else None,
            "guard_triggered": r[7] is not None  # blocked_by indicates guard was triggered
        })
    return out

def _dose_daily_range(start: Optional[str] = None, end: Optional[str] = None, days: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return daily aggregates of volume_ml for successful doses.
    Reads from unified dose_events table.
    """
    _ensure_dose_events_table()
    # Determine time window as unix timestamps
    if start and end:
        try:
            start_ts = int(datetime.fromisoformat(start.replace('Z', '+00:00')).timestamp())
            end_ts = int(datetime.fromisoformat(end.replace('Z', '+00:00')).timestamp())
        except Exception:
            d = int(days) if days else 30
            end_ts = int(time.time())
            start_ts = end_ts - (d * 86400)
    else:
        d = int(days) if days else 30
        end_ts = int(time.time())
        start_ts = end_ts - (d * 86400)
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        # Get all EC pump doses in range, grouped by day
        cur.execute(
            """
            SELECT date(ts, 'unixepoch') AS day, pump, SUM(seconds)
            FROM dose_events
            WHERE pump IN ('grow', 'micro', 'bloom') 
              AND blocked_by IS NULL 
              AND ts BETWEEN ? AND ?
            GROUP BY day, pump
            ORDER BY day ASC
            """,
            (start_ts, end_ts)
        )
        rows = cur.fetchall()
    
    # Aggregate by day, computing ml from seconds
    daily_totals: Dict[str, float] = {}
    for day, pump, total_seconds in rows:
        if day not in daily_totals:
            daily_totals[day] = 0.0
        if total_seconds:
            ml = _compute_volume_ml(pump, total_seconds) or 0.0
            daily_totals[day] += ml
    
    return [{"day": day, "total_ml": round(ml, 2)} for day, ml in sorted(daily_totals.items())]

def _today_total_ml(now_dt: datetime) -> float:
    """Get total EC dose volume (ml) for today from dose_events."""
    _ensure_dose_events_table()
    try:
        from app.settings import SA_TZ
    except Exception:
        SA_TZ = timezone.utc
    local_now = now_dt.astimezone(SA_TZ)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ts = int(start_local.astimezone(timezone.utc).timestamp())
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT pump, SUM(seconds)
            FROM dose_events
            WHERE pump IN ('grow', 'micro', 'bloom') 
              AND blocked_by IS NULL 
              AND ts >= ?
            GROUP BY pump
            """,
            (start_ts,)
        )
        rows = cur.fetchall()
    
    total_ml = 0.0
    for pump, total_seconds in rows:
        if total_seconds:
            ml = _compute_volume_ml(pump, total_seconds) or 0.0
            total_ml += ml
    return round(total_ml, 2)

def _last_ok_ts() -> Optional[datetime]:
    """Get timestamp of last successful EC dose from dose_events."""
    _ensure_dose_events_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts FROM dose_events 
            WHERE pump IN ('grow', 'micro', 'bloom') AND blocked_by IS NULL 
            ORDER BY ts DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        try:
            return datetime.fromtimestamp(row[0], tz=timezone.utc)
        except Exception:
            return None

# --- Sensors/Settings helpers ------------------------------------------------
def _get_latest_ec() -> Tuple[Optional[float], Optional[int]]:
    """Return latest EC (mS/cm) and its unix ts from readings table."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT ts, ec_ms_cm FROM readings ORDER BY ts DESC LIMIT 1")
            row = cur.fetchone()
            if row and row[1] is not None:
                return (float(row[1]), int(row[0]))
    except Exception:
        pass
    return (None, None)

def _get_latest_ph() -> Tuple[Optional[float], Optional[int]]:
    """Return latest pH and its unix ts from readings table."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT ts, ph FROM readings ORDER BY ts DESC LIMIT 1")
            row = cur.fetchone()
            if row and row[1] is not None:
                return (float(row[1]), int(row[0]))
    except Exception:
        pass
    return (None, None)

def _get_latest_temp() -> Tuple[Optional[float], Optional[int]]:
    """Return latest temp_c and its unix ts from readings table."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT ts, temp_c FROM readings ORDER BY ts DESC LIMIT 1")
            row = cur.fetchone()
            if row and row[1] is not None:
                return (float(row[1]), int(row[0]))
    except Exception:
        pass
    return (None, None)

def _get_settings_dict() -> Dict[str, str]:
    """Get all settings as string dict."""
    try:
        from app.settings import get_all_settings
        return get_all_settings()
    except Exception:
        return {}

def _s(key: str, default: str = "") -> str:
    """Helper to get setting value or default."""
    sett = _get_settings_dict()
    return sett.get(key, default)

def _f(key: str, default: float = 0.0) -> float:
    """Helper to get setting as float."""
    try:
        return float(_s(key, str(default)))
    except Exception:
        return default

def _i(key: str, default: int = 0) -> int:
    """Helper to get setting as int."""
    try:
        return int(float(_s(key, str(default))))
    except Exception:
        return default

def _b(key: str, default: bool = False) -> bool:
    """Helper to get setting as bool."""
    val = _s(key, "false" if not default else "true").strip().lower()
    return val in ("true", "1", "yes", "on")

def _get_setting_with_fallback(primary: str, fallback: str, default: float) -> float:
    """Get setting with fallback to legacy key."""
    val = _s(primary, "")
    if val:
        try:
            return float(val)
        except Exception:
            pass
    return _f(fallback, default)

def _is_dry_run_ec() -> bool:
    """Check if EC dry-run mode is enabled (default: false - pumps run water only)."""
    return _b("dosing.dry_run_ec", False)

# --- Schedule Ratio Helpers --------------------------------------------------
def _get_current_schedule_week() -> Optional[int]:
    """Get current grow week from settings and schedule.
    
    Calculates the week number (1-12) based on grow start date from settings,
    handling timezone conversion to UTC. Returns None if no start date is configured.
    
    Returns:
        week number (1-12) or None if no start date set
    """
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key = 'general.grow_start_date'")
            row = cur.fetchone()
            if not row or not row[0]:
                return None
            
            # Parse start date with timezone handling
            try:
                from app.settings import SA_TZ
                start_date = datetime.strptime(row[0], "%Y-%m-%d")
                try:
                    start_date = SA_TZ.localize(start_date)
                except AttributeError:
                    start_date = start_date.replace(tzinfo=timezone.utc)
            except (ValueError, ImportError) as e:
                # Invalid date format or timezone library import failed
                return None
            
            now = datetime.now(timezone.utc)
            delta = now - start_date.astimezone(timezone.utc)
            week = max(1, min(12, (delta.days // 7) + 1))
            return week
    except (sqlite3.Error, ValueError) as e:
        # Database error or date parsing error
        return None

def _get_schedule_ec_target() -> Optional[float]:
    """Get EC target from nutrient schedule for current week.
    
    Depends on _get_current_schedule_week() to determine the current week.
    Returns None if no valid week is available, no schedule exists for that week,
    or the schedule entry has no EC target set.
    
    Returns:
        ec_target (mS/cm) or None if no schedule/week available
    """
    try:
        week = _get_current_schedule_week()
        if week is None:
            return None
        
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT ec_target FROM nutrient_schedule WHERE week = ?",
                (week,)
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                return float(row[0])
    except (sqlite3.Error, ValueError, TypeError) as e:
        # Database error, invalid float conversion, or null value
        pass
    return None

def _get_schedule_ratios() -> Tuple[Dict[str, float], str]:
    """Get G/M/B ratios from nutrient schedule for current week.
    
    Returns:
        (ratios: {grow, micro, bloom}, source: str)
        where source is 'schedule', 'custom', or 'equal_split'
    """
    try:
        week = _get_current_schedule_week()
        if week is None:
            return ({"grow": 1/3, "micro": 1/3, "bloom": 1/3}, "equal_split:no_start_date")
        
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            # Get schedule for this week
            cur.execute(
                """
                SELECT grow_ml10, micro_ml10, bloom_ml10 
                FROM nutrient_schedule 
                WHERE week = ?
                """,
                (week,)
            )
            sched_row = cur.fetchone()
            if not sched_row:
                return ({"grow": 1/3, "micro": 1/3, "bloom": 1/3}, f"equal_split:no_schedule_week_{week}")
            
            grow_ml10, micro_ml10, bloom_ml10 = sched_row
            total = (grow_ml10 or 0) + (micro_ml10 or 0) + (bloom_ml10 or 0)
            
            if total <= 0:
                # Flush week or zero nutrients
                return ({"grow": 0, "micro": 0, "bloom": 0}, f"schedule:flush_week_{week}")
            
            return ({
                "grow": (grow_ml10 or 0) / total,
                "micro": (micro_ml10 or 0) / total,
                "bloom": (bloom_ml10 or 0) / total
            }, f"schedule:week_{week}")
    except Exception as e:
        return ({"grow": 1/3, "micro": 1/3, "bloom": 1/3}, f"equal_split:error_{str(e)[:50]}")

def _split_ml_by_ratio(total_ml: float, ratios: Dict[str, float]) -> Dict[str, float]:
    """Split total ml across pumps by ratio."""
    return {
        "grow": round(total_ml * ratios.get("grow", 1/3), 2),
        "micro": round(total_ml * ratios.get("micro", 1/3), 2),
        "bloom": round(total_ml * ratios.get("bloom", 1/3), 2)
    }

# --- GPIO helpers ------------------------------------------------------------
def _actuate_mix(grow_ml: float, micro_ml: float, bloom_ml: float) -> Tuple[str, int]:
    """Actuate G→M→B in sequence with delay. Returns (result, duration_ms)."""
    from app.relays_core import set_dosing_grow, set_dosing_micro, set_dosing_bloom
    
    # Get pump rates
    grow_rate = _f("dosing.grow_ml_per_sec", 25.0)
    micro_rate = _f("dosing.micro_ml_per_sec", 25.0)
    bloom_rate = _f("dosing.bloom_ml_per_sec", 25.0)
    mix_delay = _f("dosing.mix_delay_s", 2.0)
    
    total_ms = 0
    
    try:
        # Grow
        if grow_ml > 0:
            grow_ms = int(1000.0 * (grow_ml / max(0.0001, grow_rate)))
            set_dosing_grow(True, reason="ec_dose", force=True)
            time.sleep(grow_ms / 1000.0)
            set_dosing_grow(False, reason="ec_dose", force=True)
            total_ms += grow_ms
        
        # Delay
        if micro_ml > 0 or bloom_ml > 0:
            time.sleep(mix_delay)
            total_ms += int(mix_delay * 1000)
        
        # Micro
        if micro_ml > 0:
            micro_ms = int(1000.0 * (micro_ml / max(0.0001, micro_rate)))
            set_dosing_micro(True, reason="ec_dose", force=True)
            time.sleep(micro_ms / 1000.0)
            set_dosing_micro(False, reason="ec_dose", force=True)
            total_ms += micro_ms
        
        # Delay
        if bloom_ml > 0:
            time.sleep(mix_delay)
            total_ms += int(mix_delay * 1000)
        
        # Bloom
        if bloom_ml > 0:
            bloom_ms = int(1000.0 * (bloom_ml / max(0.0001, bloom_rate)))
            set_dosing_bloom(True, reason="ec_dose", force=True)
            time.sleep(bloom_ms / 1000.0)
            set_dosing_bloom(False, reason="ec_dose", force=True)
            total_ms += bloom_ms
        
        return ("ok", total_ms)
    except Exception as e:
        # Ensure all pumps are off
        try:
            set_dosing_grow(False, reason="ec_dose_error", force=True)
            set_dosing_micro(False, reason="ec_dose_error", force=True)
            set_dosing_bloom(False, reason="ec_dose_error", force=True)
        except Exception:
            pass
        return (f"error: {e}", total_ms)

# --- Guards ------------------------------------------------------------------
def _check_guards(pump: str = "grow", seconds: float = 0.0) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """Check guards using centralized dosing.check_dosing_guards.
    
    Returns (ok, blocked_by, caps_info).
    """
    try:
        from app.dosing import check_dosing_guards
        return check_dosing_guards(pump, seconds)
    except ImportError:
        # Fallback to basic checks if dosing module not available
        pass
    
    # Fallback implementation
    caps_info: Dict[str, Any] = {}
    
    # E-STOP (always enforced)
    if _b("safety.estop", False):
        return (False, "estop", caps_info)
    
    # Safe-off (always enforced)
    if _b("safety.safe_off_persist", False):
        return (False, "safeoff", caps_info)
    
    # Reservoir (always enforced)
    res_l = _f("general.reservoir_liters", 25.0)
    if res_l <= 0:
        return (False, "reservoir", caps_info)
    
    # Dose lock (always enforced - prevent concurrent dosing)
    dose_lock = _get_dose_lock()
    if dose_lock.locked():
        return (False, "mix_lock", caps_info)
    
    return (True, None, caps_info)

def _check_ec_high_guard() -> Tuple[bool, Optional[str]]:
    """Check if EC is already above target threshold.
    
    Returns (ok, reason). If not ok, reason is 'ec_high_guard'.
    This is a HARD guard that blocks dosing when EC is already high.
    """
    ec_val, _ = _get_latest_ec()
    if ec_val is None:
        return (True, None)  # No reading, allow dosing
    
    # Get threshold: prioritize schedule EC target
    schedule_ec_target = _get_schedule_ec_target()
    ec_tol = _f("targets.ec_tolerance", 0.2)
    
    if schedule_ec_target is not None:
        threshold = schedule_ec_target + ec_tol
    else:
        # Fallback to settings
        ec_tgt = _f("targets.ec_target", 0.0)
        ec_hi = _f("targets.ec_high", 1.2)
        threshold = (ec_tgt + ec_tol) if ec_tgt > 0 else ec_hi
    
    if threshold > 0 and ec_val >= threshold:
        return (False, f"ec_high_guard ({ec_val:.2f} >= {threshold:.2f})")
    
    return (True, None)

def _check_interval_guard(now_dt: datetime) -> Tuple[bool, Optional[str]]:
    """Check min interval since last dose. Returns (ok, reason). Default 15min for 2× HRT.
    
    AUTO-ONLY: This guard is only enforced when global_auto is enabled.
    In manual mode, operators can dose freely without interval restrictions.
    """
    # Check if we're in auto mode
    is_auto_mode = False
    try:
        from app.auto_control import is_global_auto_enabled
        is_auto_mode = is_global_auto_enabled()
    except Exception:
        is_auto_mode = True  # Fail-safe: assume auto mode if can't check
    
    # Only enforce in auto mode
    if not is_auto_mode:
        return (True, None)
    
    min_int = _i("dosing.ec_min_interval_s", 900)
    last_ts = _last_ok_ts()
    if last_ts:
        elapsed = (now_dt - last_ts).total_seconds()
        if elapsed < min_int:
            return (False, f"interval ({int(min_int - elapsed)}s)")
    return (True, None)

def _check_daily_cap(now_dt: datetime) -> Tuple[bool, Optional[str]]:
    """Check daily cap. Returns (ok, reason).
    
    AUTO-ONLY: This guard is only enforced when global_auto is enabled.
    In manual mode, operators can dose freely without daily cap restrictions.
    """
    # Check if we're in auto mode
    is_auto_mode = False
    try:
        from app.auto_control import is_global_auto_enabled
        is_auto_mode = is_global_auto_enabled()
    except Exception:
        is_auto_mode = True  # Fail-safe: assume auto mode if can't check
    
    # Only enforce in auto mode
    if not is_auto_mode:
        return (True, None)
    
    cap = _f("dosing.ec_max_ml_day", 0)
    if cap <= 0:
        return (True, None)
    used = _today_total_ml(now_dt)
    if used >= cap:
        return (False, f"daily_cap ({used:.1f}/{cap:.1f}ml)")
    return (True, None)

# --- Manual dose endpoint ----------------------------------------------------
@router.post("/api/ec/dose")
def dose_ec(body: dict = Body(...)):
    """Manual EC dose - supports both pump+seconds and ml+mix_ratio modes.
    
    V2 Changes:
    - Dry-run mode: when dosing.dry_run_ec=true (default), logs to dose_events 
      with actor="dry-run" but does NOT actuate relays.
    - Unified logging: all doses logged to dose_events only (not ec_dose_log)
    - Schedule ratios: when mix_ratio="schedule", uses nutrient_schedule ratios
    - Centralized guards: uses check_dosing_guards for all pumps
    """
    dry_run = _is_dry_run_ec()
    ec_before, _ = _get_latest_ec()
    now_dt = datetime.now(timezone.utc)
    
    # New spec: pump+seconds mode
    if "pump" in body and "seconds" in body:
        pump = body.get("pump", "").lower()
        seconds = float(body.get("seconds", 0))
        reason = body.get("reason", "manual")
        
        # Validate pump
        if pump not in ["grow", "micro", "bloom"]:
            return JSONResponse(status_code=400, content={"error": "pump must be grow|micro|bloom"})
        
        # Check enabled or global maintenance override
        enabled = _b("ec.enabled", False)
        try:
            from app.settings import get_all_settings
            override = (get_all_settings().get("safety.maintenance_override","false").lower() == "true")
        except Exception:
            override = False
        if not enabled and not override:
            return JSONResponse(status_code=409, content={"error": "EC control disabled (enable ec.enabled or safety.maintenance_override)"})
        
        # Clamp seconds
        max_sec = 10.0 if override else 5.0
        if seconds < 0.1 or seconds > max_sec:
            return JSONResponse(status_code=400, content={"error": f"seconds must be 0.1–{max_sec}"})
        
        # Check guards using centralized function
        ok, blocked_by, caps_info = _check_guards(pump, seconds)
        if not ok:
            # Log blocked event to dose_events
            controller_state = json.dumps({"blocked_by": blocked_by, "caps": caps_info})
            _log_dose_event(pump, seconds, reason, "blocked", ec_before=ec_before, blocked_by=blocked_by, controller_state_json=controller_state)
            return JSONResponse(status_code=409, content={"error": f"blocked by {blocked_by}", "blocked_by": blocked_by})
        
        # Check EC high guard (always enforced)
        ok_ec, ec_guard_reason = _check_ec_high_guard()
        if not ok_ec:
            controller_state = json.dumps({"blocked_by": "ec_high_guard", "ec_before": ec_before})
            _log_dose_event(pump, seconds, reason, "blocked", ec_before=ec_before, blocked_by="ec_high_guard", controller_state_json=controller_state)
            return JSONResponse(status_code=409, content={"error": ec_guard_reason, "blocked_by": "ec_high_guard"})
        
        # Compute volume
        ml = _compute_volume_ml(pump, seconds) or 0.0
        
        # Check interval guard
        if not override:
            ok_int, int_reason = _check_interval_guard(now_dt)
            if not ok_int:
                controller_state = json.dumps({"blocked_by": int_reason, "ec_before": ec_before})
                _log_dose_event(pump, seconds, reason, "blocked", ec_before=ec_before, blocked_by=int_reason, controller_state_json=controller_state)
                return JSONResponse(status_code=409, content={"error": f"min interval not met", "blocked_by": int_reason})
        
        # Check daily cap
        if not override:
            ok_cap, cap_reason = _check_daily_cap(now_dt)
            if not ok_cap:
                controller_state = json.dumps({"blocked_by": cap_reason, "ec_before": ec_before})
                _log_dose_event(pump, seconds, reason, "blocked", ec_before=ec_before, blocked_by=cap_reason, controller_state_json=controller_state)
                return JSONResponse(status_code=409, content={"error": f"daily cap reached", "blocked_by": cap_reason})
        
        # Dry-run mode: log shadow event without actuation
        if dry_run:
            controller_state = json.dumps({
                "mode": "dry-run",
                "planned_ml": ml,
                "planned_seconds": seconds,
                "ec_before": ec_before,
                "would_actuate": True
            })
            rowid = _log_dose_event(pump, seconds, reason, "dry-run", ec_before=ec_before, controller_state_json=controller_state)
            return {
                "ok": True,
                "dry_run": True,
                "pump": pump,
                "seconds": seconds,
                "ml": ml,
                "ec_before": ec_before,
                "rowid": rowid,
                "ts": now_dt.isoformat(),
                "message": "Dry-run mode: no pump actuation. Set dosing.dry_run_ec=false to enable."
            }
        
        # Actual actuation
        dose_lock = _get_dose_lock()
        acquired = dose_lock.acquire(blocking=False)
        if not acquired:
            return JSONResponse(status_code=409, content={"error": "another pump is active", "blocked_by": "mix_lock"})
        
        try:
            from app.relays_core import set_dosing_grow, set_dosing_micro, set_dosing_bloom
            
            if pump == "grow":
                set_dosing_grow(True, reason=f"ec_dose_{reason}", force=True)
                time.sleep(seconds)
                set_dosing_grow(False, reason=f"ec_dose_{reason}", force=True)
            elif pump == "micro":
                set_dosing_micro(True, reason=f"ec_dose_{reason}", force=True)
                time.sleep(seconds)
                set_dosing_micro(False, reason=f"ec_dose_{reason}", force=True)
            elif pump == "bloom":
                set_dosing_bloom(True, reason=f"ec_dose_{reason}", force=True)
                time.sleep(seconds)
                set_dosing_bloom(False, reason=f"ec_dose_{reason}", force=True)
        except Exception as e:
            # Ensure pumps are off
            try:
                set_dosing_grow(False, reason="ec_dose_error", force=True)
                set_dosing_micro(False, reason="ec_dose_error", force=True)
                set_dosing_bloom(False, reason="ec_dose_error", force=True)
            except Exception:
                pass
            # Log error but don't expose internal details to client
            import logging
            logging.getLogger(__name__).error(f"EC dose error for pump {pump}: {e}")
            return JSONResponse(status_code=500, content={"error": "Pump actuation failed"})
        finally:
            dose_lock.release()
        
        # Post-read EC (wait 5s for mixing)
        time.sleep(5)
        ec_after, _ = _get_latest_ec()
        
        # Log to dose_events (unified table)
        controller_state = json.dumps({
            "mode": "live",
            "planned_ml": ml,
            "ec_before": ec_before,
            "ec_after": ec_after
        })
        rowid = _log_dose_event(pump, seconds, reason, "manual", ec_before=ec_before, ec_after=ec_after, controller_state_json=controller_state)
        
        return {
            "ok": True,
            "pump": pump,
            "seconds": seconds,
            "ml": ml,
            "ec_before": ec_before,
            "ec_after": ec_after,
            "rowid": rowid,
            "ts": now_dt.isoformat()
        }
    
    # Legacy mode: ml+mix_ratio
    ml = body.get("ml", 0)
    mix_ratio_mode = body.get("mix_ratio", "schedule")  # schedule | custom
    custom = body.get("custom", {})
    reason = body.get("reason", "manual")
    
    # Validate
    if ml <= 0 or ml > 500:
        return JSONResponse(status_code=400, content={"error": "ml must be 0.1–500"})
    
    # Check EC high guard (always enforced)
    ok_ec, ec_guard_reason = _check_ec_high_guard()
    if not ok_ec:
        controller_state = json.dumps({"blocked_by": "ec_high_guard", "ec_before": ec_before})
        # Log blocked event for each pump type (we don't know which yet)
        _log_dose_event("grow", 0, reason, "blocked", ec_before=ec_before, blocked_by="ec_high_guard", controller_state_json=controller_state)
        return JSONResponse(status_code=409, content={"error": ec_guard_reason, "blocked_by": "ec_high_guard"})
    
    # Check guards using centralized function (use 'grow' as representative pump)
    ok, blocked_by, caps_info = _check_guards("grow", 1.0)
    if not ok:
        controller_state = json.dumps({"blocked_by": blocked_by, "caps": caps_info})
        _log_dose_event("grow", 0, reason, "blocked", ec_before=ec_before, blocked_by=blocked_by, controller_state_json=controller_state)
        return JSONResponse(status_code=409, content={"error": f"blocked by {blocked_by}", "blocked_by": blocked_by})
    
    override = _b("safety.maintenance_override", False)
    
    ok_int, int_guard = _check_interval_guard(now_dt)
    if not ok_int and not override:
        controller_state = json.dumps({"blocked_by": int_guard})
        _log_dose_event("grow", 0, reason, "blocked", ec_before=ec_before, blocked_by=int_guard, controller_state_json=controller_state)
        return JSONResponse(status_code=409, content={"error": f"blocked by {int_guard}", "blocked_by": int_guard})
    
    ok_cap, cap_guard = _check_daily_cap(now_dt)
    if not ok_cap and not override:
        controller_state = json.dumps({"blocked_by": cap_guard})
        _log_dose_event("grow", 0, reason, "blocked", ec_before=ec_before, blocked_by=cap_guard, controller_state_json=controller_state)
        return JSONResponse(status_code=409, content={"error": f"blocked by {cap_guard}", "blocked_by": cap_guard})
    
    # Split by ratio
    ratio_source = "unknown"
    if mix_ratio_mode == "custom":
        g = float(custom.get("grow", 0))
        m = float(custom.get("micro", 0))
        b = float(custom.get("bloom", 0))
        total_ratio = g + m + b
        if total_ratio == 0:
            return JSONResponse(status_code=400, content={"error": "custom ratio sums to zero"})
        ratios = {"grow": g / total_ratio, "micro": m / total_ratio, "bloom": b / total_ratio}
        ratio_source = "custom"
    else:
        # Get schedule ratios from nutrient_schedule
        ratios, ratio_source = _get_schedule_ratios()
    
    pump_mls = _split_ml_by_ratio(ml, ratios)
    grow_ml = pump_mls["grow"]
    micro_ml = pump_mls["micro"]
    bloom_ml = pump_mls["bloom"]
    
    # Dry-run mode: log shadow events without actuation
    if dry_run:
        controller_state = json.dumps({
            "mode": "dry-run",
            "planned_ml": ml,
            "ratio_source": ratio_source,
            "mix": {"grow": grow_ml, "micro": micro_ml, "bloom": bloom_ml},
            "ec_before": ec_before
        })
        # Log for each pump with its portion
        rowids = []
        for pump, pump_ml in [("grow", grow_ml), ("micro", micro_ml), ("bloom", bloom_ml)]:
            if pump_ml > 0:
                rate = _f(f"dosing.{pump}_ml_per_sec", 20.0)
                seconds = pump_ml / rate if rate > 0 else 0
                rowid = _log_dose_event(pump, seconds, reason, "dry-run", ec_before=ec_before, controller_state_json=controller_state)
                rowids.append(rowid)
        
        return {
            "ok": True,
            "dry_run": True,
            "ml": ml,
            "mix": {"grow": grow_ml, "micro": micro_ml, "bloom": bloom_ml},
            "ratio_source": ratio_source,
            "ec_before": ec_before,
            "rowids": rowids,
            "ts": now_dt.isoformat(),
            "message": "Dry-run mode: no pump actuation. Set dosing.dry_run_ec=false to enable."
        }
    
    # Actual actuation with lock
    dose_lock = _get_dose_lock()
    acquired = dose_lock.acquire(blocking=False)
    if not acquired:
        return JSONResponse(status_code=409, content={"error": "another pump is active", "blocked_by": "mix_lock"})
    
    try:
        result, duration_ms = _actuate_mix(grow_ml, micro_ml, bloom_ml)
    finally:
        dose_lock.release()
    
    # Post-read (wait 5s)
    time.sleep(5)
    ec_after, _ = _get_latest_ec()
    
    # Log to dose_events for each pump with its portion
    controller_state = json.dumps({
        "mode": "live",
        "planned_ml": ml,
        "ratio_source": ratio_source,
        "mix": {"grow": grow_ml, "micro": micro_ml, "bloom": bloom_ml},
        "ec_before": ec_before,
        "ec_after": ec_after
    })
    rowids = []
    for pump, pump_ml in [("grow", grow_ml), ("micro", micro_ml), ("bloom", bloom_ml)]:
        if pump_ml > 0:
            rate = _f(f"dosing.{pump}_ml_per_sec", 20.0)
            seconds = pump_ml / rate if rate > 0 else 0
            rowid = _log_dose_event(pump, seconds, reason, "manual", ec_before=ec_before, ec_after=ec_after, controller_state_json=controller_state)
            rowids.append(rowid)
    
    return {
        "ok": True,
        "rowids": rowids,
        "ml": ml,
        "mix": {"grow": grow_ml, "micro": micro_ml, "bloom": bloom_ml},
        "ratio_source": ratio_source,
        "ec_before": ec_before,
        "ec_after": ec_after,
        "result": result
    }

# --- Live endpoint -----------------------------------------------------------
@router.get("/api/ec/live")
def get_ec_live():
    """Return live EC reading with temp, PPM, and stale flag."""
    import requests
    
    ec_val, ec_ts = _get_latest_ec()
    
    # Get temp from latest reading
    temp_c = None
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT temp_c FROM readings ORDER BY ts DESC LIMIT 1")
            row = cur.fetchone()
            if row and row[0] is not None:
                temp_c = float(row[0])
    except Exception:
        pass
    
    # Check if stale via /health/db
    stale = False
    try:
        r = requests.get("http://localhost:8080/health/db", timeout=2)
        if r.status_code == 200:
            data = r.json()
            stale = data.get("is_stale", False) or data.get("age_seconds", 0) > 180
        else:
            stale = True
    except Exception:
        stale = True
    
    # Calculate PPM
    ppm_factor = _i("ec.ppm_factor", 500)
    ppm = int(ec_val * ppm_factor) if ec_val else None
    
    return {
        "ec_ms": ec_val,
        "ppm": ppm,
        "temp_c": temp_c,
        "ts": ec_ts,
        "stale": stale
    }

# --- Settings endpoint -------------------------------------------------------
@router.put("/api/ec/settings")
def update_ec_settings(body: dict = Body(...)):
    """Update EC settings with validation."""
    from app.settings import upsert_settings
    
    updates = {}
    errors = []
    
    # Validate and collect updates
    if "ec.target" in body:
        val = float(body["ec.target"])
        if not (0.6 <= val <= 2.4):
            errors.append("ec.target must be 0.6–2.4")
        else:
            updates["ec.target"] = str(val)
    
    if "ec.enabled" in body:
        updates["ec.enabled"] = "true" if body["ec.enabled"] else "false"
    
    if "ec.maintenance_override" in body:
        updates["ec.maintenance_override"] = "true" if body["ec.maintenance_override"] else "false"
    
    if "ec.ppm_factor" in body:
        val = int(body["ec.ppm_factor"])
        if val not in [448, 500, 640, 700]:
            errors.append("ec.ppm_factor must be one of [448,500,640,700]")
        else:
            updates["ec.ppm_factor"] = str(val)
    
    if "ec.step_min_ml" in body:
        val = float(body["ec.step_min_ml"])
        if val < 0:
            errors.append("ec.step_min_ml must be >= 0")
        else:
            updates["ec.step_min_ml"] = str(val)
    
    if "ec.step_max_ml" in body:
        val = float(body["ec.step_max_ml"])
        if val < 0:
            errors.append("ec.step_max_ml must be >= 0")
        else:
            updates["ec.step_max_ml"] = str(val)
    
    if "ec.safety_factor" in body:
        val = float(body["ec.safety_factor"])
        if not (0.1 <= val <= 1.0):
            errors.append("ec.safety_factor must be 0.1–1.0")
        else:
            updates["ec.safety_factor"] = str(val)
    
    if "ec.min_interval_sec" in body:
        val = int(body["ec.min_interval_sec"])
        if val < 0:
            errors.append("ec.min_interval_sec must be >= 0")
        else:
            updates["ec.min_interval_sec"] = str(val)
    
    if "ec.max_ml_day" in body:
        val = float(body["ec.max_ml_day"])
        if val < 0:
            errors.append("ec.max_ml_day must be >= 0")
        else:
            updates["ec.max_ml_day"] = str(val)
    
    if errors:
        return JSONResponse(status_code=400, content={"ok": False, "errors": errors})
    
    if updates:
        try:
            upsert_settings(updates)
            return {"ok": True, "updated": list(updates.keys())}
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
    
    return {"ok": True, "updated": []}

# --- Status endpoint ---------------------------------------------------------
@router.get("/api/ec/status")
def get_ec_status():
    """Return EC status including auto state, guards, recent, totals."""
    ec_val, ec_ts = _get_latest_ec()
    now_dt = datetime.now(timezone.utc)
    
    # Guards (now returns 3 values: ok, blocked_by, caps_info)
    ok, blocked_by, _ = _check_guards("grow", 1.0)
    guards = {"estop": False, "sensor_stale": False, "mix_lock": False, "reservoir": False, "safeoff": False}
    if not ok and blocked_by:
        if blocked_by in guards:
            guards[blocked_by] = True
    
    ok_int, int_reason = _check_interval_guard(now_dt)
    guards["interval"] = not ok_int
    
    ok_cap, cap_reason = _check_daily_cap(now_dt)
    guards["daily_cap"] = not ok_cap
    
    # EC high guard
    ok_ec, _ = _check_ec_high_guard()
    guards["ec_high"] = not ok_ec
    
    # Auto state (NEW: unified system)
    try:
        from app.auto_control import should_automate
        auto_enabled = should_automate("ec")
    except Exception:
        auto_enabled = False
    
    with _auto_lock:
        holding_reason = _auto_last_holding_reason
    
    # Targets - prioritize schedule EC target over settings
    schedule_ec_target = _get_schedule_ec_target()
    ec_tolerance = _f("targets.ec_tolerance", 0.2)
    
    if schedule_ec_target is not None:
        # Use schedule target with tolerance to calculate band
        ec_target = schedule_ec_target
        ec_low = max(0.0, ec_target - ec_tolerance)
        ec_high = ec_target + ec_tolerance
        target_source = "schedule"
    else:
        # Fallback to settings-based targets
        ec_low = _f("targets.ec_low", 0.8)
        ec_high = _f("targets.ec_high", 1.2)
        ec_target = _f("targets.ec_target", (ec_low + ec_high) / 2.0)
        target_source = "settings"
    
    # Dry-run status
    dry_run = _is_dry_run_ec()
    
    # Totals
    today_ml = _today_total_ml(now_dt)
    
    # Recent
    recent = _recent_doses(50)
    
    return {
        "ec_ms_cm": ec_val,
        "ec_ts": ec_ts,
        "targets": {
            "low": round(ec_low, 2),
            "high": round(ec_high, 2),
            "target": round(ec_target, 2),
            "source": target_source
        },
        "auto": {
            "enabled": auto_enabled,
            "holding_reason": holding_reason,
            "learned_ml_per_mScm": _learned_ml_per_mScm
        },
        "guards": guards,
        "dry_run": dry_run,
        "today_ml": today_ml,
        "recent": recent
    }

# --- Dose log/summary endpoints --------------------------------------------
@router.get("/api/ec/dose/recent")
def ec_dose_recent(limit: int = 20):
    """Return recent EC dose events with pump info for UI pills.
    Reads from unified dose_events table.
    """
    _ensure_dose_events_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts, pump, seconds, reason, actor, ec_before, ec_after, blocked_by
            FROM dose_events
            WHERE pump IN ('grow', 'micro', 'bloom') AND blocked_by IS NULL
            ORDER BY ts DESC
            LIMIT ?
            """,
            (int(limit),)
        )
        rows = cur.fetchall()
    
    events = []
    for r in rows:
        ts_unix = r[0]
        ts_iso = datetime.fromtimestamp(ts_unix, tz=timezone.utc).isoformat() if ts_unix else None
        pump = r[1]
        seconds = r[2]
        volume_ml = _compute_volume_ml(pump, seconds) if seconds else None
        
        events.append({
            "ts_iso": ts_iso,
            "pump": pump,
            "seconds": seconds,
            "volume_ml": volume_ml,
            "actor": r[4] or "manual",
            "reason": r[3] or "",
            "result": "ok"
        })
    
    return {"events": events}


@router.get("/api/ec/dose_log")
def ec_dose_log(
    start: Optional[str] = None,
    end: Optional[str] = None,
    hours: Optional[int] = None,
    grow: Optional[bool] = False,
    limit: int = 2000
):
    try:
        # Grow preset: from grow_start_date to now
        if grow:
            from app.settings import get_all_settings, SA_TZ
            s = get_all_settings()
            grow_date_str = s.get("general.grow_start_date", "")
            if grow_date_str:
                naive_dt = datetime.strptime(grow_date_str, "%Y-%m-%d")
                try:
                    local_dt = SA_TZ.localize(naive_dt)
                except Exception:
                    local_dt = naive_dt.replace(tzinfo=timezone.utc)
                start = local_dt.astimezone(timezone.utc).isoformat()
                end = datetime.now(timezone.utc).isoformat()
        return _dose_events_range(start=start, end=end, hours=hours, limit=limit)
    except ValueError as ve:
        return JSONResponse(status_code=422, content={"ok": False, "error": str(ve)})


@router.get("/api/ec/dose_summary")
def ec_dose_summary(
    start: Optional[str] = None,
    end: Optional[str] = None,
    days: Optional[int] = None,
    grow: Optional[bool] = False
):
    try:
        if grow:
            from app.settings import get_all_settings, SA_TZ
            s = get_all_settings()
            grow_date_str = s.get("general.grow_start_date", "")
            if grow_date_str:
                naive_dt = datetime.strptime(grow_date_str, "%Y-%m-%d")
                try:
                    local_dt = SA_TZ.localize(naive_dt)
                except Exception:
                    local_dt = naive_dt.replace(tzinfo=timezone.utc)
                start = local_dt.astimezone(timezone.utc).isoformat()
                end = datetime.now(timezone.utc).isoformat()
        return _dose_daily_range(start=start, end=end, days=days)
    except ValueError as ve:
        return JSONResponse(status_code=422, content={"ok": False, "error": str(ve)})


@router.get("/api/ec/dose_log.csv")
def ec_dose_log_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    hours: Optional[int] = None,
    grow: Optional[bool] = False,
    limit: int = 2000
):
    try:
        start_for_filename = start
        end_for_filename = end
        if grow:
            from app.settings import get_all_settings, SA_TZ
            s = get_all_settings()
            grow_date_str = s.get("general.grow_start_date", "")
            if grow_date_str:
                naive_dt = datetime.strptime(grow_date_str, "%Y-%m-%d")
                try:
                    local_dt = SA_TZ.localize(naive_dt)
                except Exception:
                    local_dt = naive_dt.replace(tzinfo=timezone.utc)
                start = local_dt.astimezone(timezone.utc).isoformat()
                end = datetime.now(timezone.utc).isoformat()
                start_for_filename = start
                end_for_filename = end
        events = _dose_events_range(start=start, end=end, hours=hours, limit=limit)
        # CSV content
        lines = ["ts,seconds,volume_ml,reason,ec_before,ec_after,guard_triggered"]
        for e in events:
            line = ",".join([
                str(e["ts"]),
                "" if e.get("seconds") is None else str(e.get("seconds")),
                "" if e.get("volume_ml") is None else str(e.get("volume_ml")),
                str(e.get("detail") or "manual"),
                "" if e.get("ec_before") is None else str(e.get("ec_before")),
                "" if e.get("ec_after") is None else str(e.get("ec_after")),
                "" if not e.get("guard_triggered") else str(e.get("guard_triggered"))
            ])
            lines.append(line)
        # Filename
        filename = "ec_dose_log.csv"
        if start_for_filename and end_for_filename:
            try:
                start_date = datetime.fromisoformat(start_for_filename.replace('Z','+00:00')).strftime("%Y%m%d")
                end_date = datetime.fromisoformat(end_for_filename.replace('Z','+00:00')).strftime("%Y%m%d")
                filename = f"ec_dose_log_{start_date}_{end_date}.csv"
            except Exception:
                filename = "ec_dose_log.csv"
        elif hours:
            filename = f"ec_dose_log_{int(hours)}h.csv"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return PlainTextResponse("\n".join(lines), media_type="text/csv", headers=headers)
    except ValueError as ve:
        return PlainTextResponse(f"Error: {ve}", status_code=422)

# --- Automation control ------------------------------------------------------
@router.post("/api/ec/auto")
def set_ec_auto(body: dict = Body(...)):
    """Enable or disable EC automation (DEPRECATED - use /api/auto/ec)."""
    enable = body.get("enable", False)
    
    # NEW: Use unified auto_control system
    try:
        from app.auto_control import set_controller_auto_enabled
        set_controller_auto_enabled("ec", enable)
    except Exception:
        pass
    
    global _auto_enabled_at
    try:
        if enable:
            _auto_enabled_at = time.time()
            _start_auto_worker()
        else:
            _stop_auto_worker()
            _auto_enabled_at = None
    except Exception:
        pass
    
    return {"ok": True, "enabled": enable}

@router.get("/api/ec/auto/enable")
def set_ec_auto_get(on: int = Query(0)):
    """Non-blocking GET toggle fallback (DEPRECATED - use /api/auto/ec)."""
    enable = bool(int(on))
    try:
        from app.auto_control import set_controller_auto_enabled
        set_controller_auto_enabled("ec", enable)
    except Exception:
        pass
    try:
        if enable:
            global _auto_enabled_at
            _auto_enabled_at = time.time()
            _start_auto_worker()
        else:
            _stop_auto_worker()
            _auto_enabled_at = None
    except Exception:
        pass
    return {"ok": True, "enabled": enable, "method": "GET"}

# --- Learning reset ----------------------------------------------------------
@router.post("/api/ec/auto/learn/reset")
def reset_ec_learner():
    """Reset learned ml per mS/cm."""
    global _learned_ml_per_mScm
    _learned_ml_per_mScm = None
    return {"ok": True, "learned_ml_per_mScm": None}

# --- Debug endpoint ----------------------------------------------------------
@router.get("/api/ec/auto/debug")
def get_ec_auto_debug():
    """Return internal automation state for debugging."""
    # Get auto enabled state from unified system
    try:
        from app.auto_control import should_automate
        auto_enabled = should_automate("ec")
    except Exception:
        auto_enabled = False
    
    with _auto_lock:
        return {
            "enabled": auto_enabled,
            "enabled_at": _auto_enabled_at,
            "last_holding_reason": _auto_last_holding_reason,
            "last_block": _auto_last_block,
            "last_block_count": _auto_last_block_count,
            "last_decision": _auto_last_decision,
            "learned_ml_per_mScm": _learned_ml_per_mScm
        }

# --- Controller Preview endpoint --------------------------------------------
@router.get("/api/ec/control/preview")
def get_ec_control_preview():
    """
    Dry-run EC controller decision logic - SINGLE SOURCE OF DECISION MATH.
    Returns what action the controller would take without executing it.
    The auto worker should reuse this calculation.
    
    V2: Includes schedule ratios, dry-run status, and detailed proposed_action.
    """
    # Check if auto control is enabled (NEW: unified system)
    try:
        from app.auto_control import should_automate
        auto_enabled = should_automate("ec")
    except Exception:
        auto_enabled = False
    
    # Read current EC
    ec_val, ec_ts = _get_latest_ec()
    
    # Calculate age
    ec_age_sec = None
    if ec_ts is not None:
        ec_age_sec = int(time.time()) - ec_ts
    
    # Get targets - prioritize schedule EC target over settings
    schedule_ec_target = _get_schedule_ec_target()
    ec_tolerance = _get_setting_with_fallback("targets.ec_tolerance", "ec.tolerance", 0.2)
    
    if schedule_ec_target is not None:
        # Use schedule target with tolerance
        setpoint = schedule_ec_target
        ec_low = max(0.0, setpoint - ec_tolerance)
        ec_high = setpoint + ec_tolerance
    else:
        # Fallback to settings-based targets
        ec_low = _get_setting_with_fallback("targets.ec_low", "ec.low", 0.8)
        ec_high = _get_setting_with_fallback("targets.ec_high", "ec.high", 1.2)
        ec_target = _get_setting_with_fallback("targets.ec_target", "ec.target", 0.0)
        if ec_target > 0:
            setpoint = ec_target
        else:
            setpoint = (ec_low + ec_high) / 2.0
    
    deadband = ec_tolerance if ec_tolerance > 0 else 0.05
    dry_run = _is_dry_run_ec()
    
    # Get schedule ratios
    ratios, ratio_source = _get_schedule_ratios()
    
    # Default response
    response = {
        "would_dose": False,
        "dry_run": dry_run,
        "current_ec": ec_val,
        "ec_age_sec": ec_age_sec,
        "setpoint": setpoint,
        "ec_low": ec_low,
        "ec_high": ec_high,
        "deadband": deadband,
        "auto_enabled": auto_enabled,
        "ratio_source": ratio_source,
        "ratios": ratios,
        "reason": None,
        "proposed_action": None
    }
    
    # Check sensor validity
    if ec_val is None:
        response["reason"] = "sensor_null"
        return response
    
    # Staleness check (120s for preview, stricter in auto mode)
    if ec_age_sec is not None and ec_age_sec > 120:
        response["reason"] = "sensor_stale"
        return response
    
    # Check if in range (EC at or above low threshold = no dose needed)
    if ec_val >= ec_low:
        response["reason"] = "in_range"
        return response
    
    # Check guards (for preview purposes)
    ok, blocked_by, caps_info = _check_guards("grow", 1.0)
    if not ok:
        response["reason"] = f"blocked_by_guard:{blocked_by}"
        response["blocked_by"] = blocked_by
        return response
    
    # Check EC high guard
    ok_ec, ec_guard_reason = _check_ec_high_guard()
    if not ok_ec:
        response["reason"] = "blocked_by_ec_high_guard"
        response["blocked_by"] = "ec_high_guard"
        return response
    
    # Check interval guard
    ok_int, int_reason = _check_interval_guard(datetime.now(timezone.utc))
    if not ok_int:
        response["reason"] = f"blocked_by_interval:{int_reason}"
        response["blocked_by"] = int_reason
        return response
    
    # Check daily cap
    ok_cap, cap_reason = _check_daily_cap(datetime.now(timezone.utc))
    if not ok_cap:
        response["reason"] = f"blocked_by_cap:{cap_reason}"
        response["blocked_by"] = cap_reason
        return response
    
    # Compute proposed dose
    needed_mScm = setpoint - ec_val
    safety_factor = _get_setting_with_fallback("dosing.ec_safety_factor", "ec.safety_factor", 0.6)
    
    if _learned_ml_per_mScm:
        planned_ml = needed_mScm * _learned_ml_per_mScm * safety_factor
    else:
        # Use default ml per mS/cm when no learned value is available
        planned_ml = needed_mScm * DEFAULT_ML_PER_MSCM * safety_factor
    
    # Clamp to step limits
    min_ml = _get_setting_with_fallback("dosing.ec_step_ml_min", "ec.step_min_ml", 10)
    max_ml = _get_setting_with_fallback("dosing.ec_step_ml_max", "ec.step_max_ml", 120)
    planned_ml = max(min_ml, min(planned_ml, max_ml))
    
    # Split by schedule ratio
    pump_mls = _split_ml_by_ratio(planned_ml, ratios)
    
    response.update({
        "would_dose": True,
        "reason": "ec_below_target",
        "proposed_action": {
            "ml": round(planned_ml, 1),
            "mix": pump_mls,
            "ratio_source": ratio_source,
            "needed_mScm": round(needed_mScm, 3),
            "safety_factor": safety_factor,
            "learned_ml_per_mScm": _learned_ml_per_mScm,
            "dry_run": dry_run
        }
    })
    
    return response

# --- Automation worker -------------------------------------------------------
def _auto_worker():
    """Background thread: polls EC and doses when below target.
    
    V2: Uses preview logic for decision math, supports dry-run mode.
    """
    global _auto_last_holding_reason, _auto_last_block, _auto_last_block_count, _auto_last_decision
    poll_interval = 30
    warm_up_polls = 1
    poll_count = 0
    
    while not (_auto_stop_evt and _auto_stop_evt.is_set()):
        time.sleep(poll_interval)
        poll_count += 1
        
        # Suppress auto when global maintenance override is active
        if _b("safety.maintenance_override", False):
            with _auto_lock:
                _auto_last_holding_reason = "maintenance_override"
            continue
        
        try:
            from app.auto_control import should_automate
            if not should_automate("ec"):
                with _auto_lock:
                    _auto_last_holding_reason = "auto_disabled"
                continue
        except Exception:
            with _auto_lock:
                _auto_last_holding_reason = "auto_check_failed"
            continue
        
        # Warm-up
        if poll_count <= warm_up_polls:
            with _auto_lock:
                _auto_last_holding_reason = f"warm_up ({poll_count}/{warm_up_polls})"
            continue
        
        # Use preview logic for decision (single source of truth)
        preview = get_ec_control_preview()
        
        # Check if we should dose
        if not preview.get("would_dose", False):
            with _auto_lock:
                _auto_last_holding_reason = preview.get("reason") or preview.get("blocked_by") or "no_action_needed"
                if preview.get("blocked_by"):
                    blocked = preview.get("blocked_by")
                    if _auto_last_block == blocked:
                        _auto_last_block_count += 1
                    else:
                        _auto_last_block = blocked
                        _auto_last_block_count = 1
            continue
        
        # Get planned action from preview
        proposed = preview.get("proposed_action", {})
        planned_ml = proposed.get("ml", 0)
        ratio_source = proposed.get("ratio_source", "unknown")
        ec_val = preview.get("current_ec")
        dry_run = preview.get("dry_run", True)
        
        # Dose using the dose_ec function (handles dry-run internally)
        try:
            result = dose_ec({"ml": planned_ml, "mix_ratio": "schedule", "reason": "auto"})
            with _auto_lock:
                _auto_last_holding_reason = None
                _auto_last_decision = {
                    "ec_before": ec_val,
                    "needed_mScm": proposed.get("needed_mScm"),
                    "planned_ml": planned_ml,
                    "ratio_source": ratio_source,
                    "dry_run": dry_run,
                    "result": result if isinstance(result, dict) else {"ok": True},
                    "ts": datetime.now(timezone.utc).isoformat()
                }
        except Exception as e:
            with _auto_lock:
                _auto_last_holding_reason = f"dose_error: {e}"

def _start_auto_worker():
    """Start the automation worker thread if not already running."""
    global _auto_thread, _auto_stop_evt
    with _auto_lock:
        if _auto_thread and _auto_thread.is_alive():
            return
        _auto_stop_evt = threading.Event()
        _auto_thread = threading.Thread(target=_auto_worker, daemon=True, name="EC-Auto")
        _auto_thread.start()

def _stop_auto_worker():
    """Stop the automation worker thread."""
    global _auto_thread, _auto_stop_evt
    with _auto_lock:
        if _auto_stop_evt:
            _auto_stop_evt.set()
        if _auto_thread:
            _auto_thread.join(timeout=2)
            _auto_thread = None
