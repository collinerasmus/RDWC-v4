"""Nutrient Demand Index (NDI) service.

This module aggregates daily nutrient demand from existing EC dosing history,
sensor readings, and the active nutrient schedule. It is monitoring-only; the
resulting index is not used to change EC targets yet.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from datetime import date as date_type
from datetime import datetime, time as time_type, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()
logger = logging.getLogger(__name__)
_BACKFILL_LOCK = threading.Lock()

DB_PATH = Path(os.environ.get("RDWC_DB", str(Path(__file__).resolve().parents[2] / "data" / "rdwc.db")))


def _tzinfo():
    try:
        from app.settings import SA_TZ

        return SA_TZ
    except Exception:
        return timezone.utc


def _local_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(_tzinfo())


def _as_local_date(value: Optional[Any]) -> date_type:
    if value is None:
        return (_local_now() - timedelta(days=1)).date()
    if isinstance(value, date_type) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return (_local_now() - timedelta(days=1)).date()
        dt = datetime.fromisoformat(text.replace("Z", "+00:00")) if "T" in text or ":" in text else datetime.strptime(text, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tzinfo())
    return dt.astimezone(_tzinfo()).date()


def _date_bounds(day: date_type) -> Tuple[int, int, str]:
    start = datetime.combine(day, time_type.min).replace(tzinfo=_tzinfo())
    end = start + timedelta(days=1)
    return int(start.astimezone(timezone.utc).timestamp()), int(end.astimezone(timezone.utc).timestamp()), day.isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nutrient_demand_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE,
                grow_ml REAL DEFAULT 0,
                micro_ml REAL DEFAULT 0,
                bloom_ml REAL DEFAULT 0,
                total_nutrient_ml REAL DEFAULT 0,
                dose_count INTEGER DEFAULT 0,
                avg_ec REAL,
                min_ec REAL,
                max_ec REAL,
                avg_ph REAL,
                min_ph REAL,
                max_ph REAL,
                ec_target REAL,
                ndi REAL,
                ndi_trend TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur = conn.execute("PRAGMA table_info(nutrient_demand_daily)")
        cols = {row[1] for row in cur.fetchall()}
        migrations = {
            "grow_ml": "ALTER TABLE nutrient_demand_daily ADD COLUMN grow_ml REAL DEFAULT 0",
            "micro_ml": "ALTER TABLE nutrient_demand_daily ADD COLUMN micro_ml REAL DEFAULT 0",
            "bloom_ml": "ALTER TABLE nutrient_demand_daily ADD COLUMN bloom_ml REAL DEFAULT 0",
            "total_nutrient_ml": "ALTER TABLE nutrient_demand_daily ADD COLUMN total_nutrient_ml REAL DEFAULT 0",
            "dose_count": "ALTER TABLE nutrient_demand_daily ADD COLUMN dose_count INTEGER DEFAULT 0",
            "avg_ec": "ALTER TABLE nutrient_demand_daily ADD COLUMN avg_ec REAL",
            "min_ec": "ALTER TABLE nutrient_demand_daily ADD COLUMN min_ec REAL",
            "max_ec": "ALTER TABLE nutrient_demand_daily ADD COLUMN max_ec REAL",
            "avg_ph": "ALTER TABLE nutrient_demand_daily ADD COLUMN avg_ph REAL",
            "min_ph": "ALTER TABLE nutrient_demand_daily ADD COLUMN min_ph REAL",
            "max_ph": "ALTER TABLE nutrient_demand_daily ADD COLUMN max_ph REAL",
            "ec_target": "ALTER TABLE nutrient_demand_daily ADD COLUMN ec_target REAL",
            "ndi": "ALTER TABLE nutrient_demand_daily ADD COLUMN ndi REAL",
            "ndi_trend": "ALTER TABLE nutrient_demand_daily ADD COLUMN ndi_trend TEXT",
            "notes": "ALTER TABLE nutrient_demand_daily ADD COLUMN notes TEXT",
            "created_at": "ALTER TABLE nutrient_demand_daily ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "ALTER TABLE nutrient_demand_daily ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
        }
        for column, statement in migrations.items():
            if column not in cols:
                try:
                    conn.execute(statement)
                except Exception:
                    logger.debug("NDI migration skipped for column %s", column, exc_info=True)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_nutrient_demand_daily_date ON nutrient_demand_daily(date)")
        conn.commit()


def _read_settings() -> Dict[str, str]:
    try:
        from app.settings import get_all_settings

        return get_all_settings() or {}
    except Exception:
        return {}


def _grow_start_day() -> Optional[date_type]:
    settings = _read_settings()
    raw = str(settings.get("general.grow_start_date", "") or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except Exception:
        return None


def _grow_history_days(max_days: int = 365, include_today: bool = False) -> Optional[int]:
    start_day = _grow_start_day()
    if not start_day:
        return None
    today = _local_now().date()
    end_day = today if include_today else (today - timedelta(days=1))
    if start_day > end_day:
        return 1
    days = (end_day - start_day).days + 1
    return max(1, min(int(max_days or 365), int(days)))


def _pump_rate_ml_per_sec(pump: str) -> float:
    settings = _read_settings()
    try:
        # Settings key is already in ml/sec; do not convert units here.
        return max(0.0, float(settings.get(f"dosing.{pump}_ml_per_sec", "20") or 20.0))
    except Exception:
        # Conservative fallback mirrors default settings.
        return 20.0


def _dose_event_ml_from_seconds(pump: str, seconds: Any) -> float:
    try:
        return round(float(seconds or 0.0) * _pump_rate_ml_per_sec(pump), 3)
    except Exception:
        return 0.0


def _parse_mix_ratio(mix_ratio: Optional[str]) -> Dict[str, float]:
    text = str(mix_ratio or "").strip()
    if not text:
        return {}
    out: Dict[str, float] = {}
    for key, pattern in (("grow", r"G([\d.]+)"), ("micro", r"M([\d.]+)"), ("bloom", r"B([\d.]+)")):
        match = re.search(pattern, text)
        if match:
            try:
                out[key] = float(match.group(1))
            except Exception:
                pass
    return out


def _maybe_compute_day_totals(day_start: int, day_end: int) -> Tuple[Dict[str, float], int, str]:
    totals = {"grow": 0.0, "micro": 0.0, "bloom": 0.0}
    dose_count = 0
    notes: List[str] = []

    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT pump, seconds
            FROM dose_events
            WHERE pump IN ('grow', 'micro', 'bloom')
              AND blocked_by IS NULL
              AND ts >= ? AND ts < ?
            ORDER BY ts ASC, id ASC
            """,
            (day_start, day_end),
        )
        dose_rows = cur.fetchall()

        if dose_rows:
            dose_count = len(dose_rows)
            for row in dose_rows:
                pump = str(row["pump"] or "").strip().lower()
                if pump not in totals:
                    continue
                totals[pump] += _dose_event_ml_from_seconds(pump, row["seconds"])
            notes.append("dose_events source")
        else:
            try:
                cur.execute(
                    """
                    SELECT volume_ml, mix_ratio, duration_ms, action, reason
                    FROM ec_dose_log
                    WHERE ts_utc >= ? AND ts_utc < ?
                    ORDER BY ts_utc ASC, id ASC
                    """,
                    (
                        datetime.fromtimestamp(day_start, tz=timezone.utc).isoformat(),
                        datetime.fromtimestamp(day_end, tz=timezone.utc).isoformat(),
                    ),
                )
                ec_rows = cur.fetchall()
            except sqlite3.OperationalError:
                ec_rows = []
            if ec_rows:
                dose_count = len(ec_rows)
                for row in ec_rows:
                    mix_ratio = _parse_mix_ratio(row["mix_ratio"])
                    total_ml = float(row["volume_ml"] or 0.0)
                    if mix_ratio:
                        ratio_total = sum(v for v in mix_ratio.values() if v > 0)
                        if ratio_total > 0 and total_ml > 0:
                            for key, amount in mix_ratio.items():
                                if key in totals and amount > 0:
                                    totals[key] += round(total_ml * (amount / ratio_total), 3)
                        else:
                            for key, amount in mix_ratio.items():
                                if key in totals:
                                    totals[key] += round(amount, 3)
                    elif total_ml > 0:
                        action = str(row["action"] or "").lower()
                        if action in totals:
                            totals[action] += total_ml
                notes.append("ec_dose_log source")

    return totals, dose_count, "; ".join(notes)


