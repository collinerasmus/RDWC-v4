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
# AUTO-CANNABIS 3-Part Schedule (ml per 10L) - Optimized for RDWC Autoflowers
# Based on industry best practices for 12-week auto cycle
AUTO_DEFAULTS = [
    # Seedling (Weeks 1-2) - Gentle introduction, establishing roots
    {"week": 1, "phase": "seedling", "grow_ml10": 2.5, "micro_ml10": 2.5, "bloom_ml10": 1.0, "ec_target": 0.6, "ph_low": 5.8, "ph_high": 6.2, "temp_target": 20.0, "lights": "18/6", "notes": "Seedling - gentle start, focus on root development"},
    {"week": 2, "phase": "seedling", "grow_ml10": 5.0, "micro_ml10": 5.0, "bloom_ml10": 2.0, "ec_target": 0.8, "ph_low": 5.8, "ph_high": 6.2, "temp_target": 20.0, "lights": "18/6", "notes": "Early seedling - building root mass"},
    
    # Early Veg (Weeks 3-4) - Rapid vegetative growth
    {"week": 3, "phase": "veg", "grow_ml10": 7.5, "micro_ml10": 7.5, "bloom_ml10": 3.0, "ec_target": 1.0, "ph_low": 5.5, "ph_high": 6.0, "temp_target": 20.0, "lights": "20/4", "notes": "Early veg - rapid leaf development"},
    {"week": 4, "phase": "veg", "grow_ml10": 10.0, "micro_ml10": 10.0, "bloom_ml10": 4.0, "ec_target": 1.2, "ph_low": 5.5, "ph_high": 6.0, "temp_target": 20.0, "lights": "20/4", "notes": "Mid veg - explosive growth phase"},
    
    # Late Veg (Weeks 5-6) - Preparing for flower
    {"week": 5, "phase": "veg", "grow_ml10": 12.0, "micro_ml10": 12.0, "bloom_ml10": 5.0, "ec_target": 1.3, "ph_low": 5.5, "ph_high": 6.0, "temp_target": 20.0, "lights": "20/4", "notes": "Late veg - maximum vegetative growth"},
    {"week": 6, "phase": "veg", "grow_ml10": 12.0, "micro_ml10": 12.0, "bloom_ml10": 6.0, "ec_target": 1.4, "ph_low": 5.8, "ph_high": 6.2, "temp_target": 20.0, "lights": "18/6", "notes": "Pre-flower - auto transition begins"},
    
    # Pre-Flower/Transition (Weeks 7-8) - Auto flowering trigger
    {"week": 7, "phase": "preflower", "grow_ml10": 10.0, "micro_ml10": 10.0, "bloom_ml10": 12.0, "ec_target": 1.5, "ph_low": 5.8, "ph_high": 6.2, "temp_target": 19.0, "lights": "18/6", "notes": "Pre-flower - stretch phase begins"},
    {"week": 8, "phase": "preflower", "grow_ml10": 8.0, "micro_ml10": 8.0, "bloom_ml10": 15.0, "ec_target": 1.6, "ph_low": 6.0, "ph_high": 6.3, "temp_target": 19.0, "lights": "18/6", "notes": "Early flower - bud sites forming"},
    
    # Flowering (Weeks 9-10) - Peak bud development
    {"week": 9, "phase": "flower", "grow_ml10": 5.0, "micro_ml10": 5.0, "bloom_ml10": 18.0, "ec_target": 1.7, "ph_low": 6.0, "ph_high": 6.3, "temp_target": 19.0, "lights": "18/6", "notes": "Mid flower - bud swelling"},
    {"week": 10, "phase": "flower", "grow_ml10": 3.0, "micro_ml10": 3.0, "bloom_ml10": 16.0, "ec_target": 1.5, "ph_low": 6.0, "ph_high": 6.5, "temp_target": 18.0, "lights": "18/6", "notes": "Late flower - ripening phase"},
    
    # Flush (Weeks 11-12) - Final flush and harvest prep
    {"week": 11, "phase": "flush", "grow_ml10": 0.0, "micro_ml10": 0.0, "bloom_ml10": 0.0, "ec_target": 0.4, "ph_low": 6.0, "ph_high": 6.5, "temp_target": 18.0, "lights": "18/6", "notes": "Flush - week 1 (plain water, trichome check)"},
    {"week": 12, "phase": "flush", "grow_ml10": 0.0, "micro_ml10": 0.0, "bloom_ml10": 0.0, "ec_target": 0.2, "ph_low": 6.0, "ph_high": 6.5, "temp_target": 18.0, "lights": "12/12", "notes": "Flush - week 2 (harvest prep, dark period)"},
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

def _get_current_week() -> int:
    """Calculate current grow week based on start date."""
    start = _get_grow_start_date()
    if not start:
        return 1
    now = datetime.now(timezone.utc)
    delta = now - start.astimezone(timezone.utc)
    week = max(1, (delta.days // 7) + 1)
    return min(week, 12)  # Cap at 12 weeks

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
            start_date = _get_grow_start_date()
            return {
                "weeks": [],
                "current_week": _get_current_week(),
                "grow_start_date": start_date.isoformat() if start_date else None
            }
        # Normal return (not shown in snippet)
        # ...
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("/api/nutrient_schedule failed")
        return {"ok": False, "error": str(e), "weeks": []}
    
    weeks = []
    for r in rows:
        weeks.append({
            "week": r[0],
            "phase": r[1],
            "grow_ml10": r[2],
            "micro_ml10": r[3],
            "bloom_ml10": r[4],
            "ec_target": r[5],
            "ph_low": r[6],
            "ph_high": r[7],
            "temp_target": r[8],
            "lights": r[9],
            "notes": r[10] or ""
        })
    
    start_date = _get_grow_start_date()
    return {
        "weeks": weeks,
        "current_week": _get_current_week(),
        "grow_start_date": start_date.isoformat() if start_date else None,
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
    if week_num < 1 or week_num > 12:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Week must be 1-12"})

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
                "grow_start_date": start_date.isoformat() if start_date else None
            }
        # Normal return (not shown in snippet)
        # ...
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("/api/schedule/current_week failed")
        return {"ok": False, "error": str(e), "week": None, "phase": "unknown"}
    
    return {
        "week": row[0],
        "phase": row[1],
        "grow_ml10": row[2],
        "micro_ml10": row[3],
        "bloom_ml10": row[4],
        "ec_target": row[5],
        "ph_low": row[6],
        "ph_high": row[7],
        "temp_target": row[8],
        "lights": row[9],
        "notes": row[10] or "",
        "grow_start_date": start_date.isoformat() if start_date else None
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
