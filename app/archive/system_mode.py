"""
System Mode Management - Auto/Manual relay restoration
Handles system_mode persistence and smart relay restoration on boot.
"""
import sqlite3
import time
import logging
from typing import Dict, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

# Critical relays that can be auto-restored (safety-first approach)
CRITICAL_RELAYS = ["main_pump", "chiller_pump", "chiller_power", "lights"]

# System modes
MODE_AUTO = "auto"
MODE_MANUAL = "manual"
MODE_MAINTENANCE = "maintenance"
VALID_MODES = {MODE_AUTO, MODE_MANUAL, MODE_MAINTENANCE}


def _init_tables():
    """Initialize system_mode and relay_state tables if they don't exist"""
    DB_PATH.parent.mkdir(exist_ok=True)
    
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        
        # Settings table (should already exist, but ensure it)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Relay state table for persistence
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relay_state (
                relay TEXT PRIMARY KEY,
                last_state INTEGER NOT NULL,
                last_change_ts INTEGER NOT NULL
            )
        """)
        
        # Set default system mode to manual (safety first)
        cursor.execute("""
            INSERT OR IGNORE INTO settings (key, value) 
            VALUES ('system_mode', 'manual')
        """)
        
        conn.commit()
        logger.info("System mode tables initialized")


def get_system_mode() -> str:
    """Get current system mode (auto or manual)"""
    _init_tables()
    
    try:
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'system_mode'")
            row = cursor.fetchone()
            
            if row:
                mode = row[0]
                logger.debug(f"Retrieved system mode: {mode}")
                return mode
            
            # Default to manual if not set
            logger.warning("System mode not found in database, defaulting to manual")
            return MODE_MANUAL
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve system mode: {e}")
        return MODE_MANUAL


def set_system_mode(mode: str, propagate_to_controllers: bool = True) -> bool:
    """Set system mode (auto, manual, or maintenance) and optionally propagate to all controllers"""
    if mode not in VALID_MODES:
        logger.error(f"Invalid system mode: {mode}")
        return False
    
    _init_tables()
    
    try:
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO settings (key, value) 
                VALUES ('system_mode', ?)
            """, (mode,))
            conn.commit()
            logger.info(f"System mode set to: {mode}")
        
        # Propagate to all controllers if requested
        if propagate_to_controllers:
            try:
                from app.controller_modes import set_mode, CONTROLLERS
                for controller in CONTROLLERS:
                    set_mode(controller, mode)
                logger.info(f"Propagated system mode '{mode}' to all controllers")
            except Exception as e:
                logger.error(f"Failed to propagate system mode to controllers: {e}")
                # Don't fail the whole operation if propagation fails
            
            # Also propagate to sensors (which uses a separate sensor_mode setting)
            try:
                from app.sensors_mode import set_sensor_mode
                set_sensor_mode(mode)
                logger.info(f"Propagated system mode '{mode}' to sensors")
            except Exception as e:
                logger.error(f"Failed to propagate system mode to sensors: {e}")
                # Don't fail the whole operation if propagation fails
        
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to set system mode: {e}")
        return False


def save_relay_state(relay: str, state: bool):
    """Save relay state to database for restoration"""
    _init_tables()
    
    try:
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO relay_state (relay, last_state, last_change_ts)
                VALUES (?, ?, ?)
            """, (relay, 1 if state else 0, int(time.time())))
            conn.commit()
            logger.debug(f"Saved state for {relay}: {state}")
    except sqlite3.Error as e:
        logger.error(f"Failed to save relay state for {relay}: {e}")


def get_relay_states() -> Dict[str, Tuple[bool, int]]:
    """Get all saved relay states. Returns dict of relay -> (state, timestamp)"""
    _init_tables()
    
    try:
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT relay, last_state, last_change_ts FROM relay_state")
            rows = cursor.fetchall()
            
            result = {}
            for relay, state, ts in rows:
                result[relay] = (bool(state), ts)
            
            logger.debug(f"Retrieved {len(result)} relay states from database")
            return result
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve relay states: {e}")
        return {}


def get_critical_relay_states() -> Dict[str, Tuple[bool, int]]:
    """Get saved states for critical relays only"""
    all_states = get_relay_states()
    return {k: v for k, v in all_states.items() if k in CRITICAL_RELAYS}


def should_auto_restore() -> bool:
    """Check if system should auto-restore relay states on boot"""
    mode = get_system_mode()
    result = mode == MODE_AUTO
    logger.info(f"Auto-restore check: mode={mode}, should_restore={result}")
    return result
