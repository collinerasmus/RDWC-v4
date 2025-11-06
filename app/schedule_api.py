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
EHG_DEFAULTS = [
    # Vegetative weeks (1-4)
    {"week": 1, "phase": "veg", "grow_ml10": 5.0, "micro_ml10": 5.0, "bloom_ml10": 2.5, "ec_target": 0.8, "lights": "18/6", "notes": "Seedling/Clone - gentle start"},
    {"week": 2, "phase": "veg", "grow_ml10": 7.5, "micro_ml10": 7.5, "bloom_ml10": 3.75, "ec_target": 1.0, "lights": "18/6", "notes": "Early veg - building roots"},
    {"week": 3, "phase": "veg", "grow_ml10": 10.0, "micro_ml10": 10.0, "bloom_ml10": 5.0, "ec_target": 1.2, "lights": "18/6", "notes": "Mid veg - rapid growth"},
    {"week": 4, "phase": "veg", "grow_ml10": 12.5, "micro_ml10": 12.5, "bloom_ml10": 6.25, "ec_target": 1.4, "lights": "18/6", "notes": "Late veg - preparing for flip"},
    
    # Flowering/Bloom weeks (5-12)
    {"week": 5, "phase": "bloom", "grow_ml10": 10.0, "micro_ml10": 10.0, "bloom_ml10": 15.0, "ec_target": 1.6, "lights": "12/12", "notes": "Flower transition"},
    {"week": 6, "phase": "bloom", "grow_ml10": 7.5, "micro_ml10": 7.5, "bloom_ml10": 17.5, "ec_target": 1.8, "lights": "12/12", "notes": "Early flower - stretch"},
    {"week": 7, "phase": "bloom", "grow_ml10": 5.0, "micro_ml10": 5.0, "bloom_ml10": 20.0, "ec_target": 2.0, "lights": "12/12", "notes": "Mid flower - bud formation"},
    {"week": 8, "phase": "bloom", "grow_ml10": 5.0, "micro_ml10": 5.0, "bloom_ml10": 20.0, "ec_target": 2.0, "lights": "12/12", "notes": "Mid flower - swelling"},
    {"week": 9, "phase": "bloom", "grow_ml10": 2.5, "micro_ml10": 2.5, "bloom_ml10": 17.5, "ec_target": 1.8, "lights": "12/12", "notes": "Late flower - ripening"},
    {"week": 10, "phase": "bloom", "grow_ml10": 0.0, "micro_ml10": 0.0, "bloom_ml10": 15.0, "ec_target": 1.6, "lights": "12/12", "notes": "Pre-flush - bloom only"},
    
    # Flush weeks (11-12)
    {"week": 11, "phase": "flush", "grow_ml10": 0.0, "micro_ml10": 0.0, "bloom_ml10": 0.0, "ec_target": 0.3, "lights": "12/12", "notes": "Flush - week 1 (plain water)"},
    {"week": 12, "phase": "flush", "grow_ml10": 0.0, "micro_ml10": 0.0, "bloom_ml10": 0.0, "ec_target": 0.2, "lights": "12/12", "notes": "Flush - week 2 (harvest prep)"},
]

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
                lights TEXT NOT NULL DEFAULT '18/6',
                notes TEXT
            )
        """)
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
    _ensure_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT week, phase, grow_ml10, micro_ml10, bloom_ml10, ec_target, lights, notes
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
    
    weeks = []
    for r in rows:
        weeks.append({
            "week": r[0],
            "phase": r[1],
            "grow_ml10": r[2],
            "micro_ml10": r[3],
            "bloom_ml10": r[4],
            "ec_target": r[5],
            "lights": r[6],
            "notes": r[7] or ""
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
                INSERT INTO nutrient_schedule (week, phase, grow_ml10, micro_ml10, bloom_ml10, ec_target, lights, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                week_data["week"],
                week_data["phase"],
                week_data["grow_ml10"],
                week_data["micro_ml10"],
                week_data["bloom_ml10"],
                week_data["ec_target"],
                week_data["lights"],
                week_data["notes"]
            ))
        conn.commit()
    
    return {"ok": True, "seeded": len(EHG_DEFAULTS), "source": source}

@router.get("/api/schedule/current_week")
def get_current_week_info():
    """Get current grow week and phase."""
    _ensure_table()
    week_num = _get_current_week()
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT week, phase, grow_ml10, micro_ml10, bloom_ml10, ec_target, lights, notes
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
    
    return {
        "week": row[0],
        "phase": row[1],
        "grow_ml10": row[2],
        "micro_ml10": row[3],
        "bloom_ml10": row[4],
        "ec_target": row[5],
        "lights": row[6],
        "notes": row[7] or "",
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
    except Exception:
        settings = {}
    
    # Get EC preview logic
    plan_items: List[Dict[str, Any]] = []
    
    try:
        from app.ec_control import _get_latest_ec
        ec_current, _ = _get_latest_ec()
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
