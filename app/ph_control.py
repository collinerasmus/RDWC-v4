"""
pH Control API

Endpoints:
- GET /api/ph/status
- POST /api/ph/dose
- POST /api/ph/auto
- GET /api/ph/export

Manual dosing with guards and a simple log table.
Automation: background controller (pH Up only) that gently raises pH when it falls below the target band.
It learns dose effect from prior dose logs and ignores pH when EC is below a baseline threshold.
"""
from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta, timezone
import time
import sqlite3
import threading
from pathlib import Path
import os

router = APIRouter()

DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

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

# --- DB helpers --------------------------------------------------------------
def _ensure_tables() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ph_dose_log(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts_utc TEXT NOT NULL,
              action TEXT NOT NULL,
              volume_ml REAL,
              duration_ms INTEGER,
              pre_ph REAL,
              post_ph REAL,
              result TEXT NOT NULL,
              reason TEXT
            )
            """
        )
        # Helpful index for time-ordered queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ph_dose_log_ts ON ph_dose_log(ts_utc)")
        # Optional daily totals view (idempotent)
        try:
            conn.execute(
                """
                CREATE VIEW IF NOT EXISTS ph_dose_daily AS
                SELECT substr(ts_utc,1,10) AS day, SUM(COALESCE(volume_ml,0)) AS total_ml
                FROM ph_dose_log
                WHERE result='ok'
                GROUP BY day
                ORDER BY day ASC
                """
            )
        except Exception:
            pass
        # Optional retention purge
        try:
            keep_days = int(os.environ.get("PH_DOSE_LOG_RETENTION_DAYS", "0") or "0")
        except Exception:
            keep_days = 0
        if keep_days and keep_days > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
            conn.execute("DELETE FROM ph_dose_log WHERE ts_utc < ?", (cutoff,))
        conn.commit()

def _log_row(row: Dict[str, Any]) -> int:
    _ensure_tables()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ph_dose_log(ts_utc, action, volume_ml, duration_ms, pre_ph, post_ph, result, reason)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                row.get("ts_utc"), row.get("action","dose"), row.get("volume_ml"),
                row.get("duration_ms"), row.get("pre_ph"), row.get("post_ph"),
                row.get("result","ok"), row.get("reason")
            )
        )
    rowid = cur.lastrowid or 0
    conn.commit()
    return int(rowid)

def _update_post_ph(rowid: int, post_ph: Optional[float]) -> None:
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("UPDATE ph_dose_log SET post_ph=? WHERE id=?", (post_ph, rowid))
        conn.commit()

def _is_dose_effective(pre_ph: Optional[float], post_ph: Optional[float], min_delta: float = 0.02, direction: str = "up") -> bool:
    """Check if dose produced measurable pH change in the correct direction. 
    For pH up dosing: post_ph must be > pre_ph by at least min_delta.
    For pH down dosing: post_ph must be < pre_ph by at least min_delta.
    Returns False if pH moved in wrong direction (indicates failed dose due to air bubble).
    """
    if pre_ph is None or post_ph is None:
        return False  # Can't verify without both readings
    delta = post_ph - pre_ph
    
    if direction.lower() == "up":
        # For pH up: pH should increase
        return delta >= min_delta
    elif direction.lower() == "down":
        # For pH down: pH should decrease  
        return delta <= -min_delta
    else:
        # Fallback: check absolute change
        return abs(delta) >= min_delta

def _mark_dose_faulty_and_retry(rowid: int, pre_ph: float, post_ph: float) -> None:
    """Mark dose as faulty (no measurable pH change) and queue a retry.
    Called when dose didn't produce expected pH spike (likely air bubble in line).
    """
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            # Mark original dose as faulty in notes/reason field
            conn.execute(
                "UPDATE ph_dose_log SET reason = reason || ' [FAULTY: no_ph_delta]' WHERE id=?",
                (rowid,)
            )
            # Create a retry dose entry (mark as 'retry_attempt'), using configured initial ml
            retry_ml = _settings_get_float("dosing.ph_up_initial_ml", 0.1)
            now_utc = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT INTO ph_dose_log(ts_utc, action, volume_ml, result, reason)
                   VALUES(?, ?, ?, ?, ?)""",
                (now_utc, "dose", retry_ml, "pending_retry", f"retry_for_faulty_dose_id_{rowid}")
            )
            conn.commit()
        print(f"[pH Dose Validation] rowid={rowid} marked FAULTY (delta={abs(post_ph - pre_ph):.4f}), retry queued with {retry_ml} ml")
    except Exception as e:
        print(f"[pH Dose Validation] Error marking dose faulty: {e}")

def _recent_doses(limit: int = 5) -> List[Dict[str, Any]]:
    """Return recent complete dose log entries (post_ph must not be NULL).
    Filters incomplete entries where stabilization hasn't finished yet.
    """
    _ensure_tables()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        # Only return complete entries where post_ph has been populated
        cur.execute(
            "SELECT id, ts_utc, action, volume_ml, duration_ms, pre_ph, post_ph, result, reason FROM ph_dose_log WHERE post_ph IS NOT NULL ORDER BY id DESC LIMIT ?",
            (int(limit),)
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r[0], "ts_utc": r[1], "action": r[2], "volume_ml": r[3],
            "duration_ms": r[4], "pre_ph": r[5], "post_ph": r[6],
            "result": r[7], "reason": r[8]
        })
    return out

def _dose_events_range(start: Optional[str] = None, end: Optional[str] = None, hours: Optional[int] = None, limit: int = 2000) -> List[Dict[str, Any]]:
    """Get dose events within a range. Prefers start/end over hours."""
    _ensure_tables()
    if start and end:
        # Use explicit range
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
        if start_dt >= end_dt:
            raise ValueError("start must be before end")
        cutoff = start_dt.isoformat()
        upper = end_dt.isoformat()
    else:
        # Fallback to hours
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours or 24)))).isoformat()
        upper = datetime.now(timezone.utc).isoformat()
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts_utc, action, volume_ml, duration_ms, pre_ph, post_ph, result, reason
            FROM ph_dose_log
            WHERE ts_utc >= ? AND ts_utc < ?
            ORDER BY ts_utc ASC
            LIMIT ?
            """,
            (cutoff, upper, int(limit))
        )
        rows = cur.fetchall()
    events = []
    for r in rows:
        duration_ms = r[3] if r[3] is not None else 0
        seconds = round((duration_ms or 0)/1000.0, 3)
        guard = r[7] if (r[6] == 'blocked' and r[7]) else None
        events.append({
            "ts": r[0],
            "seconds": seconds,
            "volume_ml": r[2],
            "reason": r[1],  # action field maps to reason ('dose' with reason string below)
            "ph_before": r[4],
            "ph_after": r[5],
            "guard_triggered": guard,
            "result": r[6],
            "action": r[1],
            "detail": r[7]
        })
    return events

def _dose_daily_range(start: Optional[str] = None, end: Optional[str] = None, days: Optional[int] = None) -> List[Dict[str, Any]]:
    """Aggregate dose events by day (UTC). Prefers start/end over days."""
    _ensure_tables()
    if start and end:
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
        if start_dt >= end_dt:
            raise ValueError("start must be before end")
        start_day = start_dt.date().isoformat()
        end_day = end_dt.date().isoformat()
    else:
        # Fallback to days
        start_day = (datetime.now(timezone.utc) - timedelta(days=max(1, int(days or 7))-1)).date().isoformat()
        end_day = datetime.now(timezone.utc).date().isoformat()
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT substr(ts_utc,1,10) AS day, SUM(COALESCE(volume_ml,0)) AS total_ml
            FROM ph_dose_log
            WHERE result='ok' AND substr(ts_utc,1,10) >= ? AND substr(ts_utc,1,10) <= ?
            GROUP BY day
            ORDER BY day ASC
            """,
            (start_day, end_day)
        )
        rows = cur.fetchall()
    return [{"day": r[0], "total_ml": float(r[1] or 0.0)} for r in rows]


def _dose_daily(days: int) -> List[Dict[str, Any]]:
    """Compatibility shim for tests: returns last N days (UTC) aggregated."""
    return _dose_daily_range(days=int(days))

