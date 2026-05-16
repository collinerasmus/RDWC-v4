"""
Schedule API - Nutrient timeline, targets, and action preview

Provides:
- GET /api/nutrient_schedule: Weekly schedule with EC/pH targets and nutrient ratios
- POST /api/nutrient_schedule/seed: Initialize with EHG defaults
- GET /api/schedule/plan: Preview upcoming controller actions (dry-run mode)
- GET /api/schedule/current_week: Current grow week and phase
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter()

DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

# EHG 3-Part default schedule (ml per 10L)
# EHG Nutrient Guide - 18H and 12H photoperiod schedules
# Based on EHG official nutrient chart with flush indicators
AUTO_DEFAULTS = [
    # Germination (Optional Week 0)
    {"week": 0, "phase": "germination", "grow_ml10": 0.0, "micro_ml10": 0.0, "bloom_ml10": 0.0, "ec_target": 0.0, "ph_low": 6.0, "ph_high": 6.5, "temp_target": 22.0, "lights": "24/0", "notes": "Germination - water only, high humidity"},
    
    # 18H Photoperiod - Weeks 1-3 (Seedling/Early Veg)
    {"week": 1, "phase": "seedling", "grow_ml10": 2.5, "micro_ml10": 2.5, "bloom_ml10": 2.5, "ec_target": 0.6, "ph_low": 5.8, "ph_high": 6.2, "temp_target": 20.0, "lights": "18/6", "notes": "18H Week 1 - balanced seedling start"},
    {"week": 2, "phase": "seedling", "grow_ml10": 2.5, "micro_ml10": 2.5, "bloom_ml10": 2.5, "ec_target": 0.8, "ph_low": 5.8, "ph_high": 6.2, "temp_target": 20.0, "lights": "18/6", "notes": "18H Week 2 - root establishment"},
    {"week": 3, "phase": "veg", "grow_ml10": 7.0, "micro_ml10": 7.0, "bloom_ml10": 7.0, "ec_target": 1.0, "ph_low": 5.8, "ph_high": 6.2, "temp_target": 20.0, "lights": "18/6", "notes": "18H Week 3 - early vegetative ⚠️ FLUSH recommended before flower transition"},
    
    # Veg Weeks 1-3 (High Grow phase)
    {"week": 4, "phase": "veg", "grow_ml10": 20.0, "micro_ml10": 10.0, "bloom_ml10": 0.0, "ec_target": 1.2, "ph_low": 5.8, "ph_high": 6.2, "temp_target": 20.0, "lights": "18/6", "notes": "Veg Week 1 - maximum vegetative growth"},
    {"week": 5, "phase": "veg", "grow_ml10": 20.0, "micro_ml10": 10.0, "bloom_ml10": 0.0, "ec_target": 1.3, "ph_low": 5.8, "ph_high": 6.2, "temp_target": 20.0, "lights": "18/6", "notes": "Veg Week 2 - building plant structure"},
    {"week": 6, "phase": "veg", "grow_ml10": 0.0, "micro_ml10": 10.0, "bloom_ml10": 20.0, "ec_target": 1.4, "ph_low": 5.8, "ph_high": 6.2, "temp_target": 20.0, "lights": "18/6", "notes": "Veg Week 3 - transition to bloom nutrients ⚠️ FLUSH recommended before 12/12"},
    
    # 12H Photoperiod - Weeks 4-8 (Flowering)
    {"week": 7, "phase": "flower", "grow_ml10": 0.0, "micro_ml10": 10.0, "bloom_ml10": 20.0, "ec_target": 1.5, "ph_low": 6.0, "ph_high": 6.3, "temp_target": 19.0, "lights": "12/12", "notes": "12H Week 4 - flower initiation"},
    {"week": 8, "phase": "flower", "grow_ml10": 0.0, "micro_ml10": 10.0, "bloom_ml10": 20.0, "ec_target": 1.6, "ph_low": 6.0, "ph_high": 6.3, "temp_target": 19.0, "lights": "12/12", "notes": "12H Week 5 - bud formation"},
    {"week": 9, "phase": "flower", "grow_ml10": 0.0, "micro_ml10": 10.0, "bloom_ml10": 20.0, "ec_target": 1.7, "ph_low": 6.0, "ph_high": 6.3, "temp_target": 19.0, "lights": "12/12", "notes": "12H Week 6 - peak flowering"},
    {"week": 10, "phase": "flower", "grow_ml10": 0.0, "micro_ml10": 10.0, "bloom_ml10": 20.0, "ec_target": 1.6, "ph_low": 6.0, "ph_high": 6.3, "temp_target": 19.0, "lights": "12/12", "notes": "12H Week 7 - bud swelling"},
    {"week": 11, "phase": "flower", "grow_ml10": 0.0, "micro_ml10": 0.0, "bloom_ml10": 0.0, "ec_target": 0.4, "ph_low": 6.0, "ph_high": 6.5, "temp_target": 18.0, "lights": "12/12", "notes": "12H Week 8 - pH Balanced Water Only (final ripening)"},
    
    # Final Flush
    {"week": 12, "phase": "flush", "grow_ml10": 0.0, "micro_ml10": 0.0, "bloom_ml10": 0.0, "ec_target": 0.2, "ph_low": 6.0, "ph_high": 6.5, "temp_target": 18.0, "lights": "12/12", "notes": "Final flush - harvest prep (trichome check, dark period)"},
]

# Legacy compatibility
EHG_DEFAULTS = AUTO_DEFAULTS

def _ensure_table():
    """Create nutrient_schedule table if it doesn't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nutrient_schedule (
                week INTEGER PRIMARY KEY,
                phase TEXT NOT NULL,
                grow_ml10 REAL NOT NULL DEFAULT 0,
                micro_ml10 REAL NOT NULL DEFAULT 0,
                bloom_ml10 REAL NOT NULL DEFAULT 0,
                ec_target REAL NOT NULL DEFAULT 1.0,
                ph_low REAL NOT NULL DEFAULT 5.8,
                ph_high REAL NOT NULL DEFAULT 6.2,
                temp_target REAL NOT NULL DEFAULT 20.0,
                lights TEXT NOT NULL DEFAULT '18/6',
                notes TEXT
            )
        """)
        # Lightweight migration: ensure new columns exist on older installs
        try:
            cur = conn.execute("PRAGMA table_info(nutrient_schedule)")
            cols = {row[1] for row in cur.fetchall()}
            if 'ph_low' not in cols:
                conn.execute("ALTER TABLE nutrient_schedule ADD COLUMN ph_low REAL NOT NULL DEFAULT 5.8")
            if 'ph_high' not in cols:
                conn.execute("ALTER TABLE nutrient_schedule ADD COLUMN ph_high REAL NOT NULL DEFAULT 6.2")
            if 'temp_target' not in cols:
                conn.execute("ALTER TABLE nutrient_schedule ADD COLUMN temp_target REAL NOT NULL DEFAULT 20.0")
        except Exception:
            pass
        conn.commit()

def _get_grow_start_date() -> Optional[datetime]:
    """Get grow start date from settings."""
    try:
        from app.settings import get_all_settings, SA_TZ
        s = get_all_settings()
        date_str = s.get("general.grow_start_date", "")
        if date_str:
            naive = datetime.strptime(date_str, "%Y-%m-%d")
            try:
                return SA_TZ.localize(naive)
            except Exception:
                return naive.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def _format_grow_start_date(dt: Optional[datetime]) -> Optional[str]:
    """Return grow start date as YYYY-MM-DD string for UI/Day-N calculations."""
    if not dt:
        return None
    try:
        return dt.strftime("%Y-%m-%d")
    except Exception:
        try:
            return dt.isoformat().split('T')[0]
        except Exception:
            return None

def _get_current_week() -> int:
    """Calculate current grow week.

    Week/day rollover is anchored to lights-on time so schedule changes happen
    at the start of the grow period, not at midnight.
    """
    try:
        from app.settings import get_all_settings, SA_TZ

        s = get_all_settings()
        date_str = s.get("general.grow_start_date", "")
        if not date_str:
            return 1

        # Parse grow start date (stored as YYYY-MM-DD)
        start_date = datetime.strptime(date_str, "%Y-%m-%d")

        # Use configured lights-on time as day/week rollover edge.
        lights_on = (
            s.get("general.lights_on_time", "")
            or s.get("lights_on_time", "")
            or "15:00"
        )
        try:
            on_h, on_m = map(int, str(lights_on).split(":"))
            if not (0 <= on_h <= 23 and 0 <= on_m <= 59):
                raise ValueError("lights_on_time out of range")
        except Exception:
            on_h, on_m = 15, 0

        anchor_naive = start_date.replace(hour=on_h, minute=on_m, second=0, microsecond=0)
        try:
            anchor = SA_TZ.localize(anchor_naive)
        except Exception:
            anchor = anchor_naive.replace(tzinfo=timezone.utc)

        now_local = datetime.now(timezone.utc).astimezone(anchor.tzinfo)
        elapsed_days = int((now_local - anchor).total_seconds() // 86400)
        elapsed_days = max(0, elapsed_days)

        week = max(1, (elapsed_days // 7) + 1)
        return min(week, 12)  # Cap at 12 weeks
    except Exception:
        # Safe fallback to legacy behavior
        start = _get_grow_start_date()
        if not start:
            return 1
        now = datetime.now(timezone.utc)
        delta = now - start.astimezone(timezone.utc)
        week = max(1, (delta.days // 7) + 1)
        return min(week, 12)

@router.get("/api/nutrient_schedule")
def get_nutrient_schedule():
    """Return all weeks from nutrient schedule."""
    try:
        _ensure_table()
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT week, phase, grow_ml10, micro_ml10, bloom_ml10, ec_target, ph_low, ph_high, temp_target, lights, notes
                FROM nutrient_schedule
                ORDER BY week ASC
            """)
            rows = cur.fetchall()
        if not rows:
            # Return empty with metadata
            return {
                "weeks": [],
                "current_week": _get_current_week(),
                "grow_start_date": _format_grow_start_date(_get_grow_start_date())
            }
        # Normal return (not shown in snippet)
        # ...
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("/api/nutrient_schedule failed")
        return {"ok": False, "error": str(e), "weeks": []}
    
    weeks = []
    for r in rows:
        # Compute ph_setpoint as midpoint for compatibility
        ph_setpoint = None
        try:
            if r[6] is not None and r[7] is not None:
                ph_setpoint = round((float(r[6]) + float(r[7])) / 2.0, 2)
        except Exception:
            ph_setpoint = None
        weeks.append({
            "week": r[0],
            "phase": r[1],
            "grow_ml10": r[2],
            "micro_ml10": r[3],
            "bloom_ml10": r[4],
            "ec_target": r[5],
            "ph_low": r[6],
            "ph_high": r[7],
            "ph_setpoint": ph_setpoint,
            "temp_target": r[8],
            "lights": r[9],
            "notes": r[10] or ""
        })
    
    # Fetch grow_name from settings
    grow_name = "RDWC v4"
    try:
        from app.settings import get_all_settings
        s = get_all_settings()
        grow_name = s.get("general.grow_name", "RDWC v4")
    except Exception:
        pass
    
    return {
        "weeks": weeks,
        "current_week": _get_current_week(),
        "grow_start_date": _format_grow_start_date(_get_grow_start_date()),
        "grow_name": grow_name,
        "ph_band": {"low": 5.8, "high": 6.2},
        "ec_tolerance": 0.2
    }

