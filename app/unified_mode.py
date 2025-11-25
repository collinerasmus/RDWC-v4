"""
UNIFIED MODE SYSTEM - THE ONLY MODE SYSTEM
Replaces: system_mode.py, controller_modes.py, sensors_mode.py

ONE mode concept for entire system:
- AUTO: Full automation running
- MANUAL: User control, automation paused
- MAINTENANCE: Service mode, automation paused

This module is the ONLY place where mode state is read/written.
All other modules must import from here.
"""
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Optional
import os

logger = logging.getLogger(__name__)

# Database path
def _get_db_path() -> Path:
    override = os.getenv("RDWC_DB") or os.getenv("RDWC_DB_PATH")
    if override:
        return Path(override)
    return Path(__file__).parent.parent / "data" / "rdwc.db"

DB_PATH = _get_db_path()

# Valid modes
MODE_AUTO = "auto"
MODE_MANUAL = "manual"
MODE_MAINTENANCE = "maintenance"
VALID_MODES = {MODE_AUTO, MODE_MANUAL, MODE_MAINTENANCE}

# Legacy constants for backward compatibility
MODE_HOLD = "hold"  # Maps to MANUAL

# Controllers that respect mode
CONTROLLERS = ["ph", "ec", "lights", "chiller", "circulation", "sensors"]

def _ensure_db():
    """Initialize database tables"""
    db_path = _get_db_path()
    db_path.parent.mkdir(exist_ok=True)
    
    with sqlite3.connect(str(db_path), timeout=10) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Set default mode to manual (safety first)
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("system.mode", MODE_MANUAL)
        )
        conn.commit()
        
        # Set default mode to manual (safety first)
        conn.execute("""
            INSERT OR IGNORE INTO settings (key, value) 
            VALUES ('unified_mode', 'manual')
        """)
        
        conn.commit()
        logger.debug("Unified mode database initialized")


def get_mode() -> str:
    """Get current system mode via single pooled connection."""
    _ensure_db()
    try:
        from app.db_pool import get_conn
        conn = get_conn(readonly=True)
        row = conn.execute("SELECT value FROM settings WHERE key='unified_mode'").fetchone()
        if row and row[0] in VALID_MODES:
            return row[0]
        logger.warning("Unified mode not found, defaulting to manual")
        return MODE_MANUAL
    except Exception as e:
        logger.error(f"Failed to get unified mode: {e}")
        return MODE_MANUAL


def set_mode(mode: str) -> bool:
    """Set system mode using pooled connection (atomic)."""
    if mode not in VALID_MODES:
        return False
    _ensure_db()
    try:
        from app.db_pool import get_conn
        conn = get_conn()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('unified_mode', ?)", (mode,))
        conn.commit()
        logger.info(f"✅ Unified mode set to: {mode}")
        return True
    except Exception as e:
        logger.error(f"Failed to set unified mode: {e}")
        return False


def is_auto() -> bool:
    """Quick check if system is in AUTO mode"""
    return get_mode() == MODE_AUTO


def is_manual() -> bool:
    """Quick check if system is in MANUAL mode"""
    return get_mode() == MODE_MANUAL


def is_maintenance() -> bool:
    """Quick check if system is in MAINTENANCE mode"""
    return get_mode() == MODE_MAINTENANCE


def should_automate() -> bool:
    """Returns True if automation should run (only in AUTO mode)"""
    return get_mode() == MODE_AUTO


def get_all_status() -> Dict[str, any]:
    """Get complete mode status for debugging/UI"""
    mode = get_mode()
    return {
        "mode": mode,
        "is_auto": mode == MODE_AUTO,
        "is_manual": mode == MODE_MANUAL,
        "is_maintenance": mode == MODE_MAINTENANCE,
        "should_automate": mode == MODE_AUTO,
        "controllers": {c: mode for c in CONTROLLERS}
    }


# Backward compatibility - map old functions to new unified system
def get_system_mode() -> str:
    """Legacy compatibility"""
    return get_mode()


def set_system_mode(mode: str, propagate_to_controllers: bool = True) -> bool:
    """Legacy compatibility - propagation no longer needed (unified)"""
    return set_mode(mode)


def get_controller_mode(controller: str) -> str:
    """Get mode for a specific controller.
    In unified mode, returns system-wide mode without legacy mapping."""
    return get_mode()  # Returns: "auto", "manual", or "maintenance"


def set_controller_mode(controller: str, mode: str) -> bool:
    """Legacy compatibility - setting any controller sets system mode"""
    # Map legacy "hold" to manual
    if mode == "hold":
        mode = MODE_MANUAL
    return set_mode(mode)


def get_sensor_mode() -> str:
    """Legacy compatibility"""
    return get_mode()


def set_sensor_mode(mode: str) -> bool:
    """Legacy compatibility"""
    return set_mode(mode)


def get_all_modes() -> Dict[str, str]:
    """Legacy compatibility - returns dict of controller names to modes (as "hold" for backward compat)"""
    mode = get_mode()
    # Map to legacy "hold" format that old code expects
    legacy_mode = "hold" if mode in (MODE_MANUAL, MODE_MAINTENANCE) else "auto"
    return {controller: legacy_mode for controller in CONTROLLERS}


def get_overrides() -> Dict[str, str]:
    """Legacy compatibility - sensors module compatibility"""
    return {}  # No per-sensor overrides in unified system


# Legacy relay state persistence functions (moved from system_mode.py)
def save_relay_state(relay: str, state: bool):
    """Save relay state to database for restoration"""
    _ensure_db()
    db_path = _get_db_path()
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relay_state (
                    relay TEXT PRIMARY KEY,
                    last_state INTEGER NOT NULL,
                    last_change_ts INTEGER NOT NULL
                )
            """)
            import time
            conn.execute("""
                INSERT OR REPLACE INTO relay_state (relay, last_state, last_change_ts)
                VALUES (?, ?, ?)
            """, (relay, 1 if state else 0, int(time.time())))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to save relay state: {e}")


def should_auto_restore() -> bool:
    """Check if relays should be auto-restored on boot"""
    return get_mode() == MODE_AUTO


def get_critical_relay_states() -> Dict[str, tuple]:
    """Get last known states of critical relays with timestamps"""
    _ensure_db()
    db_path = _get_db_path()
    states = {}
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relay_state (
                    relay TEXT PRIMARY KEY,
                    last_state INTEGER NOT NULL,
                    last_change_ts INTEGER NOT NULL
                )
            """)
            rows = conn.execute("SELECT relay, last_state, last_change_ts FROM relay_state").fetchall()
            for relay, state, ts in rows:
                states[relay] = (bool(state), ts)
    except Exception as e:
        logger.error(f"Failed to get relay states: {e}")
    return states


def _init_tables():
    """Legacy compatibility - initialize all tables"""
    _ensure_db()
