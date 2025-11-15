"""Generic controller mode persistence.
Controllers: ph, ec, lights, chiller, circulation.
Modes: auto (normal automation), manual (suppress automation), maintenance (automation suppressed + overrides/diagnostics; semantics controller-specific).
Stored in settings table as controller.<name>.mode.
"""
import sqlite3
import logging
from pathlib import Path
from typing import Dict
import os

logger = logging.getLogger(__name__)
# Allow DB_PATH override for tests
def _get_db_path():
    override = os.environ.get("RDWC_CONTROLLER_MODES_DB")
    if override:
        return Path(override)
    return Path(__file__).parent.parent / "data" / "rdwc.db"
DB_PATH = _get_db_path()
VALID_MODES = {"auto", "manual", "maintenance"}
CONTROLLERS = ["ph", "ec", "lights", "chiller", "circulation"]

INIT_SQL = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

def _ensure():
    db_path = _get_db_path()
    db_path.parent.mkdir(exist_ok=True)
    with sqlite3.connect(str(db_path), timeout=10) as conn:
        conn.execute(INIT_SQL)
        for c in CONTROLLERS:
            conn.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?, ?)", (f"controller.{c}.mode", "auto"))
        conn.commit()


def get_mode(controller: str) -> str:
    _ensure()
    if controller not in CONTROLLERS:
        return "auto"
    db_path = _get_db_path()
    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (f"controller.{controller}.mode",)).fetchone()
            if row and row[0] in VALID_MODES:
                return row[0]
    except Exception as e:
        logger.error(f"get_mode({controller}) failed: {e}")
    return "auto"


def set_mode(controller: str, mode: str) -> bool:
    if controller not in CONTROLLERS or mode not in VALID_MODES:
        return False
    _ensure()
    db_path = _get_db_path()
    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (f"controller.{controller}.mode", mode))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"set_mode({controller},{mode}) failed: {e}")
        return False


def get_all_modes() -> Dict[str, str]:
    _ensure()
    result = {}
    db_path = _get_db_path()
    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            for c in CONTROLLERS:
                row = conn.execute("SELECT value FROM settings WHERE key=?", (f"controller.{c}.mode",)).fetchone()
                result[c] = (row[0] if row and row[0] in VALID_MODES else "auto")
    except Exception as e:
        logger.error(f"get_all_modes failed: {e}")
    return result