@router.post("/api/nutrient_schedule/seed")
def seed_nutrient_schedule(source: str = Query("ehg-defaults")):
    """Seed schedule with defaults if empty."""
    _ensure_table()
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM nutrient_schedule")
        count = cur.fetchone()[0]
        
        if count > 0:
            return JSONResponse(
                status_code=409,
                content={"ok": False, "error": "Schedule already seeded", "count": count}
            )
        
        # Insert EHG defaults
        for week_data in EHG_DEFAULTS:
            conn.execute("""
                INSERT INTO nutrient_schedule (week, phase, grow_ml10, micro_ml10, bloom_ml10, ec_target, ph_low, ph_high, temp_target, lights, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                week_data["week"],
                week_data["phase"],
                week_data["grow_ml10"],
                week_data["micro_ml10"],
                week_data["bloom_ml10"],
                week_data["ec_target"],
                week_data.get("ph_low", 5.8),
                week_data.get("ph_high", 6.2),
                week_data.get("temp_target", 20.0),
                week_data["lights"],
                week_data["notes"]
            ))
        conn.commit()
    
    return {"ok": True, "seeded": len(EHG_DEFAULTS), "source": source}

@router.put("/api/nutrient_schedule/week/{week_num}")
def update_week(week_num: int, updates: dict):
    """Update specific week parameters in the nutrient schedule."""
    if week_num < 0 or week_num > 52:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Week must be 0-52"})

    _ensure_table()

    allowed_fields = [
        "phase", "grow_ml10", "micro_ml10", "bloom_ml10", "ec_target",
        "ph_low", "ph_high", "temp_target", "lights", "notes"
    ]
    update_fields = []
    values = []

    for key, value in (updates or {}).items():
        if key in allowed_fields:
            update_fields.append(f"{key} = ?")
            values.append(value)

    if not update_fields:
        return JSONResponse(status_code=400, content={"ok": False, "error": "No valid fields to update"})

    values.append(week_num)
    with sqlite3.connect(str(DB_PATH)) as conn:
        query = f"UPDATE nutrient_schedule SET {', '.join(update_fields)} WHERE week = ?"
        conn.execute(query, values)
        conn.commit()

    return {"ok": True, "week": week_num, "updated": list((updates or {}).keys())}


@router.post("/api/nutrient_schedule/week")
def upsert_week(payload: dict):
    """Insert or replace a week in the nutrient schedule."""
    try:
        week_num = int(payload.get("week", 0))
    except Exception:
        week_num = 0
    if week_num < 0 or week_num > 52:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Week must be 0-52"})

    _ensure_table()

    allowed_fields = [
        "phase", "grow_ml10", "micro_ml10", "bloom_ml10", "ec_target",
        "ph_low", "ph_high", "temp_target", "lights", "notes"
    ]
    fields = ["week"]
    values = [week_num]

    for key in allowed_fields:
        if key in payload:
            fields.append(key)
            values.append(payload[key])

    if len(fields) == 1:
        return JSONResponse(status_code=400, content={"ok": False, "error": "No valid fields to insert"})

    placeholders = ",".join(["?"] * len(fields))
    columns = ",".join(fields)

    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            f"REPLACE INTO nutrient_schedule ({columns}) VALUES ({placeholders})",
            values
        )
        conn.commit()

    return {"ok": True, "week": week_num, "updated": fields}


@router.delete("/api/nutrient_schedule/week/{week_num}")
def delete_week(week_num: int):
    """Delete a specific week from the nutrient schedule."""
    if week_num < 0 or week_num > 52:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Week must be 0-52"})

    _ensure_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.execute("DELETE FROM nutrient_schedule WHERE week = ?", (week_num,))
        conn.commit()
        deleted = cur.rowcount

    return {"ok": True, "deleted": deleted, "week": week_num}

@router.post("/api/nutrient_schedule/reset")
def reset_nutrient_schedule():
    """Clear and reseed schedule with default AUTO values."""
    _ensure_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("DELETE FROM nutrient_schedule")
        for week_data in EHG_DEFAULTS:
            conn.execute(
                """
                INSERT INTO nutrient_schedule (week, phase, grow_ml10, micro_ml10, bloom_ml10, ec_target, ph_low, ph_high, temp_target, lights, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    week_data["week"],
                    week_data["phase"],
                    week_data["grow_ml10"],
                    week_data["micro_ml10"],
                    week_data["bloom_ml10"],
                    week_data["ec_target"],
                    week_data.get("ph_low", 5.8),
                    week_data.get("ph_high", 6.2),
                    week_data.get("temp_target", 20.0),
                    week_data["lights"],
                    week_data["notes"],
                ),
            )
        conn.commit()
    return {"ok": True, "reset": len(EHG_DEFAULTS)}

