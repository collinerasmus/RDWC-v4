"""
EC Control API

Endpoints:
- GET /api/ec/status
- POST /api/ec/dose
- POST /api/ec/auto
- POST /api/ec/auto/learn/reset
- GET /api/ec/auto/debug

Manual dosing with guards (G/M/B pumps in sequential mix) and dose log table.
Automation: background controller that raises EC when it falls below the target band.
It learns dose effect from prior dose logs (ml per 1.0 mS/cm) and respects all guards.
"""
from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone, timedelta
import time
import sqlite3
import threading
from pathlib import Path

router = APIRouter()

DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"
try:
    # Unified dose events logger (used for UI totals and cross-controller history)
    from app.dosing import log_dose_event
except Exception:
    log_dose_event = None  # Fallback if module import fails during tooling

# --- Automation state --------------------------------------------------------
_auto_thread: Optional[threading.Thread] = None
_auto_stop_evt: Optional[threading.Event] = None
_auto_lock = threading.Lock()
_dose_lock = threading.Lock()
_auto_last_holding_reason: Optional[str] = None
_auto_enabled_at: Optional[float] = None
_auto_last_block: Optional[str] = None
_auto_last_block_count: int = 0
_auto_last_decision: Dict[str, Any] = {}  # For debug endpoint

# Learning estimator (ml per 1.0 mS/cm)
_learned_ml_per_mScm: Optional[float] = None

# --- DB helpers --------------------------------------------------------------
def _ensure_tables() -> None:
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

def _log_row(row: Dict[str, Any]) -> int:
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
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("UPDATE ec_dose_log SET post_ec=? WHERE id=?", (post_ec, rowid))
        conn.commit()

def _read_post_ec_async(rowid: int, observe_s: int) -> None:
    """
    Background thread: wait observe_s seconds, then read EC and update post_ec.
    Also calculates learning from successful doses.
    """
    time.sleep(observe_s)
    
    # Read EC after settling
    ec_after, _ = _get_latest_ec()
    if ec_after is None:
        return
    
    # Update post_ec in database
    _update_post_ec(rowid, ec_after)
    
    # Learn from this dose
    _update_learning(rowid, ec_after)

def _update_learning(rowid: int, ec_after: Optional[float]) -> None:
    """
    Calculate learned ml per mS/cm from recent successful doses.
    Uses doses with valid pre/post EC readings.
    Formula: median(ml / delta_ec) where delta_ec = |post_ec - pre_ec|.
    """
    global _learned_ml_per_mScm
    
    _ensure_tables()
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            # Get recent successful doses with valid pre/post EC
            cur.execute(
                """
                SELECT volume_ml, pre_ec, post_ec
                FROM ec_dose_log
                WHERE result='ok' AND pre_ec IS NOT NULL AND post_ec IS NOT NULL
                  AND volume_ml > 0
                ORDER BY id DESC
                LIMIT 20
                """
            )
            rows = cur.fetchall()
        
        if not rows:
            return  # No valid doses yet
        
        # Calculate ml per mS/cm for each dose
        rates = []
        for ml, pre_ec, post_ec in rows:
            delta_ec = abs(post_ec - pre_ec)
            if delta_ec > 0.01:  # Avoid division by very small numbers
                rate = ml / delta_ec
                rates.append(rate)
        
        if rates:
            # Use median (less sensitive to outliers)
            rates.sort()
            _learned_ml_per_mScm = rates[len(rates) // 2]
    except Exception as e:
        import logging
        logging.error(f"EC learning calculation failed: {e}")


def _compute_learning_from_db(limit: int = 50) -> Optional[float]:
    """Recompute learned ml/mS·cm from recent successful doses.
    Used on startup/status when in-memory cache is empty so the UI doesn't show blanks after restart."""
    _ensure_tables()
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT volume_ml, pre_ec, post_ec
                FROM ec_dose_log
                WHERE result='ok' AND pre_ec IS NOT NULL AND post_ec IS NOT NULL
                  AND volume_ml > 0
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            )
            rows = cur.fetchall()
        rates = []
        for ml, pre_ec, post_ec in rows:
            delta_ec = abs(post_ec - pre_ec)
            if delta_ec > 0.01:
                rates.append(ml / delta_ec)
        if not rates:
            return None
        rates.sort()
        return rates[len(rates) // 2]
    except Exception:
        return None

def _recent_doses(limit: int = 5) -> List[Dict[str, Any]]:
    _ensure_tables()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, ts_utc, action, volume_ml, mix_ratio, duration_ms, pre_ec, post_ec, result, reason FROM ec_dose_log WHERE post_ec IS NOT NULL ORDER BY id DESC LIMIT ?",
            (int(limit),)
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r[0], "ts_utc": r[1], "action": r[2], "volume_ml": r[3],
            "mix_ratio": r[4], "duration_ms": r[5], "pre_ec": r[6], "post_ec": r[7],
            "result": r[8], "reason": r[9]
        })
    return out

