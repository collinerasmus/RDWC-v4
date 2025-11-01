"""
pH Control API

Endpoints:
- GET /api/ph/status
- POST /api/ph/dose
- POST /api/ph/auto
- GET /api/ph/export

Implements manual dosing with guards and a simple log table.
Automation is a placeholder that currently refuses enabling.
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

def _recent_doses(limit: int = 5) -> List[Dict[str, Any]]:
    _ensure_tables()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, ts_utc, action, volume_ml, duration_ms, pre_ph, post_ph, result, reason FROM ph_dose_log ORDER BY id DESC LIMIT ?",
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
        cur.execute(
            "SELECT COALESCE(SUM(volume_ml),0) FROM ph_dose_log WHERE result='ok' AND ts_utc >= ?",
            (start_utc.isoformat(),)
        )
        val = cur.fetchone()[0]
        return float(val or 0.0)

def _last_ok_ts() -> Optional[datetime]:
    _ensure_tables()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT ts_utc FROM ph_dose_log WHERE result='ok' ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return None
        try:
            return datetime.fromisoformat(row[0]).astimezone(timezone.utc)
        except Exception:
            return None

# --- Sensors/Settings helpers ------------------------------------------------
def _get_latest_ph() -> Tuple[Optional[float], Optional[int]]:
    """Return latest pH and its unix ts from readings table."""
    from app.logger import DB_PATH as READ_DB
    try:
        with sqlite3.connect(READ_DB) as conn:
            cur = conn.cursor()
            cur.execute("SELECT ts, ph FROM readings WHERE ph IS NOT NULL ORDER BY ts DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                return (float(row[1]) if row[1] is not None else None, int(row[0]))
    except Exception:
        pass
    return (None, None)

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
    sensor_stale = True
    if ts:
        sensor_stale = (now - ts) > 90

    # Min interval guard
    last_ok = _last_ok_ts()
    min_interval = _settings_get_int("dosing.ph_min_interval_s", 300)
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
        "since_last_ok_s": since_last_ok,
        "today_total_ml": today_ml,
        "min_interval_s": min_interval,
        "daily_cap_ml": daily_cap,
    }

# --- API ---------------------------------------------------------------------
@router.get("/api/ph/status")
def ph_status():
    now = time.time()
    ph_val, ts = _get_latest_ph()
    targets = {
        "low": _settings_get_float("targets.ph_low", 5.8),
        "high": _settings_get_float("targets.ph_high", 6.2),
    }
    guards = _compute_guards(now)
    recent = _recent_doses(5)
    return {
        "ph": ph_val,
        "ts": ts,
        "targets": targets,
        "auto": {"enabled": False, "guard": "automation unsupported: only pH Up available"},
        "guards": guards,
        "recent": recent
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
    on = set_dosing_ph_up(True, reason="ph_dose", force=True)
    if not on.get("changed") and not on.get("state"):
        # Could be blocked by estop or cooldown
        return {"ok": False, "reason": on.get("reason", "blocked")}
    time.sleep(max(0, duration_ms) / 1000.0)
    set_dosing_ph_up(False, reason="ph_dose", force=True)
    return {"ok": True}


def _background_observe_and_update(rowid: int, baseline_ts_unix: Optional[int], max_wait_s: int):
    """Poll for the next pH sample after dosing completes, up to max_wait_s seconds.
    Updates post_ph when a newer sample than baseline appears; otherwise leaves as-is.
    """
    try:
        deadline = time.time() + max(0, max_wait_s)
        last_seen_ts = baseline_ts_unix or 0
        while time.time() < deadline:
            ph_after, ts = _get_latest_ph()
            if ts and ts > last_seen_ts:
                _update_post_ph(rowid, ph_after)
                return
            time.sleep(1.0)
        # Fallback single read at end (may still be same sample)
        ph_after, ts = _get_latest_ph()
        if ts and (baseline_ts_unix is None or ts >= baseline_ts_unix):
            _update_post_ph(rowid, ph_after)
    except Exception:
        pass


@router.post("/api/ph/dose")
def ph_dose(body: Dict[str, Any] = Body(...)):
    """Manual dose endpoint.
    Accepts { ml?: number, ms?: number, reason?: string }
    """
    ml = body.get("ml")
    ms = body.get("ms")
    reason = str(body.get("reason", "manual"))[:200]

    # Prefer ml if provided (convert to ms using calibration), but log-time ml always derived from ms
    if ml is not None:
        try:
            ml = float(ml)
        except Exception:
            return JSONResponse(status_code=422, content={"ok": False, "error": "invalid_ml"})
        ms_calc, err = _dose_ms_from_ml(ml)
        if err:
            return JSONResponse(status_code=422, content={"ok": False, "error": err})
        duration_ms = ms_calc
    else:
        try:
            duration_ms = int(float(ms or 0))
        except Exception:
            return JSONResponse(status_code=422, content={"ok": False, "error": "invalid_ms"})
    # Compute volume at log-time using calibration (nullable if no calibration)
    volume_ml = _volume_ml_from_ms(duration_ms)

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
    blocked_reasons = [k for k,v in guard_map.items() if v]
    ts_iso = datetime.now(timezone.utc).isoformat()

    pre_ph, pre_ts = _get_latest_ph()

    if blocked_reasons:
        rowid = _log_row({
            "ts_utc": ts_iso, "action": "dose", "volume_ml": None if volume_ml is None else float(volume_ml),
            "duration_ms": int(duration_ms), "pre_ph": pre_ph, "post_ph": None,
            "result": "blocked", "reason": ",".join(blocked_reasons)
        })
        return JSONResponse(status_code=409, content={"ok": False, "blocked": True, "reasons": blocked_reasons, "rowid": rowid})

    # Actuate pump
    act = _actuate_ph_up(int(duration_ms))
    if not act.get("ok"):
        rowid = _log_row({
            "ts_utc": ts_iso, "action": "dose", "volume_ml": None if volume_ml is None else float(volume_ml),
            "duration_ms": int(duration_ms), "pre_ph": pre_ph, "post_ph": None,
            "result": "error", "reason": act.get("reason","error")
        })
        return JSONResponse(status_code=500, content={"ok": False, "error": act.get("reason","error"), "rowid": rowid})

    rowid = _log_row({
        "ts_utc": ts_iso, "action": "dose", "volume_ml": None if volume_ml is None else float(volume_ml),
        "duration_ms": int(duration_ms), "pre_ph": pre_ph, "post_ph": None,
        "result": "ok", "reason": reason
    })

    # Schedule background observe to update post_ph with next sample (avoid request blocking)
    # Hard-limit to 10s to capture next sample quickly
    observe_s = min(10, _settings_get_int("dosing.observe_s_after_dose", 60))
    threading.Thread(target=_background_observe_and_update, args=(rowid, pre_ts, observe_s), daemon=True).start()

    return {"ok": True, "rowid": rowid, "pre_ph": pre_ph, "volume_ml": None if volume_ml is None else float(volume_ml), "duration_ms": int(duration_ms)}


@router.post("/api/ph/auto")
def ph_auto(body: Dict[str, Any] = Body(...)):
    enable = bool(body.get("enable", False))
    if enable:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "enabled": False,
            "guard": "automation unsupported: only pH Up available"
        })
    return {"ok": True, "enabled": False}


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
        print(f"[DEBUG] dose_log called: start={start}, end={end}, hours={hours}, grow={grow}")
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
        print(f"[DEBUG] _dose_events_range returned {len(events)} events")
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
