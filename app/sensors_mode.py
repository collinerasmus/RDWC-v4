"""
Sensor Mode & Overrides Management
Modes:
- auto: normal continuous polling
- manual: poller heartbeat only; no new sensor reads
- maintenance: continuous polling but controllers should use override values while UI shows both

Overrides stored as JSON in settings key 'sensor_overrides'. Structure:
{
  "temperature_c": 23.4 | null,
  "ph": 6.50 | null,
  "ec_mscm": 1.45 | null,
  "updated_ts": 1731670000
}

Small, additive helper; mirrors pattern in system_mode.
"""
import sqlite3
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

MODE_AUTO = "auto"
MODE_MANUAL = "manual"
MODE_MAINTENANCE = "maintenance"
VALID_MODES = {MODE_AUTO, MODE_MANUAL, MODE_MAINTENANCE}

SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

def _ensure_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        conn.execute(SETTINGS_TABLE_SQL)
        # Default sensor_mode if absent
        conn.execute("""
            INSERT OR IGNORE INTO settings (key, value) VALUES ('sensor_mode', 'auto')
        """)
        conn.commit()


def get_sensor_mode() -> str:
    _ensure_db()
    try:
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='sensor_mode'").fetchone()
            if row and row[0] in VALID_MODES:
                return row[0]
    except Exception as e:
        logger.error(f"get_sensor_mode failed: {e}")
    return MODE_AUTO


def set_sensor_mode(mode: str) -> bool:
    if mode not in VALID_MODES:
        return False
    _ensure_db()
    try:
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('sensor_mode', ?)", (mode,))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"set_sensor_mode failed: {e}")
        return False


def get_overrides() -> Dict[str, Any]:
    _ensure_db()
    try:
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='sensor_overrides'").fetchone()
            if not row:
                return {"temperature_c": None, "ph": None, "ec_mscm": None, "updated_ts": None}
            data = json.loads(row[0])
            # Normalize keys
            return {
                "temperature_c": data.get("temperature_c"),
                "ph": data.get("ph"),
                "ec_mscm": data.get("ec_mscm"),
                "updated_ts": data.get("updated_ts")
            }
    except Exception as e:
        logger.error(f"get_overrides failed: {e}")
        return {"temperature_c": None, "ph": None, "ec_mscm": None, "updated_ts": None}


def set_overrides(new_values: Dict[str, Any]) -> Dict[str, Any]:
    """Set multiple override values atomically; ignores keys not in allowlist."""
    allow = {"temperature_c", "ph", "ec_mscm"}
    current = get_overrides()
    changed = False
    for k, v in new_values.items():
        if k in allow:
            current[k] = v
            changed = True
    if changed:
        current["updated_ts"] = int(time.time())
        try:
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key,value) VALUES ('sensor_overrides', ?)",
                    (json.dumps(current),)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"set_overrides failed: {e}")
    return current


def clear_override_field(field: str) -> bool:
    allow = {"temperature_c", "ph", "ec_mscm"}
    if field not in allow:
        return False
    cur = get_overrides()
    if cur.get(field) is None:
        return True  # already clear
    cur[field] = None
    cur["updated_ts"] = int(time.time())
    try:
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key,value) VALUES ('sensor_overrides', ?)",
                (json.dumps(cur),)
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"clear_override_field failed: {e}")
        return False


def overrides_effective_age(now_ts: Optional[int] = None) -> Optional[int]:
    o = get_overrides()
    if o.get("updated_ts") is None:
        return None
    if now_ts is None:
        now_ts = int(time.time())
    return now_ts - int(o["updated_ts"]) if o.get("updated_ts") else None


def get_effective_values(live: Dict[str, Any]) -> Dict[str, Any]:
    """Return effective sensor values given live sample and current mode/overrides."""
    mode = get_sensor_mode()
    overrides = get_overrides()
    # Copy live
    effective = {
        "temperature_c": live.get("temperature_c"),
        "ph": live.get("ph"),
        "ec_mscm": live.get("ec_mscm")
    }
    if mode == MODE_MAINTENANCE:
        for k in ["temperature_c", "ph", "ec_mscm"]:
            if overrides.get(k) is not None:
                effective[k] = overrides[k]
    return {
        "mode": mode,
        "overrides": overrides,
        "effective": effective
    }