def _read_reading_stats(day_start: int, day_end: int) -> Dict[str, Optional[float]]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COUNT(*) AS samples,
                AVG(ec_ms_cm) AS avg_ec,
                MIN(ec_ms_cm) AS min_ec,
                MAX(ec_ms_cm) AS max_ec,
                AVG(ph) AS avg_ph,
                MIN(ph) AS min_ph,
                MAX(ph) AS max_ph
            FROM readings
            WHERE ts >= ? AND ts < ?
            """,
            (day_start, day_end),
        )
        row = cur.fetchone() or {}
    return {
        "samples": int(row["samples"] or 0),
        "avg_ec": float(row["avg_ec"]) if row["avg_ec"] is not None else None,
        "min_ec": float(row["min_ec"]) if row["min_ec"] is not None else None,
        "max_ec": float(row["max_ec"]) if row["max_ec"] is not None else None,
        "avg_ph": float(row["avg_ph"]) if row["avg_ph"] is not None else None,
        "min_ph": float(row["min_ph"]) if row["min_ph"] is not None else None,
        "max_ph": float(row["max_ph"]) if row["max_ph"] is not None else None,
    }


def _target_for_day(day: date_type) -> Optional[float]:
    settings = _read_settings()
    try:
        grow_start = str(settings.get("general.grow_start_date", "") or "").strip()
        if grow_start:
            start_day = datetime.strptime(grow_start, "%Y-%m-%d").date()
            elapsed_days = max(0, (day - start_day).days)
            week = min(12, (elapsed_days // 7) + 1)
            with _connect() as conn:
                row = conn.execute("SELECT ec_target FROM nutrient_schedule WHERE week = ? LIMIT 1", (week,)).fetchone()
                if row and row[0] is not None:
                    return float(row[0])
    except Exception:
        logger.debug("NDI schedule lookup failed for %s", day, exc_info=True)

    try:
        value = settings.get("targets.ec_target")
        return float(value) if value not in (None, "") else None
    except Exception:
        return None


def classify_ndi_trend(today_value: Optional[float], previous_value: Optional[float]) -> str:
    if today_value is None:
        return "unknown"
    if previous_value is None:
        return "unknown"
    try:
        today = float(today_value)
        previous = float(previous_value)
    except Exception:
        return "unknown"
    if previous <= 0:
        if today > 0:
            return "rising"
        return "stable"
    delta = (today - previous) / previous
    if delta > 0.10:
        return "rising"
    if delta < -0.10:
        return "falling"
    return "stable"


def _previous_day_total(day: date_type) -> Optional[float]:
    prev_row = _previous_day_row(day)
    if not prev_row:
        return None
    return prev_row.get("total_nutrient_ml")


def _previous_day_row(day: date_type) -> Optional[Dict[str, Any]]:
    prev_day = day - timedelta(days=1)
    return _fetch_day_row(prev_day.isoformat())


def _fetch_day_row(day_str: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM nutrient_demand_daily WHERE date = ? LIMIT 1", (day_str,)).fetchone()
        return dict(row) if row else None


def _existing_day_set(start_day: date_type, end_day: date_type) -> set[str]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT date
            FROM nutrient_demand_daily
            WHERE date >= ? AND date <= ?
            """,
            (start_day.isoformat(), end_day.isoformat()),
        ).fetchall()
    return {str(row[0]) for row in rows if row and row[0] is not None}