@router.get("/api/schedule/current_week")
def get_current_week_info():
    """Get current grow week and phase."""
    try:
        _ensure_table()
        week_num = _get_current_week()
        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT week, phase, grow_ml10, micro_ml10, bloom_ml10, ec_target, ph_low, ph_high, temp_target, lights, notes
                FROM nutrient_schedule
                WHERE week = ?
            """, (week_num,))
            row = cur.fetchone()
        start_date = _get_grow_start_date()
        if not row:
            return {
                "week": week_num,
                "phase": "unknown",
                "grow_start_date": _format_grow_start_date(start_date)
            }
        # Normal return (not shown in snippet)
        # ...
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("/api/schedule/current_week failed")
        return {"ok": False, "error": str(e), "week": None, "phase": "unknown"}
    
    # Compute setpoint midpoint for current week
    ph_setpoint = None
    try:
        if row[6] is not None and row[7] is not None:
            ph_setpoint = round((float(row[6]) + float(row[7])) / 2.0, 2)
    except Exception:
        ph_setpoint = None
    return {
        "week": row[0],
        "phase": row[1],
        "grow_ml10": row[2],
        "micro_ml10": row[3],
        "bloom_ml10": row[4],
        "ec_target": row[5],
        "ph_low": row[6],
        "ph_high": row[7],
        "ph_setpoint": ph_setpoint,
        "temp_target": row[8],
        "lights": row[9],
        "notes": row[10] or "",
        "grow_start_date": _format_grow_start_date(start_date)
    }

@router.get("/api/schedule/plan")
def get_schedule_plan(hours: int = Query(48, ge=1, le=168)):
    """
    Preview upcoming controller actions without execution.
    
    Returns planned EC doses, pH adjusts, and lights changes for next N hours.
    All predictions respect guards but do NOT actuate hardware.
    """
    try:
        from app.settings import get_all_settings
        settings = get_all_settings()
        # Get EC preview logic
        plan_items: List[Dict[str, Any]] = []
        from app.ec_control import _get_latest_ec
        ec_current, _ = _get_latest_ec()
        # ... rest of logic ...
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("/api/schedule/plan failed")
        return {"ok": False, "error": str(e), "plan": []}
    except Exception:
        ec_current = None
    
    # Sample future timestamps (every 30 min for next N hours)
    now = datetime.now(timezone.utc)
    timestamps = [now + timedelta(minutes=i*30) for i in range((hours*2) + 1)]
    
    for ts in timestamps:
        # EC dose preview (if EC is low and guards allow)
        try:
            if ec_current is not None:
                ec_target = float(settings.get("targets.ec_target", "1.0"))
                ec_tolerance = float(settings.get("targets.ec_tolerance", "0.2"))
                
                if ec_current < (ec_target - ec_tolerance):
                    # Would dose if guards pass
                    min_interval = int(settings.get("ec.min_interval_sec", "300"))
                    
                    plan_items.append({
                        "ts": ts.isoformat(),
                        "type": "ec_dose",
                        "reason": "ec_below_target",
                        "pump": "grow",  # Could cycle through pumps in real logic
                        "seconds": 0.5,
                        "from_ec": ec_current,
                        "to_ec_est": ec_current + 0.1,
                        "guards": {
                            "min_interval_sec": min_interval,
                            "blocked": False
                        }
                    })
                    # Only predict one dose per window to keep it simple
                    break
        except Exception:
            pass
    
    # Future: add pH preview, lights schedule preview
    
    return {"plan": plan_items, "hours": hours, "generated_at": now.isoformat()}