def _dose_events_range(start: Optional[str] = None, end: Optional[str] = None, hours: Optional[int] = None, limit: int = 2000) -> List[Dict[str, Any]]:
    """Return dose events within a time range ordered ascending by ts_utc.
    Each row: {ts, seconds, volume_ml, detail, pumps, ec_before, ec_after, guard_triggered}
    """
    _ensure_tables()
    # Determine time window
    start_iso = None
    end_iso = None
    if start and end:
        start_iso = start
        end_iso = end
    elif hours:
        end_iso = datetime.now(timezone.utc).isoformat()
        start_iso = (datetime.now(timezone.utc) - timedelta(hours=int(hours))).isoformat()
    else:
        # Default last 24h
        end_iso = datetime.now(timezone.utc).isoformat()
        start_iso = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts_utc, action, volume_ml, duration_ms, pre_ec, post_ec, result, reason, mix_ratio
            FROM ec_dose_log
            WHERE ts_utc BETWEEN ? AND ?
            ORDER BY ts_utc ASC
            LIMIT ?
            """,
            (start_iso, end_iso, int(limit))
        )
        rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        ts_s = r[0]
        # Parse mix_ratio to extract pump amounts (e.g., "schedule:G15.2M15.2B15.2" or "grow:1.0s")
        pumps = {"grow": None, "micro": None, "bloom": None}
        mix_ratio = r[8] or ""
        if mix_ratio:
            import re
            # Look for G, M, B values
            g_match = re.search(r'G([\d.]+)', mix_ratio)
            m_match = re.search(r'M([\d.]+)', mix_ratio)
            b_match = re.search(r'B([\d.]+)', mix_ratio)
            if g_match:
                pumps["grow"] = float(g_match.group(1))
            if m_match:
                pumps["micro"] = float(m_match.group(1))
            if b_match:
                pumps["bloom"] = float(b_match.group(1))
        
        out.append({
            "ts": ts_s,
            "seconds": (float(r[3]) / 1000.0) if r[3] is not None else None,
            "volume_ml": float(r[2]) if r[2] is not None else None,
            "pumps": pumps,
            "detail": r[7] or r[1],
            "ec_before": float(r[4]) if r[4] is not None else None,
            "ec_after": float(r[5]) if r[5] is not None else None,
            "guard_triggered": (r[6] or '').startswith('error')
        })
    return out

def _dose_daily_range(start: Optional[str] = None, end: Optional[str] = None, days: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return daily aggregates of volume_ml for result='ok'."""
    _ensure_tables()
    # Range
    if start and end:
        start_iso = start
        end_iso = end
    else:
        d = int(days) if days else 30
        end_iso = datetime.now(timezone.utc).isoformat()
        start_iso = (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT substr(ts_utc,1,10) AS day, COALESCE(SUM(volume_ml),0)
            FROM ec_dose_log
            WHERE result='ok' AND ts_utc BETWEEN ? AND ?
            GROUP BY day
            ORDER BY day ASC
            """,
            (start_iso, end_iso)
        )
        rows = cur.fetchall()
    return [{"day": r[0], "total_ml": float(r[1] or 0.0)} for r in rows]

def _today_total_ml(now_dt: datetime) -> float:
    _ensure_tables()
    try:
        from app.settings import SA_TZ
    except Exception:
        SA_TZ = timezone.utc
    local_now = now_dt.astimezone(SA_TZ)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_local.astimezone(timezone.utc)
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(volume_ml),0) FROM ec_dose_log WHERE result='ok' AND ts_utc >= ?",
            (start_utc.isoformat(),)
        )
        val = cur.fetchone()[0]
        return float(val or 0.0)

def _last_ok_ts() -> Optional[datetime]:
    _ensure_tables()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT ts_utc FROM ec_dose_log WHERE result='ok' ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return None
        try:
            return datetime.fromisoformat(row[0]).astimezone(timezone.utc)
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

def _get_schedule_ec_target() -> Tuple[Optional[float], Optional[float]]:
    """
    Get EC target from current week in nutrient schedule.
    Returns (ec_target, tolerance) or (None, None) if schedule not available.
    Tolerance defaults to settings or 0.2.
    """
    try:
        from app.settings import get_all_settings
        settings = get_all_settings()
        tolerance = float(settings.get("targets.ec_tolerance", "0.2") or 0.2)
        start_str = settings.get("general.grow_start_date", "")
        if not start_str:
            return (None, None)

        # Align with schedule_api week calc (YYYY-MM-DD, UTC, capped to 12)
        from datetime import datetime, timezone
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            start_date = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        days = max(0, (now - start_date).days)
        current_week = min(12, max(1, (days // 7) + 1))
        
        # Get schedule from DB
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT ec_target FROM nutrient_schedule WHERE week = ? LIMIT 1",
                (current_week,)
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                return (float(row[0]), tolerance)
    except Exception:
        pass
    return (None, None)

def _get_schedule_mix_ratios() -> Optional[Tuple[float, float, float]]:
    """
    Get nutrient mix ratios (Grow/Micro/Bloom) for the current week from the
    nutrient_schedule table. Returns (grow, micro, bloom) ml per 10L. If the
    schedule is unavailable or invalid, returns None.
    """
    try:
        from app.settings import get_all_settings
        settings = get_all_settings()
        start_str = settings.get("general.grow_start_date", "")
        if not start_str:
            return None

        from datetime import datetime, timezone
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            start_date = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        days = max(0, (now - start_date).days)
        current_week = min(12, max(1, (days // 7) + 1))

        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT grow_ml10, micro_ml10, bloom_ml10 FROM nutrient_schedule WHERE week = ? LIMIT 1",
                (current_week,),
            )
            row = cur.fetchone()
            if row:
                g, m, b = (float(row[0] or 0.0), float(row[1] or 0.0), float(row[2] or 0.0))
                # Treat negatives as zero for safety
                g = max(0.0, g); m = max(0.0, m); b = max(0.0, b)
                if (g + m + b) > 0:
                    return (g, m, b)
    except Exception:
        pass
    return None

def _get_ec_targets() -> Tuple[float, float]:
    """
    Get EC low and high targets.
    
    **Priority 1**: Current week's scheduler target ± tolerance
    (e.g., week 2 seedling = 0.8 ± 0.2 → 0.6-1.0 mS/cm)
    
    **Priority 2 (Fallback)**: Manual settings targets.ec_low/high
    If scheduler is unavailable, defaults to 0.4-0.6 (SEEDLING-SAFE).
    
    **IMPORTANT**: UI Parameters section shows live scheduler-derived values.
    Manual settings are LEGACY and only used if scheduler is broken.
    
    Returns (ec_low, ec_high) in mS/cm.
    """
    schedule_target, schedule_tol = _get_schedule_ec_target()
    if schedule_target is not None and schedule_tol is not None:
        return (schedule_target - schedule_tol, schedule_target + schedule_tol)
    
    # Fallback to manual settings (SEEDLING-SAFE DEFAULTS)
    # WARNING: If scheduler is broken, we use 0.4-0.6 (safe for seedlings)
    # User MUST update targets based on grow stage from scheduler
    s = _get_settings_dict()
    def _f(k: str, d: float) -> float:
        return float(s.get(k, str(d)) or d)
    return (_f("targets.ec_low", 0.4), _f("targets.ec_high", 0.6))

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
def _check_guards() -> Tuple[bool, Optional[str]]:
    """Return (ok, reason). If not ok, reason is the blocking guard.
    
    ALWAYS-ON guards (both Auto and Manual):
        - E-STOP
        - Reservoir empty
        - Mix lock (concurrent dosing)
        - Temperature range (16-26°C) - protects plants
        - pH range (5.5-6.5) - protects nutrient uptake
    
    AUTO-ONLY guards (only when global_auto is enabled):
        - Sensor stale (5min)
    """
    # Check if we're in auto mode
    is_auto_mode = False
    try:
        from app.auto_control import is_global_auto_enabled
        is_auto_mode = is_global_auto_enabled()
    except Exception:
        is_auto_mode = True  # Fail-safe: assume auto mode if can't check
    
    # === ALWAYS-ON GUARDS ===
    
    # E-STOP (always enforced)
    if _b("safety.estop", False):
        return (False, "estop")
    
    # Reservoir (always enforced)
    res_l = _f("general.reservoir_liters", 25.0)
    if res_l <= 0:
        return (False, "reservoir")
    
    # Dose lock (always enforced - prevent concurrent dosing)
    if _dose_lock.locked():
        return (False, "mix_lock")
    
    # Temperature range gate (16-28°C) - always enforced (plant safety)
    temp_val, temp_ts = _get_latest_temp()
    if temp_val is not None:
        if temp_val < 16.0 or temp_val > 28.0:
            return (False, f"temp_range ({temp_val:.1f}°C)")
    
    # pH range gate (5.5-6.5) - always enforced (nutrient uptake safety)
    ph_val, ph_ts = _get_latest_ph()
    if ph_val is not None:
        if ph_val < 5.5 or ph_val > 6.5:
            return (False, f"ph_range ({ph_val:.2f})")
    
    # === AUTO-ONLY GUARDS ===
    if is_auto_mode:
        # Stale EC sensor (only in auto mode)
        ec_val, ec_ts = _get_latest_ec()
        if ec_val is None or ec_ts is None:
            return (False, "sensor_stale")
        now_ts = int(time.time())
        if (now_ts - ec_ts) > 300:  # 5 min stale
            return (False, "sensor_stale")
    
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
    """Manual EC dose - supports both pump+seconds and ml+mix_ratio modes."""
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
        # Global safety override gate
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
        
        # Check interval guard (per-pump) - 15min default for 2× HRT
        min_interval = _i("ec.min_interval_sec", 900)
        if not override and min_interval > 0:
            last_ts = _last_ok_ts()
            if last_ts:
                elapsed = (datetime.now(timezone.utc) - last_ts).total_seconds()
                if elapsed < min_interval:
                    return JSONResponse(status_code=409, content={"error": f"min interval not met ({int(min_interval - elapsed)}s remaining)"})
        
        # Check daily cap
        if not override:
            cap = _f("ec.max_ml_day", 0)
            if cap > 0:
                used = _today_total_ml(datetime.now(timezone.utc))
                if used >= cap:
                    return JSONResponse(status_code=409, content={"error": f"daily cap reached ({used:.1f}/{cap:.1f}ml)"})
        
        # Never allow >1 nutrient pump ON
        if _dose_lock.locked():
            return JSONResponse(status_code=409, content={"error": "another pump is active"})
        
        # Get rate for this pump
        rate_key = f"dosing.{pump}_ml_per_sec"
        rate = _f(rate_key, 0.784)  # Default to calibrated nursery standard
        # Sanity bounds: 0.1–50 ml/sec (allow slow peristaltic to fast gear pumps)
        rate = max(0.1, min(50.0, rate))
        ml = seconds * rate
        
        # Pre-read EC
        ec_before, _ = _get_latest_ec()
        # Hard guardrail: disallow nutrient if EC already above target band
        try:
            # Prefer target±tolerance if present
            ec_tgt = _f("targets.ec_target", 0.0)
            ec_tol = _f("targets.ec_tolerance", 0.0)
            ec_hi = _f("targets.ec_high", 1.2)
            threshold = (ec_tgt + ec_tol) if (ec_tgt > 0 and ec_tol > 0) else ec_hi
            if (ec_before is not None) and (threshold > 0) and (ec_before >= threshold):
                return JSONResponse(status_code=409, content={"error": f"blocked: ec_high_guard ({ec_before:.2f} >= {threshold:.2f})"})
        except Exception:
            pass
        
        # Actuate with lock and try/finally
        from app.relays_core import set_dosing_grow, set_dosing_micro, set_dosing_bloom
        
        result = "ok"
        duration_ms = int(seconds * 1000)
        
        try:
            with _dose_lock:
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
            result = f"error: {e}"
            # Ensure OFF
            try:
                set_dosing_grow(False, reason="ec_dose_error", force=True)
                set_dosing_micro(False, reason="ec_dose_error", force=True)
                set_dosing_bloom(False, reason="ec_dose_error", force=True)
            except Exception:
                pass
        
# Log with post_ec=None initially (will be updated after settling time)
        rowid = _log_row({
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "action": "dose",
            "volume_ml": ml,
            "mix_ratio": f"{pump}:{seconds}s",
            "duration_ms": duration_ms,
            "pre_ec": ec_before,
            "post_ec": None,
            "result": result,
            "reason": reason
        })
        
        # Schedule post-read after settling time (async)
        # Use EC-specific observe window if configured; fallback to 600s sensible default
        observe_s = _i("dosing.ec_observe_s_after_dose", _i("dosing.observe_s_after_dose", 600))
        threading.Thread(
            target=_read_post_ec_async,
            args=(rowid, observe_s),
            daemon=True
        ).start()

        # Also log to unified dose_events for UI totals (if available)
        try:
            if log_dose_event is not None:
                # Record a single-pump event for dashboard totals
                log_dose_event(
                    pump=pump,
                    seconds=seconds,
                    reason=reason or "manual",
                    actor="controller",
                    ec_before=ec_before,
                    ec_after=None,
                )
        except Exception:
            pass
        
        ec_after = None
        
        return {
            "ok": True,
            "pump": pump,
            "seconds": seconds,
            "ec_before": ec_before,
            "ec_after": ec_after,
            "ts": datetime.now(timezone.utc).isoformat()
        }
    
    # Legacy mode: ml+mix_ratio (only reached if pump+seconds not in body)
    ml = body.get("ml", 0)
    mix_ratio = body.get("mix_ratio", "schedule")  # schedule | custom
    custom = body.get("custom", {})
    reason = body.get("reason", "manual")
    
    # Validate
    if ml <= 0 or ml > 500:
        return JSONResponse(status_code=400, content={"error": "ml must be 0.1–500"})
    
    # Guards
    ok, guard = _check_guards()
    if not ok:
        return JSONResponse(status_code=409, content={"error": f"blocked by {guard}"})
    
    ok, guard = _check_interval_guard(datetime.now(timezone.utc))
    if not ok:
        # Maintenance override bypasses interval
        if not _b("safety.maintenance_override", False):
            return JSONResponse(status_code=409, content={"error": f"blocked by {guard}"})
    
    ok, guard = _check_daily_cap(datetime.now(timezone.utc))
    if not ok:
        if not _b("safety.maintenance_override", False):
            return JSONResponse(status_code=409, content={"error": f"blocked by {guard}"})

    # Hard guardrail before dosing in ml-mode as well
    try:
        ec_before, _ = _get_latest_ec()
        ec_tgt = _f("targets.ec_target", 0.0)
        ec_tol = _f("targets.ec_tolerance", 0.0)
        ec_hi = _f("targets.ec_high", 1.2)
        threshold = (ec_tgt + ec_tol) if (ec_tgt > 0 and ec_tol > 0) else ec_hi
        if (ec_before is not None) and (threshold > 0) and (ec_before >= threshold):
            return JSONResponse(status_code=409, content={"error": f"blocked: ec_high_guard ({ec_before:.2f} >= {threshold:.2f})"})
    except Exception:
        pass
    
    # Split by ratio
    if mix_ratio == "custom":
        g = float(custom.get("grow", 0))
        m = float(custom.get("micro", 0))
        b = float(custom.get("bloom", 0))
        total_ratio = g + m + b
        if total_ratio == 0:
            return JSONResponse(status_code=400, content={"error": "custom ratio sums to zero"})
        grow_ml = ml * (g / total_ratio)
        micro_ml = ml * (m / total_ratio)
        bloom_ml = ml * (b / total_ratio)
    else:
        # Schedule ratio from active week
        ratios = _get_schedule_mix_ratios()
        if ratios is None:
            # Fallback: equal split if schedule not available
            grow_ml = ml / 3.0
            micro_ml = ml / 3.0
            bloom_ml = ml / 3.0
            mix_ratio = "schedule_fallback_equal"
        else:
            g, m, b = ratios
            total = g + m + b
            grow_ml = ml * (g / total)
            micro_ml = ml * (m / total)
            bloom_ml = ml * (b / total)
    
    # Pre-read
    ec_before, _ = _get_latest_ec()
    
    # Dose with lock
    with _dose_lock:
        result, duration_ms = _actuate_mix(grow_ml, micro_ml, bloom_ml)
    
    # Log with post_ec=None initially (will be updated after settling time)
    rowid = _log_row({
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "action": "dose",
        "volume_ml": ml,
        "mix_ratio": f"{mix_ratio}:G{grow_ml:.1f}M{micro_ml:.1f}B{bloom_ml:.1f}",
        "duration_ms": duration_ms,
        "pre_ec": ec_before,
        "post_ec": None,
        "result": result,
        "reason": reason
    })
    
    # Schedule post-read after settling time (async)
    observe_s = _i("dosing.ec_observe_s_after_dose", _i("dosing.observe_s_after_dose", 600))
    threading.Thread(
        target=_read_post_ec_async,
        args=(rowid, observe_s),
        daemon=True
    ).start()
    
    ec_after = None

    # Also log to unified dose_events for UI totals (split per pump)
    try:
        if log_dose_event is not None:
            # Compute seconds per pump from ml and configured rates
            def _rate(key: str, default: float) -> float:
                try:
                    return max(0.1, min(50.0, _f(key, default)))
                except Exception:
                    return default
            r_g = _rate("dosing.grow_ml_per_sec", 1.02)
            r_m = _rate("dosing.micro_ml_per_sec", 1.02)
            r_b = _rate("dosing.bloom_ml_per_sec", 1.02)
            parts: List[Tuple[str, float, float]] = [
                ("grow", grow_ml, r_g),
                ("micro", micro_ml, r_m),
                ("bloom", bloom_ml, r_b),
            ]
            for name, ml_part, rate_part in parts:
                if ml_part and ml_part > 0:
                    sec = ml_part / rate_part
                    log_dose_event(
                        pump=name,
                        seconds=sec,
                        reason=reason or "manual",
                        actor="controller",
                        ec_before=ec_before,
                        ec_after=None,
                    )
    except Exception:
        pass
    
    return {
        "ok": True,
        "rowid": rowid,
        "ml": ml,
        "mix": {"grow": grow_ml, "micro": micro_ml, "bloom": bloom_ml},
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
    
    # Guards
    ok, guard = _check_guards()
    guards = {"estop": False, "sensor_stale": False, "mix_lock": False, "reservoir": False}
    if not ok and guard:
        guards[guard] = True
    
    ok_int, int_reason = _check_interval_guard(now_dt)
    guards["interval"] = not ok_int
    
    ok_cap, cap_reason = _check_daily_cap(now_dt)
    guards["daily_cap"] = not ok_cap
    
    # Auto state (NEW: unified system)
    try:
        from app.auto_control import should_automate
        auto_enabled = should_automate("ec")
        if auto_enabled:
            _start_auto_worker()  # ensure worker is running when automation is allowed
    except Exception:
        auto_enabled = False
    
    with _auto_lock:
        holding_reason = _auto_last_holding_reason

    # Ensure learned estimate is populated after restart (pull from DB if cache empty)
    global _learned_ml_per_mScm
    if _learned_ml_per_mScm is None:
        _learned_ml_per_mScm = _compute_learning_from_db()
    
    # Targets from scheduler or manual settings
    ec_low, ec_high = _get_ec_targets()
    
    # Totals
    today_ml = _today_total_ml(now_dt)
    
    # Recent
    recent = _recent_doses(50)
    
    return {
        "ec_ms_cm": ec_val,
        "ec_ts": ec_ts,
        "targets": {"low": ec_low, "high": ec_high},
        "auto": {
            "enabled": auto_enabled,
            "holding_reason": holding_reason,
            "learned_ml_per_mScm": _learned_ml_per_mScm
        },
        "guards": guards,
        "today_ml": today_ml,
        "recent": recent
    }

# --- Dose log/summary endpoints --------------------------------------------
@router.get("/api/ec/dose/recent")
def ec_dose_recent(limit: int = 20):
    """Return recent EC dose events with pump info for UI pills."""
    _ensure_tables()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts_utc, action, volume_ml, mix_ratio, duration_ms, result, reason
            FROM ec_dose_log
            WHERE result='ok'
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),)
        )
        rows = cur.fetchall()
    
    events = []
    for r in rows:
        ts_iso = r[0]
        mix_ratio = r[3] or ""
        duration_ms = r[4]
        
        # Extract pump from mix_ratio (format: "grow:0.4s" or "micro:0.2s")
        pump = "unknown"
        seconds = None
        if ":" in mix_ratio:
            parts = mix_ratio.split(":")
            pump = parts[0].strip()
            if len(parts) > 1 and parts[1].endswith("s"):
                try:
                    seconds = float(parts[1].rstrip("s"))
                except Exception:
                    pass
        
        # Fallback to duration_ms if seconds not parsed
        if seconds is None and duration_ms:
            seconds = float(duration_ms) / 1000.0
        
        events.append({
            "ts_iso": ts_iso,
            "pump": pump,
            "seconds": seconds,
            "volume_ml": float(r[2]) if r[2] else None,
            "actor": r[6] or "manual",
            "reason": r[6] or "",
            "result": r[5]
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

# --- Fix post_ec for past doses -----------------------------------------------
@router.post("/api/ec/dose/fix_post_ec")
def fix_dose_post_ec(dose_ids: List[int] = Body(...)):
    """
    Fix post_ec values for doses by reading current EC and updating them.
    Useful after enabling settling time observation.
    Returns fixed doses and updated learning.
    """
    _ensure_tables()
    fixed = []
    
    try:
        # Read current EC
        ec_val, _ = _get_latest_ec()
        if ec_val is None:
            return JSONResponse(status_code=409, content={"error": "EC sensor unavailable"})
        
        with sqlite3.connect(str(DB_PATH)) as conn:
            for dose_id in dose_ids:
                cur = conn.cursor()
                cur.execute("SELECT pre_ec FROM ec_dose_log WHERE id=?", (dose_id,))
                row = cur.fetchone()
                if row and row[0] is not None:
                    pre_ec = float(row[0])
                    # Estimate effect: assume dose reduces EC proportionally
                    # For now, use current reading as post_ec
                    conn.execute("UPDATE ec_dose_log SET post_ec=? WHERE id=?", (ec_val, dose_id))
                    fixed.append({"id": dose_id, "pre_ec": pre_ec, "post_ec": ec_val})
        
        # Recalculate learning
        _update_learning(None, None)
        
        return {
            "ok": True,
            "fixed": fixed,
            "learned_ml_per_mScm": _learned_ml_per_mScm
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

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
    Dry-run EC controller decision logic.
    Returns what action the controller would take without executing it.
    Useful for UI feedback and debugging.
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
    
    # Get targets
    ec_low, ec_high = _get_ec_targets()
    target_mid = (ec_low + ec_high) / 2.0
    deadband = _f("ec.deadband", 0.05)
    
    # Default response
    response = {
        "would_dose": False,
        "current_ec": ec_val,
        "ec_age_sec": ec_age_sec,
        "setpoint": target_mid,
        "ec_low": ec_low,
        "ec_high": ec_high,
        "deadband": deadband,
        "auto_enabled": auto_enabled,
        "reason": None,
        "proposed_action": None
    }
    
    # Check sensor validity
    if ec_val is None:
        response["reason"] = "sensor_null"
        return response
    
    if ec_age_sec is not None and ec_age_sec > 120:
        response["reason"] = "sensor_stale"
        return response
    
    # Check if in range
    if ec_val >= ec_low:
        response["reason"] = "in_range"
        return response
    
    # Check guards (for preview purposes)
    ok, guard = _check_guards()
    if not ok:
        response["reason"] = f"blocked_by_guard: {guard}"
        return response
    
    # Check interval guard
    ok_int, int_reason = _check_interval_guard(datetime.now(timezone.utc))
    if not ok_int:
        response["reason"] = f"blocked_by_interval: {int_reason}"
        return response
    
    # Check daily cap
    ok_cap, cap_reason = _check_daily_cap(datetime.now(timezone.utc))
    if not ok_cap:
        response["reason"] = f"blocked_by_cap: {cap_reason}"
        return response
    
    # Compute proposed dose
    needed_mScm = target_mid - ec_val
    safety_factor = _f("dosing.ec_safety_factor", 0.6)
    
    if _learned_ml_per_mScm:
        planned_ml = needed_mScm * _learned_ml_per_mScm * safety_factor
    else:
        # Default: 30ml per 0.1 mS/cm
        planned_ml = needed_mScm * 300 * safety_factor
    
    # Clamp
    min_ml = _f("dosing.ec_step_ml_min", 10)
    max_ml = _f("dosing.ec_step_ml_max", 120)
    planned_ml = max(min_ml, min(planned_ml, max_ml))
    
    # Get mix ratio (schedule or custom)
    mix_ratio = _s("dosing.ec_mix_ratio", "schedule")
    
    response.update({
        "would_dose": True,
        "reason": "ec_below_target",
        "proposed_action": {
            "ml": round(planned_ml, 1),
            "mix_ratio": mix_ratio,
            "needed_mScm": round(needed_mScm, 3),
            "safety_factor": safety_factor,
            "learned_ml_per_mScm": _learned_ml_per_mScm
        }
    })
    
    return response

# --- Automation worker -------------------------------------------------------
def _auto_worker():
    """Background thread: polls EC and doses when below target."""
    global _auto_last_holding_reason, _auto_last_block, _auto_last_block_count, _auto_last_decision
    poll_interval = 30
    warm_up_polls = 1
    poll_count = 0
    
    while not (_auto_stop_evt and _auto_stop_evt.is_set()):
        time.sleep(poll_interval)
        poll_count += 1
        
        # Suppress auto when global maintenance override is active
        # Controller automation gating (NEW: unified system)
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
        
        # Guards
        ok, guard = _check_guards()
        if not ok:
            with _auto_lock:
                _auto_last_holding_reason = guard
                if _auto_last_block == guard:
                    _auto_last_block_count += 1
                else:
                    _auto_last_block = guard
                    _auto_last_block_count = 1
            continue
        
        ok_int, int_reason = _check_interval_guard(datetime.now(timezone.utc))
        if not ok_int:
            with _auto_lock:
                _auto_last_holding_reason = int_reason
            continue
        
        ok_cap, cap_reason = _check_daily_cap(datetime.now(timezone.utc))
        if not ok_cap:
            with _auto_lock:
                _auto_last_holding_reason = cap_reason
            continue
        
        # Read EC
        ec_val, _ = _get_latest_ec()
        if ec_val is None:
            with _auto_lock:
                _auto_last_holding_reason = "sensor_null"
            continue
        
        # Check if below target
        ec_low, ec_high = _get_ec_targets()
        target_mid = (ec_low + ec_high) / 2.0
        
        if ec_val >= ec_low:
            with _auto_lock:
                _auto_last_holding_reason = "in_range"
            continue
        
        # Compute dose
        needed_mScm = target_mid - ec_val
        safety_factor = _f("dosing.ec_safety_factor", 0.6)
        
        if _learned_ml_per_mScm:
            planned_ml = needed_mScm * _learned_ml_per_mScm * safety_factor
        else:
            # Default: 30ml per 0.1 mS/cm
            planned_ml = needed_mScm * 300 * safety_factor
        
        # Clamp
        min_ml = _f("dosing.ec_step_ml_min", 10)
        max_ml = _f("dosing.ec_step_ml_max", 120)
        planned_ml = max(min_ml, min(planned_ml, max_ml))
        
        # Dose (schedule ratio for auto)
        try:
            dose_ec({"ml": planned_ml, "mix_ratio": "schedule", "reason": "auto"})
            with _auto_lock:
                _auto_last_holding_reason = None
                _auto_last_decision = {
                    "ec_before": ec_val,
                    "needed_mScm": needed_mScm,
                    "planned_ml": planned_ml,
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

# --- Module initialization ---------------------------------------------------
def _init_learning_on_load():
    """On module load, recalculate learning from existing dose log if available."""
    global _learned_ml_per_mScm
    _ensure_tables()
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM ec_dose_log
                WHERE result='ok' AND pre_ec IS NOT NULL AND post_ec IS NOT NULL
                  AND volume_ml > 0
                """
            )
            count = cur.fetchone()[0]
        if count > 0:
            _update_learning(None, None)
            import logging
            logging.info(f"EC learning initialized: {_learned_ml_per_mScm} ml/mScm from {count} doses")
    except Exception as e:
        import logging
        logging.warning(f"Failed to initialize EC learning on load: {e}")

# Initialize learning on module load
try:
    _init_learning_on_load()
except Exception:
    pass  # Silently fail if DB not ready yet