def _backfill_history(days: int, include_today: bool = False) -> None:
    """Ensure daily NDI rows exist for the requested rolling window.

    This keeps history usable even before a daily timer is configured and
    guarantees zero-dose days are represented in the table.
    """
    days = max(1, int(days or 1))
    today = _local_now().date()
    end_day = today if include_today else (today - timedelta(days=1))
    start_day = end_day - timedelta(days=days - 1)
    if start_day > end_day:
        return

    with _BACKFILL_LOCK:
        existing = _existing_day_set(start_day, end_day)
        cursor = start_day
        while cursor <= end_day:
            key = cursor.isoformat()
            if key not in existing:
                calculate_daily_ndi(key)
            cursor += timedelta(days=1)


def _upsert_row(row: Dict[str, Any]) -> Dict[str, Any]:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO nutrient_demand_daily (
                date, grow_ml, micro_ml, bloom_ml, total_nutrient_ml, dose_count,
                avg_ec, min_ec, max_ec, avg_ph, min_ph, max_ph, ec_target,
                ndi, ndi_trend, notes, updated_at
            ) VALUES (
                :date, :grow_ml, :micro_ml, :bloom_ml, :total_nutrient_ml, :dose_count,
                :avg_ec, :min_ec, :max_ec, :avg_ph, :min_ph, :max_ph, :ec_target,
                :ndi, :ndi_trend, :notes, CURRENT_TIMESTAMP
            )
            ON CONFLICT(date) DO UPDATE SET
                grow_ml=excluded.grow_ml,
                micro_ml=excluded.micro_ml,
                bloom_ml=excluded.bloom_ml,
                total_nutrient_ml=excluded.total_nutrient_ml,
                dose_count=excluded.dose_count,
                avg_ec=excluded.avg_ec,
                min_ec=excluded.min_ec,
                max_ec=excluded.max_ec,
                avg_ph=excluded.avg_ph,
                min_ph=excluded.min_ph,
                max_ph=excluded.max_ph,
                ec_target=excluded.ec_target,
                ndi=excluded.ndi,
                ndi_trend=excluded.ndi_trend,
                notes=excluded.notes,
                updated_at=CURRENT_TIMESTAMP
            """,
            row,
        )
        conn.commit()
    return row


def calculate_daily_ndi(date: Optional[Any] = None) -> Dict[str, Any]:
    """Create or update a single daily NDI row.

    When date is omitted this summarizes the previous completed local day. The
    result is monitoring-only; adaptive EC control will be added later.
    """
    _ensure_table()
    day = _as_local_date(date)
    day_start, day_end, day_str = _date_bounds(day)
    stats = _read_reading_stats(day_start, day_end)
    totals, dose_count, source_note = _maybe_compute_day_totals(day_start, day_end)
    total_nutrient_ml = round(totals["grow"] + totals["micro"] + totals["bloom"], 3)
    ec_target = _target_for_day(day)
    prev_total = _previous_day_total(day)
    ndi_trend = classify_ndi_trend(total_nutrient_ml, prev_total)

    notes: List[str] = []
    if source_note:
        notes.append(source_note)
    if dose_count == 0:
        notes.append("no nutrient dosing recorded")
    if ec_target is None:
        notes.append("no active schedule target available")
    notes.append("monitoring only; adaptive EC control will be added later")

    row = {
        "date": day_str,
        "grow_ml": round(totals["grow"], 3),
        "micro_ml": round(totals["micro"], 3),
        "bloom_ml": round(totals["bloom"], 3),
        "total_nutrient_ml": total_nutrient_ml,
        "dose_count": int(dose_count),
        "avg_ec": stats["avg_ec"],
        "min_ec": stats["min_ec"],
        "max_ec": stats["max_ec"],
        "avg_ph": stats["avg_ph"],
        "min_ph": stats["min_ph"],
        "max_ph": stats["max_ph"],
        "ec_target": ec_target,
        "ndi": total_nutrient_ml,
        "ndi_trend": ndi_trend,
        "notes": "; ".join(notes),
    }
    _upsert_row(row)
    return row


def get_ndi_history(days: int = 30) -> List[Dict[str, Any]]:
    _ensure_table()
    days = max(1, int(days or 30))
    _backfill_history(days=days, include_today=False)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM nutrient_demand_daily
            ORDER BY date DESC
            LIMIT ?
            """,
            (days,),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def get_latest_ndi() -> Dict[str, Any]:
    _ensure_table()
    # Keep recent history hydrated so trend/yesterday values are meaningful.
    _backfill_history(days=30, include_today=False)
    with _connect() as conn:
        latest = conn.execute("SELECT * FROM nutrient_demand_daily ORDER BY date DESC LIMIT 1").fetchone()
        last_7 = conn.execute(
            "SELECT total_nutrient_ml FROM nutrient_demand_daily ORDER BY date DESC LIMIT 7"
        ).fetchall()

    latest_row = dict(latest) if latest else None
    previous_row = None
    if latest_row and latest_row.get("date"):
        try:
            previous_row = _previous_day_row(datetime.strptime(str(latest_row["date"]), "%Y-%m-%d").date())
        except Exception:
            previous_row = None
    latest_value = float(latest_row["total_nutrient_ml"]) if latest_row and latest_row.get("total_nutrient_ml") is not None else 0.0
    prev_value = float(previous_row["total_nutrient_ml"]) if previous_row and previous_row.get("total_nutrient_ml") is not None else None
    seven_day_values = [float(row[0]) for row in last_7 if row[0] is not None]
    seven_day_avg = round(sum(seven_day_values) / len(seven_day_values), 3) if seven_day_values else 0.0

    if latest_row and latest_row.get("ndi_trend") in (None, ""):
        latest_row["ndi_trend"] = classify_ndi_trend(latest_value, prev_value)

    return {
        "latest": latest_row,
        "previous": previous_row,
        "latest_value": latest_value,
        "previous_value": prev_value,
        "yesterday_ml": prev_value if prev_value is not None else 0.0,
        "seven_day_average_ml": seven_day_avg,
        "trend": latest_row.get("ndi_trend") if latest_row else "unknown",
    }