def _today_total_ml(now_dt: datetime) -> float:
    _ensure_tables()
    # Use SA timezone if available from settings
    try:
        from app.settings import SA_TZ
    except Exception:
        SA_TZ = timezone.utc
    local_now = now_dt.astimezone(SA_TZ)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_local.astimezone(timezone.utc)
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        # Check unified dose_events table first (convert seconds to ml using calibrated rate)
        cur.execute(
            "SELECT COALESCE(SUM(seconds),0) FROM dose_events WHERE pump='ph_up' AND blocked_by IS NULL AND ts >= ?",
            (int(start_utc.timestamp()),)
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            # Convert seconds to ml using calibrated rate from settings
            total_seconds = float(row[0])
            try:
                from app.settings import get_setting_key
                ml_per_sec = float(get_setting_key("dosing.ph_up_ml_per_sec", "0") or "0")
                if ml_per_sec > 0:
                    return total_seconds * ml_per_sec
            except Exception:
                pass
        # Fallback to old ph_dose_log table
        cur.execute(
            "SELECT COALESCE(SUM(volume_ml),0) FROM ph_dose_log WHERE result='ok' AND ts_utc >= ?",
            (start_utc.isoformat(),)
        )
        val = cur.fetchone()[0]
        return float(val or 0.0)

def _last_ok_ts() -> Optional[datetime]:
    """Get timestamp of last successful pH dose from ph_dose_log table.
    This is the PRIMARY source for interval guard since _perform_dose logs here."""
    _ensure_tables()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        # PRIMARY: Check ph_dose_log table (where _perform_dose logs successful doses)
        cur.execute("SELECT ts_utc FROM ph_dose_log WHERE result='ok' ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            try:
                return datetime.fromisoformat(row[0]).astimezone(timezone.utc)
            except Exception:
                pass
        # FALLBACK: Check unified dose_events table (for backward compatibility)
        cur.execute("SELECT ts FROM dose_events WHERE pump='ph_up' AND blocked_by IS NULL ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            try:
                return datetime.fromtimestamp(row[0], tz=timezone.utc)
            except Exception:
                pass
        return None

# --- Sensors/Settings helpers ------------------------------------------------
def _get_latest_ph() -> Tuple[Optional[float], Optional[int]]:
    """Return latest pH and its unix ts from readings table."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT ts, ph FROM readings ORDER BY ts DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                # Row may have ph NULL; treat as None
                return (float(row[1]) if row[1] is not None else None, int(row[0]))
    except Exception:
        pass
    return (None, None)

def _get_latest_ec() -> Tuple[Optional[float], Optional[int]]:
    """Return latest EC and its unix ts from readings table."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT ts, ec_ms_cm FROM readings ORDER BY ts DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                return (float(row[1]) if row[1] is not None else None, int(row[0]))
    except Exception:
        pass
    return (None, None)

def _get_ec_near(ts_unix: int, window_s: int = 600) -> Optional[float]:
    """Fetch EC nearest to a given timestamp within a window (seconds)."""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT ts, ec_ms_cm FROM readings WHERE ts BETWEEN ? AND ? ORDER BY ABS(ts-?) ASC LIMIT 1",
                (int(ts_unix - window_s), int(ts_unix + window_s), int(ts_unix))
            )
            row = cur.fetchone()
            if row:
                return float(row[1]) if row[1] is not None else None
    except Exception:
        pass
    return None

def _volume_ml_from_ms(duration_ms: int) -> Optional[float]:
    """Compute volume_ml using calibration rate; return None if not configured (>0)."""
    try:
        rate = _settings_get_float("dosing.ph_up_ml_per_sec", 25.0)
        if rate is None or rate <= 0:
            return None
        seconds = max(0.0, float(duration_ms or 0) / 1000.0)
        return round(seconds * rate, 3)
    except Exception:
        return None

def _settings_get(key: str, default: str) -> str:
    try:
        from app.settings import get_setting_key
        v = get_setting_key(key, default)
        return v if v is not None else default
    except Exception:
        return default

def _settings_get_float(key: str, default: float) -> float:
    try:
        return float(_settings_get(key, str(default)))
    except Exception:
        return default

def _settings_get_int(key: str, default: int) -> int:
    try:
        return int(float(_settings_get(key, str(default))))
    except Exception:
        return default

# --- Guards ------------------------------------------------------------------
def _compute_guards(now: float) -> Dict[str, Any]:
    from app.relays_core import get_estop_status
    ph, ts = _get_latest_ph()
    # Stale if no pH value OR no timestamp OR last sample older than 90s
    sensor_stale = (ph is None) or (not ts) or ((now - ts) > 90)
    # EC baseline guard
    ec_val, _ = _get_latest_ec()
    ec_baseline_min = _settings_get_float("dosing.ec_baseline_min", 0.2)
    ec_baseline_low = (ec_val is None) or (ec_val < ec_baseline_min)

    # Out-of-band stabilization guard: wait for pH to settle before re-attempting
    def _last_out_of_band_ts() -> Optional[datetime]:
        """Find the most recent time pH went out of target band."""
        try:
            targets = {
                "low": _settings_get_float("targets.ph_low", 5.8),
                "high": _settings_get_float("targets.ph_high", 6.2),
            }
            with sqlite3.connect(str(DB_PATH)) as conn:
                cur = conn.cursor()
                # Find most recent reading outside band
                cur.execute("""
                    SELECT ts FROM readings 
                    WHERE ph IS NOT NULL AND (ph < ? OR ph > ?)
                    ORDER BY ts DESC LIMIT 1
                """, (targets["low"], targets["high"]))
                row = cur.fetchone()
                if not row or not row[0]:
                    return None
                # Convert unix timestamp to datetime
                return datetime.fromtimestamp(row[0], tz=timezone.utc)
        except Exception:
            return None

    stabilize_wait_s = _settings_get_int("dosing.ph_stabilization_window_s", 180)
    last_oob = _last_out_of_band_ts()
    since_last_oob = None
    out_of_band = False
    if last_oob:
        since_last_oob = int(datetime.now(timezone.utc).timestamp() - last_oob.timestamp())
        out_of_band = since_last_oob < stabilize_wait_s

    # Recent EC dose guard: wait for EC-induced pH drift to settle before dosing/learning
    def _last_ec_dose_ts() -> Optional[datetime]:
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cur = conn.cursor()
                cur.execute("SELECT ts_utc FROM ec_dose_log WHERE result='ok' ORDER BY id DESC LIMIT 1")
                row = cur.fetchone()
                if not row or not row[0]:
                    return None
                return datetime.fromisoformat(row[0]).astimezone(timezone.utc)
        except Exception:
            return None

    ec_wait = _settings_get_int("dosing.ph_wait_after_ec_s", 300)  # Wait 5min after EC dose (1 pH interval), not 15min
    last_ec = _last_ec_dose_ts()
    since_last_ec = None
    ec_settle = False
    if last_ec:
        since_last_ec = int(datetime.now(timezone.utc).timestamp() - last_ec.timestamp())
        ec_settle = since_last_ec < ec_wait

    # Min interval guard - 15min default for 2× hydraulic residence time (100L @ 20 LPM)
    last_ok = _last_ok_ts()
    min_interval = _settings_get_int("dosing.ph_min_interval_s", 900)
    since_last_ok = None
    interval_guard = False
    if last_ok:
        since_last_ok = int(datetime.now(timezone.utc).timestamp() - last_ok.timestamp())
        interval_guard = since_last_ok < min_interval

    # Daily cap guard
    today_ml = _today_total_ml(datetime.now(timezone.utc))
    daily_cap = _settings_get_float("dosing.ph_up_max_ml_per_day", 50.0)
    daily_guard = today_ml >= daily_cap if daily_cap > 0 else False

    # Reservoir > 0
    res_liters = _settings_get_float("general.reservoir_liters", 25.0)
    res_guard = res_liters <= 0

    return {
        "estop": bool(get_estop_status()),
        "safe_off": False,  # placeholder - no separate latch beyond E-STOP
        "sensor_stale": bool(sensor_stale),
        "interval": bool(interval_guard),
        "daily_cap": bool(daily_guard),
        "reservoir": bool(res_guard),
        "ec_baseline_low": bool(ec_baseline_low),
        "ec_settle": bool(ec_settle),
        "out_of_band": bool(out_of_band),
        "since_last_ok_s": since_last_ok,
        "since_last_ec_s": since_last_ec,
        "today_total_ml": today_ml,
        "min_interval_s": min_interval,
        "daily_cap_ml": daily_cap,
    }

# --- API ---------------------------------------------------------------------
@router.get("/api/ph/status")
def ph_status():
    now = time.time()
    ph_val, ts = _get_latest_ph()
    # Prefer scheduler setpoint + band tolerance if available
    band_tol = _settings_get_float("targets.ph_band", 0.2)
    setpoint = None
    try:
        # Lightweight read of current week setpoint from nutrient_schedule
        from datetime import datetime, timezone
        import sqlite3
        from pathlib import Path
        from app.schedule_api import DB_PATH as _DB
        # Compute current week (duplicate minimal logic)
        from app.settings import get_all_settings
        s = get_all_settings()
        date_str = s.get("general.grow_start_date", "")
        week_num = 1
        if date_str:
            try:
                start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                now_dt = datetime.now(timezone.utc)
                delta_days = (now_dt - start).days
                week_num = max(1, min(12, (delta_days // 7) + 1))
            except Exception:
                week_num = 1
        with sqlite3.connect(str(_DB)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT ph_low, ph_high FROM nutrient_schedule WHERE week = ?", (week_num,))
            row = cur.fetchone()
            if row and row[0] is not None and row[1] is not None:
                setpoint = ((float(row[0]) + float(row[1])) / 2.0)
    except Exception:
        setpoint = None
    if setpoint is not None:
        targets = {"low": round(setpoint - band_tol, 2), "high": round(setpoint + band_tol, 2)}
    else:
        targets = {
            "low": _settings_get_float("targets.ph_low", 5.8),
            "high": _settings_get_float("targets.ph_high", 6.2),
        }
    guards = _compute_guards(now)
    # Remaining cooldown helper
    since = guards.get("since_last_ok_s") or 0
    min_int = guards.get("min_interval_s") or 0
    remaining = int(max(0, min_int - since))
    # Last ok ts for reference
    last_ok = _last_ok_ts()
    recent = _recent_doses(50)
    try:
        from app.settings import get_setting_key
        from app.auto_control import should_automate
        maint_override = (get_setting_key("safety.maintenance_override", "false") or "false").lower() == "true"
        auto_enabled = should_automate("ph")  # NEW: Global AND pH-specific auto
    except Exception:
        maint_override = False
        auto_enabled = False
    # Learned ml per 1.0 pH (may be None)
    try:
        learned = _estimate_ml_per_pH(_get_latest_ec()[0])
    except Exception:
        learned = None
    # Holding reason (deterministic by guards + band), allow lock to signal cooldown
    holding_reason = _derive_holding_reason(ph_val, guards, targets)
    if not auto_enabled and holding_reason is None:
        holding_reason = "auto_disabled"
    if _dose_lock.locked() and holding_reason is None:
        holding_reason = "cooldown"
    # Surface safety-related parameters for UI transparency (canonical key set)
    # Canonical pH automation safety keys (single source of truth):
    #   dosing.ph_up_initial_ml
    #   dosing.ph_min_interval_s
    #   dosing.ph_max_predicted_delta_ph
    #   dosing.ph_stabilization_window_s
    #   dosing.ph_stabilization_delta_threshold
    # Backward compatibility: fall back to legacy duplicate keys if canonical missing.
    initial_ml = _settings_get_float("dosing.ph_up_initial_ml", 0.1)
    max_est_change = _settings_get_float("dosing.ph_max_predicted_delta_ph", _settings_get_float("safety.max_estimated_ph_change", 0.5))
    est_guard = (_settings_get("safety.estimated_change_guard", "true").lower() == "true")  # guard key retained in safety.* namespace
    # Relaxed defaults: shorter stabilization window and wider delta tolerance
    stabilize_wait_s = _settings_get_int("dosing.ph_stabilization_window_s", _settings_get_int("dosing.stabilize_wait_s", 180))
    stability_delta = _settings_get_float("dosing.ph_stabilization_delta_threshold", _settings_get_float("dosing.stability_delta", 0.05))
    stability_samples = _settings_get_int("dosing.stability_samples", 3)
    return {
        "ph": ph_val,
        "ts": ts,
        "targets": targets,
        "auto": {"enabled": bool(auto_enabled), "guard": None, "holding_reason": holding_reason, "learned_ml_per_pH": learned},
        "guards": guards,
        "recent": recent,
        "remaining_cooldown_s": remaining,
        "maintenance_override": maint_override,
        "last_dose_ts": int(last_ok.timestamp()) if last_ok else None,
        "safety": {
            "initial_ml": initial_ml,
            "estimated_change_guard": est_guard,
            "max_estimated_delta_ph": max_est_change,
            "stabilization": {
                "wait_s": stabilize_wait_s,
                "delta": stability_delta,
                "samples": stability_samples,
            }
        }
    }


def _dose_ms_from_ml(ml: float) -> Tuple[int, Optional[str]]:
    rate = _settings_get_float("dosing.ph_up_ml_per_sec", 25.0)
    max_single = _settings_get_float("dosing.ph_up_max_single_ml", 5.0)
    if ml <= 0:
        return 0, "ml_must_be_positive"
    if max_single > 0 and ml > max_single:
        return 0, "exceeds_max_single_ml"
    ms = int(1000.0 * (ml / max(0.0001, rate)))
    return max(0, ms), None


def _actuate_ph_up(duration_ms: int) -> Dict[str, Any]:
    from app.relays_core import set_dosing_ph_up
    # Active-low handled in relays_core
    try:
        print(f"[pH] GPIO LOW (ON) ms={duration_ms} on dosing_ph_up")
        on = set_dosing_ph_up(True, reason="ph_dose", force=True)
        if not on.get("changed") and not on.get("state"):
            # Could be blocked by estop or cooldown
            return {"ok": False, "reason": on.get("reason", "blocked")}
        time.sleep(max(0, duration_ms) / 1000.0)
        return {"ok": True}
    finally:
        # Always return HIGH (OFF)
        try:
            set_dosing_ph_up(False, reason="ph_dose", force=True)
            print("[pH] GPIO HIGH (OFF) dosing_ph_up")
        except Exception:
            pass


def _update_post_ph_with_flag(rowid: int, post_ph: Optional[float], stable: bool) -> None:
    """Update post_ph and add stability flag to reason field."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        # Get current reason and append stability info
        cur.execute("SELECT reason FROM ph_dose_log WHERE id=?", (rowid,))
        row = cur.fetchone()
        current_reason = row[0] if row else ""
        stability_flag = "; ph_stable" if stable else "; ph_unsettled"
        # current_reason is guaranteed to be a string (empty or actual value)
        new_reason = current_reason + stability_flag
        conn.execute("UPDATE ph_dose_log SET post_ph=?, reason=? WHERE id=?", (post_ph, new_reason, rowid))
        conn.commit()


# Stabilization constants
SAMPLE_RETENTION_MULTIPLIER = 2  # Keep 2x stability_samples for trend analysis


def _background_observe_and_update(rowid: int, baseline_ts_unix: Optional[int], max_wait_s: int):
    """Two-phase stabilization: detect immediate spike (delivery), then wait for settling (learning).
    
    PHASE 1 (0-60s): Early spike detection to verify solution delivery
    - Poll every 5s for first 60s
    - If pH rises by >= 0.02 from pre_ph, mark delivery as confirmed
    - This proves pump worked and solution reached reservoir
    
    PHASE 2 (60s-300s): Settling observation for learning
    - Wait for pH to stabilize (min 180s total)
    - Check last N samples for stability (range < 0.05)
    - Record final post_ph for learning effectiveness
    - Validate dose effectiveness: if final change < 0.02, mark faulty and retry
    
    This fixes the issue where the system doesn't see the immediate spike
    and incorrectly treats successful doses as ineffective.
    """
    try:
        # Configuration
        # Use canonical stabilization keys with fallback to legacy duplicates
        # Require ~5 minutes by default to observe the settled effect
        stabilize_wait_s = _settings_get_int("dosing.ph_stabilization_window_s", _settings_get_int("dosing.stabilize_wait_s", 300))
        stability_delta = _settings_get_float("dosing.ph_stabilization_delta_threshold", _settings_get_float("dosing.stability_delta", 0.05))
        stability_samples = _settings_get_int("dosing.stability_samples", 3)  # sample count remained unchanged
        dose_effectiveness_threshold = _settings_get_float("dosing.dose_effectiveness_threshold", 0.02)  # Min pH change to consider dose effective
        
        # NEW: Phase 1 early spike detection
        early_spike_window_s = _settings_get_int("dosing.ph_early_spike_window_s", 60)  # Check for spike in first 60s
        early_spike_threshold = _settings_get_float("dosing.ph_early_spike_threshold", 0.02)  # Min rise to confirm delivery
        early_poll_interval = 5.0  # Fast polling for spike detection
        settling_poll_interval = 10.0  # Slower polling after spike confirmed
        
        deadline = time.time() + max(0, max_wait_s)
        stabilize_deadline = time.time() + stabilize_wait_s
        early_spike_deadline = time.time() + early_spike_window_s
        last_seen_ts = baseline_ts_unix or 0
        
        # Get pre-dose pH for validation
        pre_dose_row = None
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT pre_ph FROM ph_dose_log WHERE id=?", (rowid,))
            pre_dose_row = cur.fetchone()
        pre_ph = pre_dose_row[0] if pre_dose_row else None
        
        # Collect pH samples for stability check
        samples = []
        delivery_confirmed = False  # True only when spike is observed
        delivery_window_expired = False  # Becomes True after early window passes
        poll_interval = early_poll_interval  # Start with fast polling
        
        print(f"[pH Stabilization] Starting 2-phase observation for rowid={rowid} (pre_ph={pre_ph:.3f})")
        print(f"[pH Stabilization]  Phase 1: Early spike detection (0-{early_spike_window_s}s, threshold={early_spike_threshold})")
        print(f"[pH Stabilization]  Phase 2: Settling observation ({early_spike_window_s}s-{stabilize_wait_s}s, delta={stability_delta})")
        
        while time.time() < deadline:
            ph_val, ts = _get_latest_ph()
            
            if ts and ts > last_seen_ts:
                # New reading available
                samples.append({"ph": ph_val, "ts": ts})
                last_seen_ts = ts
                
                # Keep recent samples for stability check (retain extra for trend analysis)
                max_samples = stability_samples * SAMPLE_RETENTION_MULTIPLIER
                if len(samples) > max_samples:
                    samples = samples[-max_samples:]
                
                # PHASE 1: Early spike detection (first 60s) - confirms solution delivery
                if not delivery_confirmed and time.time() < early_spike_deadline:
                    # If pre_ph is missing (rare), seed it from the first observed sample
                    if pre_ph is None and ph_val is not None:
                        pre_ph = ph_val
                    if pre_ph is not None and ph_val is not None:
                        delta = ph_val - pre_ph
                        if delta >= early_spike_threshold:
                            # Spike detected! Solution reached reservoir
                            delivery_confirmed = True
                            poll_interval = settling_poll_interval  # Slow down polling after confirmation
                            print(f"[pH Stabilization] ✓ DELIVERY CONFIRMED for rowid={rowid}: spike detected! pH {pre_ph:.3f} → {ph_val:.3f} (Δ={delta:.3f})")
                            print(f"[pH Stabilization] Switching to Phase 2: waiting for settling to measure final effect...")
                
                # Transition: Early window expired without spike — continue, but keep unconfirmed
                if not delivery_confirmed and not delivery_window_expired and time.time() >= early_spike_deadline:
                    delivery_window_expired = True
                    poll_interval = settling_poll_interval
                    print(f"[pH Stabilization] ⚠ No early spike detected for rowid={rowid} within {early_spike_window_s}s")
                    print(f"[pH Stabilization] Will treat as unconfirmed delivery; if effect is zero, will mark faulty and retry")
                
                # PHASE 2: Stability check (after minimum settling time)
                if time.time() >= stabilize_deadline and len(samples) >= stability_samples:
                    # Check if last N samples are stable (low range = max - min)
                    recent = [s["ph"] for s in samples[-stability_samples:] if s["ph"] is not None]
                    if len(recent) >= stability_samples:
                        min_ph = min(recent)
                        max_ph = max(recent)
                        sample_range = max_ph - min_ph
                        
                        if sample_range <= stability_delta:
                            # Stable! Record the average of recent samples
                            stable_ph = sum(recent) / len(recent)
                            print(f"[pH Stabilization] rowid={rowid} STABLE: ph={stable_ph:.3f}, range={sample_range:.4f}")
                            _update_post_ph_with_flag(rowid, round(stable_ph, 3), stable=True)
                            
                            # Validate dose effectiveness: check if pH changed sufficiently in correct direction (up)
                            if pre_ph is not None:
                                delta = stable_ph - pre_ph
                                is_effective = _is_dose_effective(pre_ph, stable_ph, dose_effectiveness_threshold, direction="up")
                                if not is_effective:
                                    if delivery_confirmed:
                                        # Delivery happened (spike seen) but net effect small — treat as low-effect, no retry
                                        print(f"[pH Dose Validation] rowid={rowid} LOW EFFECT: delta={delta:.4f} (< {dose_effectiveness_threshold}) but spike confirmed; skipping retry, keep for learning")
                                        try:
                                            with sqlite3.connect(str(DB_PATH)) as conn:
                                                conn.execute(
                                                    "UPDATE ph_dose_log SET reason = reason || ' [LOW_EFFECT]' WHERE id=?",
                                                    (rowid,),
                                                )
                                                conn.commit()
                                        except Exception:
                                            pass
                                    else:
                                        print(f"[pH Dose Validation] rowid={rowid} INEFFECTIVE: delta={delta:.4f} (expected >= {dose_effectiveness_threshold}), pre={pre_ph:.3f}, post={stable_ph:.3f}")
                                        _mark_dose_faulty_and_retry(rowid, pre_ph, stable_ph)
                                else:
                                    print(f"[pH Dose Validation] rowid={rowid} EFFECTIVE: delta={delta:.4f}, learning updated")
                            return
                        else:
                            print(f"[pH Stabilization] rowid={rowid} still settling: range={sample_range:.4f} > {stability_delta}")
            
            time.sleep(poll_interval)
        
        # Timeout: record last value as unsettled
        ph_final, ts_final = _get_latest_ph()
        if ph_final is not None:
            print(f"[pH Stabilization] rowid={rowid} TIMEOUT (unsettled): last_ph={ph_final:.3f}")
            _update_post_ph_with_flag(rowid, ph_final, stable=False)
        else:
            print(f"[pH Stabilization] rowid={rowid} TIMEOUT: no pH reading available")
            
            
    except Exception as e:
        print(f"[pH Stabilization] Error for rowid={rowid}: {e}")


def _perform_dose(body: Dict[str, Any]) -> Dict[str, Any]:
    """Shared dose performer used by endpoint and automation.
    Accepts { ml?: number, ms?: number, seconds?: number, reason?: string, force?: bool }
    Returns a JSON-serializable dict.
    """
    ml = body.get("ml")
    ms = body.get("ms")
    seconds = body.get("seconds")
    reason = str(body.get("reason", "manual"))[:200]
    force_req = bool(body.get("force", False))
    rowid: int = 0
    nonblocking = bool(body.get("nonblocking", False))

    # Prefer ml if provided (convert to ms using calibration), but log-time ml always derived from ms
    if ml is not None:
        try:
            ml = float(ml)
        except Exception:
            return {"http_status": 422, "ok": False, "error": "invalid_ml"}
        ms_calc, err = _dose_ms_from_ml(ml)
        if err:
            return {"http_status": 422, "ok": False, "error": err}
        duration_ms = ms_calc
    else:
        # Accept either ms or seconds
        try:
            if ms is not None:
                duration_ms = int(round(float(ms)))
            elif seconds is not None:
                duration_ms = int(round(float(seconds) * 1000.0))
            else:
                duration_ms = 0
        except Exception:
            return {"http_status": 422, "ok": False, "error": "invalid_duration"}
    # Compute volume at log-time using calibration (nullable if no calibration)
    volume_ml = _volume_ml_from_ms(duration_ms)
    # Clamp duration
    MAX_MS = int(_settings_get_int("dosing.ph_up_max_ms", 5000))
    if duration_ms <= 0 or duration_ms > MAX_MS:
        return {"http_status": 422, "ok": False, "error": "invalid_duration_ms", "max_ms": MAX_MS}

    # EXPERIMENTAL: Pre-dose estimated pH change guard
    # Block if estimated pH change exceeds threshold (default 0.5 pH)
    # This helps prevent overdosing when concentration is high or reservoir is small
    # Constants for the guard
    # SAFETY: User's system spec: 1ml pH Up = roughly 1 pH unit change
    # Start conservative at 0.1ml doses, let learning algorithm build up gradually
    DEFAULT_ML_PER_PH_FALLBACK = 1.0  # User spec: 1ml raises pH by 1.0
    MIN_ML_PER_PH = 0.01  # Minimum divisor to prevent division by zero
    
    def _ec_compensated_ml_per_pH(base_ml_per_pH: float, ec_current: Optional[float]) -> float:
        """Scale ml_per_pH based on EC to reflect reduced effectiveness at higher ionic strength.
        factor = clamp(1 + slope * (ec - ref), [min_factor, max_factor])
        Settings (with safe defaults):
          - dosing.ph_up_ml_per_pH_ref_ec_mscm (default 1.0)
          - dosing.ph_up_ml_per_pH_ec_slope (default 0.0 → disabled)
          - dosing.ph_up_ml_per_pH_ec_min_factor (default 0.5)
          - dosing.ph_up_ml_per_pH_ec_max_factor (default 2.0)
        """
        try:
            if ec_current is None:
                return base_ml_per_pH
            ref = _settings_get_float("dosing.ph_up_ml_per_pH_ref_ec_mscm", 1.0)
            slope = _settings_get_float("dosing.ph_up_ml_per_pH_ec_slope", 0.0)
            fmin = _settings_get_float("dosing.ph_up_ml_per_pH_ec_min_factor", 0.5)
            fmax = _settings_get_float("dosing.ph_up_ml_per_pH_ec_max_factor", 2.0)
            factor = 1.0 + slope * (float(ec_current) - ref)
            if fmin > fmax:
                fmin, fmax = fmax, fmin
            factor = max(fmin, min(fmax, factor))
            return max(0.001, float(base_ml_per_pH) * factor)
        except Exception:
            return base_ml_per_pH
    
    pre_ph_for_check, _ = _get_latest_ph()
    if volume_ml is not None and volume_ml > 0 and pre_ph_for_check is not None:
        try:
            estimated_change_guard = (
                _settings_get("safety.estimated_change_guard", "true").lower() == "true"
            )
            if estimated_change_guard:
                max_estimated_change = _settings_get_float("safety.max_estimated_ph_change", 0.5)
                _ec = _get_latest_ec()[0]
                ml_per_pH = _estimate_ml_per_pH(_ec) or DEFAULT_ML_PER_PH_FALLBACK
                ml_per_pH = _ec_compensated_ml_per_pH(ml_per_pH, _ec)
                # Estimated pH change = volume_ml / ml_per_pH
                estimated_delta = volume_ml / max(MIN_ML_PER_PH, ml_per_pH)
                if estimated_delta > max_estimated_change:
                    ts_iso = datetime.now(timezone.utc).isoformat()
                    rowid = _log_row({
                        "ts_utc": ts_iso, "action": "dose", "volume_ml": float(volume_ml),
                        "duration_ms": int(duration_ms), "pre_ph": pre_ph_for_check, "post_ph": None,
                        "result": "blocked", "reason": f"estimated_change_too_large ({estimated_delta:.2f} > {max_estimated_change:.2f})"
                    })
                    return {
                        "http_status": 409, "ok": False, "blocked": True,
                        "reasons": ["estimated_change_too_large"],
                        "estimated_delta_ph": round(estimated_delta, 3),
                        "max_allowed": max_estimated_change,
                        "suggestion": "Reduce dose size, verify reservoir volume, or check solution concentration",
                        "rowid": rowid
                    }
        except Exception as e:
            print(f"[pH] Estimated change guard error (continuing): {e}")

    # Guards
    g = _compute_guards(time.time())
    guard_map = {
        "estop": g["estop"],
        "safe_off": g["safe_off"],
        "sensor_stale": g["sensor_stale"],
        "interval": g["interval"],
        "daily_cap": g["daily_cap"],
        "reservoir": g["reservoir"],
    }
    
    # Check if we're in auto mode - some guards only apply in auto mode
    is_auto_mode = False
    try:
        from app.auto_control import is_global_auto_enabled
        is_auto_mode = is_global_auto_enabled()
    except Exception:
        is_auto_mode = True  # Fail-safe: assume auto mode if can't check
    
    # ALWAYS-ON guards: estop, safe_off, reservoir (hard safety limits)
    # AUTO-ONLY guards: interval, daily_cap, sensor_stale (operational limits)
    always_on_guards = {"estop", "safe_off", "reservoir"}
    auto_only_guards = {"interval", "daily_cap", "sensor_stale"}
    
    if is_auto_mode:
        # All guards active in auto mode
        blocked_reasons = [k for k,v in guard_map.items() if v]
    else:
        # Manual mode: only always-on guards enforced
        blocked_reasons = [k for k,v in guard_map.items() if v and k in always_on_guards]
    
    # Force bypass (testing only) for interval/daily_cap guards - only applies in auto mode
    try:
        from app.settings import get_setting_key
        allow_force = (get_setting_key("safety.allow_force", "false") or "false").lower() == "true"
        maint_override = (get_setting_key("safety.maintenance_override", "false") or "false").lower() == "true"
        allow_stale_on_override = (get_setting_key("safety.allow_stale_on_override", "false") or "false").lower() == "true"
    except Exception:
        allow_force = False
        maint_override = False
        allow_stale_on_override = False
    if is_auto_mode and (maint_override or (force_req and allow_force)):
        # Under overrides in auto mode, allow bypassing interval and daily caps.
        # Stale-sensor bypass is only permitted when BOTH maintenance_override is true
        # AND safety.allow_stale_on_override is explicitly enabled (test-only).
        bypass = {"interval", "daily_cap"}
        if maint_override and allow_stale_on_override:
            bypass.add("sensor_stale")
        # Still enforce hard safety guards: estop, safe_off, reservoir
        blocked_reasons = [r for r in blocked_reasons if r not in bypass]
    ts_iso = datetime.now(timezone.utc).isoformat()

    pre_ph, pre_ts = _get_latest_ph()

    # Hard guardrail: disallow pH-Up when pH is already above the safe high threshold
    try:
        # Use targets.ph_high if configured; otherwise use an absolute 6.6 ceiling
        # Use scheduler-derived high if available, else settings
        if setpoint is not None:
            ph_high = max(setpoint + band_tol, _settings_get_float("targets.ph_high", 6.2))
        else:
            ph_high = _settings_get_float("targets.ph_high", 6.2)
        hard_hi = max(6.6, ph_high)
        if (pre_ph is not None) and (pre_ph >= hard_hi):
            ts_iso = datetime.now(timezone.utc).isoformat()
            rowid = _log_row({
                "ts_utc": ts_iso, "action": "dose", "volume_ml": None if volume_ml is None else float(volume_ml),
                "duration_ms": int(duration_ms), "pre_ph": pre_ph, "post_ph": None,
                "result": "blocked", "reason": f"ph_high_guard ({pre_ph:.2f} >= {hard_hi:.2f})"
            })
            return {"http_status": 409, "ok": False, "blocked": True, "reasons": ["ph_high_guard"], "rowid": rowid}
    except Exception:
        pass

    if blocked_reasons:
        # Provide structured reason and remaining cooldown if applicable
        remaining = None
        if guard_map.get("interval"):
            since = guard_map.get("since_last_ok_s") or 0
            min_int = guard_map.get("min_interval_s") or 0
            remaining = int(max(0, min_int - since))
        rowid = _log_row({
            "ts_utc": ts_iso, "action": "dose", "volume_ml": None if volume_ml is None else float(volume_ml),
            "duration_ms": int(duration_ms), "pre_ph": pre_ph, "post_ph": None,
            "result": "blocked", "reason": ",".join(blocked_reasons)
        })
        result = {"ok": False, "blocked": True, "reasons": blocked_reasons, "rowid": rowid}
        if remaining is not None:
            result.update({"reason": "cooldown", "remaining_cooldown_s": remaining})
        return {"http_status": 409, **result}

    # Concurrency control: always use non-blocking lock acquisition to prevent blocking the API server
    # and to avoid potential deadlocks in hardware control operations (both in tests and production).
    acquired = _dose_lock.acquire(blocking=False)
    if not acquired:
        # Lock already held: treat as busy regardless of nonblocking flag
        rowid = _log_row({
            "ts_utc": ts_iso, "action": "dose", "volume_ml": None if volume_ml is None else float(volume_ml),
            "duration_ms": int(duration_ms), "pre_ph": pre_ph, "post_ph": None,
            "result": "blocked", "reason": "busy"
        })
        return {"http_status": 409, "ok": False, "blocked": True, "reasons": ["busy"], "reason": "cooldown", "rowid": rowid}

    try:
        # Actuate pump
        act = _actuate_ph_up(int(duration_ms))
        if not act.get("ok"):
            rowid = _log_row({
                "ts_utc": ts_iso, "action": "dose", "volume_ml": None if volume_ml is None else float(volume_ml),
                "duration_ms": int(duration_ms), "pre_ph": pre_ph, "post_ph": None,
                "result": "error", "reason": act.get("reason","error")
            })
            return {"http_status": 500, "ok": False, "error": act.get("reason","error"), "rowid": rowid}
    finally:
        if acquired:
            try:
                _dose_lock.release()
            except Exception:
                pass

    # Success path: log ok and schedule observation to capture post_ph
    rowid = _log_row({
        "ts_utc": ts_iso, "action": "dose", "volume_ml": None if volume_ml is None else float(volume_ml),
        "duration_ms": int(duration_ms), "pre_ph": pre_ph, "post_ph": None,
        "result": "ok", "reason": ("maintenance_override; " + reason) if maint_override else (("force_bypass; " + reason) if (force_req and allow_force) else reason)
    })

    # UNIFIED LOGGING: Also insert into dose_events table for unified analytics
    # This ensures interval guard and UI see the dose in both tables
    try:
        dose_seconds = round(duration_ms / 1000.0, 3)
        ts_unix = int(datetime.fromisoformat(ts_iso.replace('Z', '+00:00')).timestamp())
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """INSERT INTO dose_events (pump, ts, seconds, reason, blocked_by, pre_ph, pre_ec, post_ph)
                   VALUES (?, ?, ?, ?, NULL, ?, NULL, NULL)""",
                ("ph_up", ts_unix, dose_seconds, reason, pre_ph)
            )
            conn.commit()
    except Exception as e:
        print(f"[pH] Warning: Failed to insert into dose_events: {e}")

    # Schedule background observe to update post_ph with next sample (avoid request blocking)
    observe_s = max(1, min(1800, _settings_get_int("dosing.observe_s_after_dose", 600)))
    threading.Thread(target=_background_observe_and_update, args=(rowid, pre_ts, observe_s), daemon=True).start()

    return {"ok": True, "rowid": rowid, "pre_ph": pre_ph, "volume_ml": None if volume_ml is None else float(volume_ml), "duration_ms": int(duration_ms), "clamped_ms": min(duration_ms, MAX_MS), "override": bool(maint_override or (force_req and allow_force))}


@router.post("/api/ph/dose")
def ph_dose(body: Dict[str, Any] = Body(...)):
    """Manual dose endpoint.
    Accepts { ml?: number, ms?: number, reason?: string }
    """
    res = _perform_dose(body)
    if res.get("http_status"):
        code = int(res.pop("http_status"))
        return JSONResponse(status_code=code, content=res)
    return res


def _estimate_ml_per_pH(ec_current: Optional[float]) -> Optional[float]:
    """Estimate ml required to raise 1.0 pH based on recent successful doses.
    Uses rows where volume_ml, pre_ph and post_ph exist, filters to reasonable deltas, and
    ignores events where EC near dose time is below baseline.
    Returns a conservative default if not enough data.
    """
    baseline = _settings_get_float("dosing.ec_baseline_min", 0.2)
    # SAFETY: User's system spec: 1ml pH Up solution = roughly 1 pH unit change
    # Concentration is calibrated to the specific reservoir size
    # This is the default used for learning when no historical data exists
    default_ml_per_pH = _settings_get_float("dosing.ph_up_ml_per_pH_default", 1.0)  # User spec: 1ml = 1 pH
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT ts_utc, volume_ml, pre_ph, post_ph
                FROM ph_dose_log
                WHERE result='ok' AND volume_ml IS NOT NULL AND pre_ph IS NOT NULL AND post_ph IS NOT NULL
                    AND (reason IS NULL OR (reason NOT LIKE '%unsettled%' AND reason NOT LIKE '%FAULTY%'))
                ORDER BY id DESC LIMIT 50
                """
            )
            rows = cur.fetchall()
        total_ml = 0.0
        total_dpH = 0.0
        num_valid = 0
        for ts_iso, ml, pre, post in rows:
            try:
                dpH = float(post) - float(pre)
                if ml is None:
                    continue
                ml = float(ml)
                # Filter to reasonable positive deltas (avoid noise/overshoot)
                # Require >= 0.005 pH change (5 millivolts) to reduce noise from small measurement jitter
                if dpH <= 0 or dpH > 0.6 or abs(dpH) < 0.005:
                    continue
                # Filter by EC near dose time
                try:
                    ts = int(datetime.fromisoformat(ts_iso.replace('Z', '+00:00')).timestamp())
                except Exception:
                    continue
                ec_near = _get_ec_near(ts)
                if ec_near is None or ec_near < baseline:
                    continue
                total_ml += ml
                total_dpH += dpH
                num_valid += 1
            except Exception:
                continue
        if total_dpH > 0.02 and total_ml > 0 and num_valid >= 2:
            est = float(total_ml / total_dpH)  # ml for 1.0 pH
            # Clamp to [1.5,50] ml per 1.0 pH — conservative range given user spec of ~1ml = 1 pH
            # Upper bound reduced from 100 to prevent learning runaway from low-effect doses
            est = max(1.5, min(50.0, est))
            return est
    except Exception:
        pass
    return default_ml_per_pH


def _derive_holding_reason(ph_val: Optional[float], guards: Dict[str, Any], targets: Dict[str, float]) -> Optional[str]:
    """Priority order: estop → reservoir → safe_off → stale → ec_baseline_low → daily_cap → interval → above_high → None"""
    g = guards or {}
    if g.get("estop"):
        return "estop"
    if g.get("reservoir"):
        return "reservoir"
    if g.get("safe_off"):
        return "safe_off"
    if g.get("sensor_stale"):
        return "stale"
    if g.get("ec_baseline_low"):
        return "ec_baseline_low"
    if g.get("ec_settle"):
        return "ec_settle"
    if g.get("daily_cap"):
        return "daily_cap"
    if g.get("interval"):
        return "cooldown"
    try:
        if ph_val is not None and (ph_val > float(targets.get("high", 6.2))):
            return "above_high"
    except Exception:
        pass
    return None


def _set_auto_block(reason: str) -> None:
    """Track last auto holding reason and simple backoff counters."""
    global _auto_last_holding_reason, _auto_last_block, _auto_last_block_count
    try:
        reason = str(reason)
    except Exception:
        reason = "unknown"
    _auto_last_holding_reason = reason
    if _auto_last_block == reason:
        _auto_last_block_count += 1
    else:
        _auto_last_block = reason
        _auto_last_block_count = 1
    
    # Backoff: if same non-interval guard repeats 3×, log once then skip one extra poll
    if _auto_last_block_count == 3 and reason not in ("cooldown", "above_high"):
        print(f"[AUTO pH] Backoff: {reason} repeated 3× — skipping one extra poll to reduce log spam")


def _print_auto_decision(action: str, ph: Optional[float], ec: Optional[float], targets: Dict[str, float], ml: float, guards: Dict[str, Any]) -> None:
    global _auto_last_decision
    try:
        ts = datetime.now(timezone.utc).isoformat()
        decision = {
            "timestamp": ts,
            "action": action,
            "ph": ph,
            "ec": ec,
            "dose_ml": round(ml, 3),
            "target_band": [targets.get('low'), targets.get('high')],
            "active_guards": [k for k, v in (guards or {}).items() if v]
        }
        _auto_last_decision = decision
        print(f"[AUTO pH] {ts} action={action} ph={ph} ec={ec} -> dose_ml={round(ml,3)} band=[{targets.get('low')},{targets.get('high')}] guards={ {k:v for k,v in (guards or {}).items() if v} }")
    except Exception:
        pass


def _auto_loop():
    global _auto_stop_evt, _auto_enabled_at, _auto_last_holding_reason, _auto_last_block, _auto_last_block_count
    poll_s = _settings_get_int("dosing.poll_interval_s", 30)
    margin = _settings_get_float("ph_auto.margin", 0.05)  # aim to stop slightly inside band
    step_min = _settings_get_float("dosing.ph_up_step_min_ml", 0.05)
    step_max = _settings_get_float("dosing.ph_up_step_max_ml", 10.0)
    safety = _settings_get_float("dosing.ph_up_safety_factor", 0.85)  # under-dose fraction (increased to 0.85 for more aggressive response)
    warmup_done = False
    skip_next_poll = False  # For backoff
    
    while _auto_stop_evt and not _auto_stop_evt.is_set():
        try:
            # NEW: Use unified auto-enable system
            try:
                from app.auto_control import should_automate
                if not should_automate("ph"):
                    _set_auto_block("auto_disabled")
                    time.sleep(poll_s)
                    continue
            except Exception:
                pass
            # Suppress automation when global maintenance override is active
            try:
                from app.settings import get_setting_key
                if (get_setting_key("safety.maintenance_override", "false") or "false").lower() == "true":
                    _set_auto_block("maintenance_override")
                    time.sleep(poll_s)
                    continue
            except Exception:
                pass
            # Backoff: skip one extra poll if same non-interval guard repeated 3×
            if skip_next_poll:
                skip_next_poll = False
                time.sleep(poll_s)
                continue
            
            now = time.time()
            ph_val, _ = _get_latest_ph()
            # Use same target logic as status endpoint: prefer schedule setpoint + band, fallback to settings
            band_tol = _settings_get_float("targets.ph_band", 0.2)
            setpoint = None
            try:
                from datetime import datetime, timezone
                import sqlite3
                from pathlib import Path
                from app.schedule_api import DB_PATH as _DB
                from app.settings import get_all_settings
                s = get_all_settings()
                date_str = s.get("general.grow_start_date", "")
                week_num = 1
                if date_str:
                    try:
                        start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        now_dt = datetime.now(timezone.utc)
                        delta_days = (now_dt - start).days
                        week_num = max(1, min(12, (delta_days // 7) + 1))
                    except Exception:
                        week_num = 1
                with sqlite3.connect(str(_DB)) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT ph_low, ph_high FROM nutrient_schedule WHERE week = ?", (week_num,))
                    row = cur.fetchone()
                    if row and row[0] is not None and row[1] is not None:
                        setpoint = ((float(row[0]) + float(row[1])) / 2.0)
            except Exception:
                setpoint = None
            if setpoint is not None:
                targets = {"low": round(setpoint - band_tol, 2), "high": round(setpoint + band_tol, 2)}
            else:
                targets = {
                    "low": _settings_get_float("targets.ph_low", 5.8),
                    "high": _settings_get_float("targets.ph_high", 6.2),
                }
            g = _compute_guards(now)
            if ph_val is None or g.get("sensor_stale"):
                _set_auto_block("stale")
                if _auto_last_block_count == 3:
                    skip_next_poll = True
                time.sleep(poll_s)
                continue
            # Warm-up: wait one poll interval after enabling
            if not warmup_done and _auto_enabled_at:
                if (now - _auto_enabled_at) < poll_s:
                    _set_auto_block("cooldown")
                    time.sleep(poll_s)
                    continue
                warmup_done = True
            
            # Check for pending retries (failed doses due to air bubbles, etc.)
            try:
                max_retry_attempts = _settings_get_int("dosing.ph_retry_max_attempts", 10)
                retry_spacing_s = _settings_get_int("dosing.ph_retry_spacing_s", 60)
                retry_observe_s = _settings_get_int("dosing.observe_s_after_retry", 60)
                attempts = 0

                while attempts < max_retry_attempts:
                    with sqlite3.connect(str(DB_PATH)) as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT id, reason FROM ph_dose_log WHERE result='pending_retry' ORDER BY id ASC LIMIT 1")
                        retry_row = cur.fetchone()
                        if not retry_row:
                            break

                        retry_id = retry_row[0]
                        retry_reason = retry_row[1] or ""
                        
                        # GUARD: Check if pH has already reached/exceeded setpoint - if so, abort retry
                        ph_val, _ = _get_latest_ph()
                        targets = {
                            "low": _settings_get_float("targets.ph_low", 5.8),
                            "high": _settings_get_float("targets.ph_high", 6.2),
                        }
                        setpoint = (targets["low"] + targets["high"]) / 2.0
                        if ph_val is not None and ph_val >= setpoint:
                            print(f"[pH Auto] Aborting retry id={retry_id}: pH {ph_val:.3f} already >= setpoint {setpoint:.3f}")
                            conn.execute("UPDATE ph_dose_log SET result='retry_aborted_at_target' WHERE id=?", (retry_id,))
                            conn.commit()
                            attempts += 1
                            continue
                        
                        # Mark as executing retry
                        conn.execute("UPDATE ph_dose_log SET result='executing_retry' WHERE id=?", (retry_id,))
                        conn.commit()
                        print(f"[pH Auto] Processing pending retry for dose id={retry_id}, attempt #{attempts+1} (bypassing interval guard)")

                        # Execute via shared performer to ensure consistent logging/locking
                        try:
                            # Escalate dose based on retry attempt count: 0.1, 0.15, 0.2, 0.25, 0.3...
                            # Each retry gets progressively stronger
                            base_ml = _settings_get_float("dosing.ph_up_initial_ml", 0.1)
                            escalation_factor = 1.0 + (0.5 * attempts)  # 1.0, 1.5, 2.0, 2.5...
                            retry_ml = base_ml * escalation_factor
                            step_max = _settings_get_float("dosing.ph_up_step_max_ml", 0.5)
                            retry_ml = min(retry_ml, step_max)  # cap at step_max
                            
                            print(f"[pH Auto] Retry dose #{attempts+1}: {retry_ml:.3f}ml (escalation x{escalation_factor:.1f})")
                            
                            res = _perform_dose({"ml": retry_ml, "reason": f"retry_for_faulty_dose_id_{retry_id}", "nonblocking": True})
                            if res.get("ok"):
                                print(f"[pH Auto] Retry dose executed successfully for id={retry_id}: {retry_ml:.3f}ml")
                                # Mark retry success and schedule stabilization with tighter window for fast re-eval
                                with sqlite3.connect(str(DB_PATH)) as conn2:
                                    now_utc = datetime.now(timezone.utc).isoformat()
                                    conn2.execute("UPDATE ph_dose_log SET result='ok', ts_utc=? WHERE id=?", (now_utc, retry_id))
                                    conn2.commit()
                                threading.Thread(
                                    target=_background_observe_and_update,
                                    args=(retry_id, int(time.time()), retry_observe_s),
                                    daemon=True,
                                ).start()
                            else:
                                print(f"[pH Auto] Retry dose FAILED for id={retry_id}: {res}")
                                with sqlite3.connect(str(DB_PATH)) as conn2:
                                    conn2.execute("UPDATE ph_dose_log SET result='retry_failed' WHERE id=?", (retry_id,))
                                    conn2.commit()
                        except Exception as e:
                            print(f"[pH Auto] Exception during retry: {e}")
                            with sqlite3.connect(str(DB_PATH)) as conn2:
                                conn2.execute("UPDATE ph_dose_log SET result='retry_error' WHERE id=?", (retry_id,))
                                conn2.commit()

                        attempts += 1
                        # Short spacing for this scenario to recheck quickly (override longer polls)
                        time.sleep(retry_spacing_s)

                if attempts:
                    continue
            except Exception as e:
                print(f"[pH Auto] Error checking retries: {e}")
            
            # Only act when below band
            if ph_val < targets["low"]:
                # Guarded holds
                if g.get("estop"):
                    _set_auto_block("estop")
                    if _auto_last_block_count == 3:
                        skip_next_poll = True
                elif g.get("reservoir"):
                    _set_auto_block("reservoir")
                    if _auto_last_block_count == 3:
                        skip_next_poll = True
                elif g.get("safe_off"):
                    _set_auto_block("safe_off")
                    if _auto_last_block_count == 3:
                        skip_next_poll = True
                elif g.get("ec_baseline_low"):
                    _set_auto_block("ec_baseline_low")
                    if _auto_last_block_count == 3:
                        skip_next_poll = True
                elif g.get("ec_settle"):
                    _set_auto_block("ec_settle")
                    if _auto_last_block_count == 3:
                        skip_next_poll = True
                elif g.get("daily_cap"):
                    _set_auto_block("daily_cap")
                    if _auto_last_block_count == 3:
                        skip_next_poll = True
                elif g.get("interval"):
                    _set_auto_block("cooldown")
                else:
                    # Concurrency: skip if dosing lock is held
                    if _dose_lock.locked():
                        _set_auto_block("cooldown")
                    else:
                        # Aim for setpoint (midpoint of band), not the low edge
                        setpoint = (targets["low"] + targets["high"]) / 2.0
                        need_dpH = max(0.0, setpoint - ph_val)
                        # Safe initial micro-dose when learner unknown/default
                        # SAFETY: 0.10ml provides faster response while remaining conservative
                        initial_ml = _settings_get_float("dosing.ph_up_initial_ml", 0.10)
                        _ec_now = _get_latest_ec()[0]
                        est_val = _estimate_ml_per_pH(_ec_now)
                        # SAFETY: If no estimator available, use conservative micro-dose
                        if est_val is None:
                            ml = initial_ml
                        else:
                            # Apply EC compensation if configured (helper defined in _perform_dose scope is not accessible here,
                            # so re-evaluate factor inline with identical logic for minimal coupling)
                            ml_per_pH = est_val
                            try:
                                if _ec_now is not None:
                                    ref = _settings_get_float("dosing.ph_up_ml_per_pH_ref_ec_mscm", 1.0)
                                    slope = _settings_get_float("dosing.ph_up_ml_per_pH_ec_slope", 0.0)
                                    fmin = _settings_get_float("dosing.ph_up_ml_per_pH_ec_min_factor", 0.5)
                                    fmax = _settings_get_float("dosing.ph_up_ml_per_pH_ec_max_factor", 2.0)
                                    factor = 1.0 + slope * (float(_ec_now) - ref)
                                    if fmin > fmax:
                                        fmin, fmax = fmax, fmin
                                    factor = max(fmin, min(fmax, factor))
                                    ml_per_pH = max(0.001, float(ml_per_pH) * factor)
                            except Exception:
                                pass
                            ml_est = safety * need_dpH * ml_per_pH
                            ml = max(step_min, min(step_max, ml_est))
                        _print_auto_decision("dose", ph_val, _get_latest_ec()[0], targets, ml, g)
                        _perform_dose({"ml": ml, "reason": "auto", "nonblocking": True})
                        _auto_last_holding_reason = None
            else:
                # pH above band: clear holding reason
                _auto_last_holding_reason = None
            time.sleep(poll_s)
        except Exception:
            time.sleep(poll_s)


def _auto_enable(enable: bool) -> bool:
    """Start/stop automation thread."""
    global _auto_thread, _auto_stop_evt, _auto_enabled_at
    with _auto_lock:
        if enable:
            if _auto_thread and _auto_thread.is_alive():
                return True
            _auto_stop_evt = threading.Event()
            _auto_thread = threading.Thread(target=_auto_loop, daemon=True)
            _auto_enabled_at = time.time()
            _auto_thread.start()
            return True
        else:
            if _auto_stop_evt:
                _auto_stop_evt.set()
            _auto_thread = None
            _auto_enabled_at = None
            return False


@router.post("/api/ph/auto")
def ph_auto(body: Dict[str, Any] = Body(...)):
    enable = bool(body.get("enable", False))
    # NEW: Persist setting in unified auto-control system
    try:
        from app.auto_control import set_controller_auto_enabled
        set_controller_auto_enabled("ph", enable)
    except Exception:
        pass
    # Apply runtime state (non-blocking)
    try:
        _auto_enable(enable)
    except Exception:
        pass
    return {"ok": True, "enabled": bool(enable)}


def start_ph_auto_if_enabled():
    """Start pH auto loop on app startup if enabled in settings.
    Called from main.py startup event."""
    try:
        from app.auto_control import should_automate
        if should_automate("ph"):
            _auto_enable(True)
            print("[pH Auto] Started automation loop (enabled in settings)")
        else:
            print("[pH Auto] Not starting (disabled in settings)")
    except Exception as e:
        print(f"[pH Auto] Failed to auto-start: {e}")


@router.get("/api/ph/auto/enable")
def ph_auto_enable(on: int = Query(0)):
    """Non-blocking GET toggle for UI fallback when POST hangs.
    Usage: /api/ph/auto/enable?on=1 (enable) or on=0 (disable)."""
    enable = bool(int(on))
    # NEW: Persist setting in unified auto-control system
    try:
        from app.auto_control import set_controller_auto_enabled
        set_controller_auto_enabled("ph", enable)
    except Exception:
        pass
    try:
        _auto_enable(enable)
    except Exception:
        pass
    return {"ok": True, "enabled": enable, "method": "GET"}


@router.post("/api/ph/auto/learn/reset")
def ph_auto_learn_reset():
    """Clear learned estimator by resetting post_ph for all successful doses.
    This forces the estimator to return the default until new valid samples accumulate.
    Safe to call anytime; does not delete dose history.
    Also persists reset timestamp to system_state for service restart resilience.
    """
    try:
        ts_now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(DB_PATH)) as conn:
            # Clear post_ph to invalidate learning samples
            conn.execute("UPDATE ph_dose_log SET post_ph = NULL WHERE result = 'ok'")
            # Create system_state table if not exists (sensor_poller may not have run yet)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
            """)
            # Persist reset timestamp for audit and potential service restart handling
            conn.execute(
                "INSERT OR REPLACE INTO system_state (key, value, updated_at) VALUES (?, ?, ?)",
                ("ph_learner_reset_ts", ts_now, ts_now)
            )
            conn.commit()
        return {"ok": True, "message": "Learned estimator reset", "reset_at": ts_now}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.post("/api/ph/auto/reset_to_safe_defaults")
def ph_auto_reset_to_safe_defaults():
    """Reset ALL pH dosing settings to safe conservative defaults.
    
    This updates the database settings to use:
    - initial_ml: 0.01 (was 0.1 - too aggressive for some systems)
    - min_interval_s: 900 (15 minutes between doses)
    - ml_per_pH_default: 1.0 (conservative starting estimate)
    
    Also clears the learned estimator to force fresh learning.
    
    Call this after the system has been over-dosing to reset to safe values.
    """
    try:
        from app.settings import upsert_settings
        
        # Set safe conservative defaults
        safe_settings = {
            "dosing.ph_up_initial_ml": "0.01",        # Ultra-conservative 0.01ml initial dose
            "dosing.ph_min_interval_s": "900",         # 15 minutes between doses
            "dosing.ph_up_ml_per_pH_default": "1.0",   # 1ml per 1 pH unit (will be learned)
            "dosing.ph_stabilization_window_s": "180", # 3 minutes to stabilize
            "dosing.ph_max_predicted_delta_ph": "0.3", # Max 0.3 pH change per dose
        }
        
        upsert_settings(safe_settings)
        
        # Also clear the learned estimator
        ts_now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("UPDATE ph_dose_log SET post_ph = NULL WHERE result = 'ok'")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute(
                "INSERT OR REPLACE INTO system_state (key, value, updated_at) VALUES (?, ?, ?)",
                ("ph_learner_reset_ts", ts_now, ts_now)
            )
            conn.commit()
        
        return {
            "ok": True, 
            "message": "Reset to safe defaults and cleared learned estimator",
            "settings_applied": safe_settings,
            "reset_at": ts_now
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@router.get("/api/ph/auto/debug")
def ph_auto_debug():
    """Compact introspection endpoint for automation state."""
    # NEW: Use unified auto-control system
    try:
        from app.auto_control import should_automate
        enabled = should_automate("ph")
    except Exception:
        enabled = False
    
    poll_s = _settings_get_int("dosing.poll_interval_s", 30)
    observe_s = _settings_get_int("dosing.observe_s_after_dose", 600)
    
    try:
        learned = _estimate_ml_per_pH(_get_latest_ec()[0])
    except Exception:
        learned = None
    
    return {
        "enabled": enabled,
        "holding_reason": _auto_last_holding_reason,
        "poll_interval_s": poll_s,
        "observe_s": observe_s,
        "learned_ml_per_pH": learned,
        "last_decision": _auto_last_decision or {}
    }


@router.get("/api/ph/export")
def ph_export(hours: int = Query(24)):
    _ensure_tables()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ts_utc, action, volume_ml, duration_ms, pre_ph, post_ph, result, reason FROM ph_dose_log WHERE ts_utc >= ? ORDER BY ts_utc ASC",
            (cutoff.isoformat(),)
        )
        rows = cur.fetchall()
    # CSV
    lines = ["ts_utc,action,volume_ml,duration_ms,pre_ph,post_ph,result,reason"]
    for r in rows:
        line = ",".join([
            str(r[0]), str(r[1]), str(r[2] if r[2] is not None else ""), str(r[3] if r[3] is not None else ""),
            str(r[4] if r[4] is not None else ""), str(r[5] if r[5] is not None else ""), str(r[6]), str(r[7] if r[7] else "")
        ])
        lines.append(line)
    return PlainTextResponse("\n".join(lines), media_type="text/csv")


# --- New telemetry endpoints -------------------------------------------------
@router.get("/api/ph/dose_log")
def ph_dose_log(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    hours: Optional[int] = Query(None),
    grow: Optional[bool] = Query(False),
    limit: int = Query(2000)
):
    """Get dose events. Prefers start/end over hours. If grow=true, computes range from settings."""
    try:
        # Handle grow preset
        if grow:
            grow_date_str = _settings_get("general.grow_start_date", "")
            if grow_date_str:
                try:
                    from app.settings import SA_TZ
                    # pytz timezone needs localize
                    naive_dt = datetime.strptime(grow_date_str, "%Y-%m-%d")
                    local_dt = SA_TZ.localize(naive_dt)
                except Exception:
                    # Fallback to UTC if import fails
                    naive_dt = datetime.strptime(grow_date_str, "%Y-%m-%d")
                    local_dt = naive_dt.replace(tzinfo=timezone.utc)
                start = local_dt.astimezone(timezone.utc).isoformat()
                end = datetime.now(timezone.utc).isoformat()
        
        events = _dose_events_range(start=start, end=end, hours=hours, limit=limit)
        # Align field names with spec
        out = []
        for e in events:
            out.append({
                "ts": e["ts"],
                "seconds": e["seconds"],
                "volume_ml": e["volume_ml"],
                "reason": e.get("detail") or e.get("action") or "manual",
                "ph_before": e["ph_before"],
                "ph_after": e["ph_after"],
                "guard_triggered": e["guard_triggered"],
            })
        return out
    except ValueError as ve:
        return JSONResponse(status_code=422, content={"ok": False, "error": str(ve)})


@router.get("/api/ph/dose_summary")
def ph_dose_summary(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    days: Optional[int] = Query(None),
    grow: Optional[bool] = Query(False)
):
    """Get daily aggregated dose totals. Prefers start/end over days."""
    try:
        # Handle grow preset
        if grow:
            grow_date_str = _settings_get("general.grow_start_date", "")
            if grow_date_str:
                try:
                    from app.settings import SA_TZ
                    naive_dt = datetime.strptime(grow_date_str, "%Y-%m-%d")
                    local_dt = SA_TZ.localize(naive_dt)
                except Exception:
                    naive_dt = datetime.strptime(grow_date_str, "%Y-%m-%d")
                    local_dt = naive_dt.replace(tzinfo=timezone.utc)
                start = local_dt.astimezone(timezone.utc).isoformat()
                end = datetime.now(timezone.utc).isoformat()
        
        rows = _dose_daily_range(start=start, end=end, days=days)
        return rows
    except ValueError as ve:
        return JSONResponse(status_code=422, content={"ok": False, "error": str(ve)})


@router.get("/api/ph/dose_log.csv")
def ph_dose_log_csv(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    hours: Optional[int] = Query(None),
    grow: Optional[bool] = Query(False),
    limit: int = Query(2000)
):
    """CSV export of dose events with range support."""
    try:
        # Handle grow preset
        start_for_filename = start
        end_for_filename = end
        if grow:
            grow_date_str = _settings_get("general.grow_start_date", "")
            if grow_date_str:
                try:
                    from app.settings import SA_TZ
                    naive_dt = datetime.strptime(grow_date_str, "%Y-%m-%d")
                    local_dt = SA_TZ.localize(naive_dt)
                except Exception:
                    naive_dt = datetime.strptime(grow_date_str, "%Y-%m-%d")
                    local_dt = naive_dt.replace(tzinfo=timezone.utc)
                start = local_dt.astimezone(timezone.utc).isoformat()
                end = datetime.now(timezone.utc).isoformat()
                start_for_filename = start
                end_for_filename = end
        
        events = _dose_events_range(start=start, end=end, hours=hours, limit=limit)
        
        # Build filename based on range
        filename = "ph_dose_log"
        if start_for_filename and end_for_filename:
            start_date = datetime.fromisoformat(start_for_filename.replace('Z', '+00:00')).strftime("%Y%m%d")
            end_date = datetime.fromisoformat(end_for_filename.replace('Z', '+00:00')).strftime("%Y%m%d")
            filename = f"ph_dose_log_{start_date}_{end_date}.csv"
        elif hours:
            filename = f"ph_dose_log_{hours}h.csv"
        else:
            filename = "ph_dose_log.csv"
        
        lines = ["ts,seconds,volume_ml,reason,ph_before,ph_after,guard_triggered"]
        for e in events:
            line = ",".join([
                str(e["ts"]), str(e["seconds"]),
                "" if e["volume_ml"] is None else str(e["volume_ml"]),
                str(e.get("detail") or e.get("action") or "manual"),
                "" if e["ph_before"] is None else str(e["ph_before"]),
                "" if e["ph_after"] is None else str(e["ph_after"]),
                "" if not e["guard_triggered"] else str(e["guard_triggered"]) 
            ])
            lines.append(line)
        
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return PlainTextResponse("\n".join(lines), media_type="text/csv", headers=headers)
    except ValueError as ve:
        return PlainTextResponse(f"Error: {ve}", status_code=422)

# --- Module init: auto-start automation if enabled in settings ---
try:
    # NEW: Use unified auto-control system
    from app.auto_control import should_automate
    _enabled = should_automate("ph")
    if _enabled:
        _auto_enable(True)
except Exception:
    # If auto_control is not yet available at import time, ignore
    pass
