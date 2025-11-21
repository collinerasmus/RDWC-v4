"""Generic controller mode persistence - Simplified Hold System.
Controllers: ph, ec, lights, chiller, circulation.
Modes: 
  - auto (default): automation runs normally
  - hold: automation paused (user intervention mode)
Legacy modes (manual, maintenance) are mapped to "hold" for backward compatibility.
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
# Valid modes: auto (running) and hold (paused)
VALID_MODES = {"auto", "hold"}
# Legacy modes map to hold for backward compatibility
LEGACY_MODE_MAP = {"manual": "hold", "maintenance": "hold"}
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
    """Get controller mode (auto or hold). Defaults to auto.
    Legacy modes (manual, maintenance) are automatically converted to hold.
    """
    _ensure()
    if controller not in CONTROLLERS:
        return "auto"
    db_path = _get_db_path()
    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (f"controller.{controller}.mode",)).fetchone()
            if row:
                mode = row[0]
                # Map legacy modes to hold
                if mode in LEGACY_MODE_MAP:
                    return LEGACY_MODE_MAP[mode]
                if mode in VALID_MODES:
                    return mode
    except Exception as e:
        logger.error(f"get_mode({controller}) failed: {e}")
    return "auto"


def set_mode(controller: str, mode: str) -> bool:
    """Set controller mode (auto or hold).
    Legacy modes (manual, maintenance) are accepted and converted to hold.
    """
    if controller not in CONTROLLERS:
        return False
    # Map legacy modes to hold for backward compatibility
    if mode in LEGACY_MODE_MAP:
        mode = LEGACY_MODE_MAP[mode]
    if mode not in VALID_MODES:
        return False
    _ensure()
    db_path = _get_db_path()
    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (f"controller.{controller}.mode", mode))
            conn.commit()
        logger.info(f"Controller {controller} mode set to {mode}")
        return True
    except Exception as e:
        logger.error(f"set_mode({controller},{mode}) failed: {e}")
        return False


def get_all_modes() -> Dict[str, str]:
    """Get modes for all controllers. Legacy modes are converted to hold."""
    _ensure()
    result = {}
    db_path = _get_db_path()
    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            for c in CONTROLLERS:
                row = conn.execute("SELECT value FROM settings WHERE key=?", (f"controller.{c}.mode",)).fetchone()
                if row:
                    mode = row[0]
                    # Map legacy modes
                    if mode in LEGACY_MODE_MAP:
                        mode = LEGACY_MODE_MAP[mode]
                    result[c] = mode if mode in VALID_MODES else "auto"
                else:
                    result[c] = "auto"
    except Exception as e:
        logger.error(f"get_all_modes failed: {e}")
        # Return all auto on error
        for c in CONTROLLERS:
            result[c] = "auto"
    return result


def is_held(controller: str) -> bool:
    """Check if a controller is in hold mode (automation paused)."""
    return get_mode(controller) == "hold"


def set_hold(controller: str, hold: bool) -> bool:
    """Set or release hold for a controller.
    
    Args:
        controller: Controller name
        hold: True to pause automation, False to resume
    
    Returns:
        True if successful
    """
    mode = "hold" if hold else "auto"
    return set_mode(controller, mode)


def set_all_hold(hold: bool) -> bool:
    """Set or release hold for all controllers.
    
    Args:
        hold: True to pause all automation, False to resume all
    
    Returns:
        True if all successful
    """
    success = True
    for controller in CONTROLLERS:
        if not set_hold(controller, hold):
            success = False
    return success