@router.get("/api/nutrient-demand/history")
def api_ndi_history(days: int = Query(30, ge=1, le=365), scope: str = Query("rolling")):
    try:
        scope_norm = (scope or "rolling").strip().lower()
        effective_days = days
        if scope_norm == "grow":
            effective_days = _grow_history_days(max_days=365, include_today=False) or days
        return {
            "ok": True,
            "scope": scope_norm,
            "days": effective_days,
            "history": get_ndi_history(effective_days),
        }
    except Exception as exc:
        logger.exception("NDI history fetch failed")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@router.get("/api/nutrient-demand/latest")
def api_ndi_latest():
    try:
        return {"ok": True, **get_latest_ndi()}
    except Exception as exc:
        logger.exception("NDI latest fetch failed")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@router.post("/api/nutrient-demand/calculate")
def api_ndi_calculate(date: Optional[str] = Query(None)):
    try:
        row = calculate_daily_ndi(date=date)
        return {"ok": True, "row": row}
    except Exception as exc:
        logger.exception("NDI calculate failed")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@router.post("/api/nutrient-demand/run-daily")
def api_ndi_run_daily(date: Optional[str] = Query(None)):
    """Service-safe hook for cron or a systemd timer."""
    try:
        row = calculate_daily_ndi(date=date)
        return {"ok": True, "row": row}
    except Exception as exc:
        logger.exception("NDI daily run failed")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@router.get("/nutrient-demand")
@router.get("/ec/demand")
def nutrient_demand_page():
    page = Path(__file__).resolve().parents[1] / "static" / "nutrient_demand.html"
    return FileResponse(str(page), media_type="text/html")


def main() -> None:
    """Command-line entry point for cron/systemd usage."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Calculate RDWC daily NDI")
    parser.add_argument("--date", default=None, help="Local date to calculate (YYYY-MM-DD). Defaults to previous day.")
    parser.add_argument("--history", type=int, default=0, help="Print recent NDI history instead of calculating.")
    args = parser.parse_args()

    if args.history:
        print(json.dumps(get_ndi_history(args.history), indent=2, default=str))
        return

    print(json.dumps(calculate_daily_ndi(args.date), indent=2, default=str))


_ensure_table()


if __name__ == "__main__":
    main()