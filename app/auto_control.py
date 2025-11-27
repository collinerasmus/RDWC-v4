"""
CLEAN AUTO-ENABLE SYSTEM - Single Source of Truth
Replaces: MODE_AUTO/MANUAL/MAINTENANCE, ph.auto_enabled, hold states

ARCHITECTURE:
- Global master enable: controls.global_auto (true/false)
- Per-controller enable: controls.{controller}_auto (true/false)
- Controller runs ONLY if: global_auto=true AND controller_auto=true

NO MORE:
- MODE_AUTO/MANUAL/MAINTENANCE (confusing, conflicting)
- Hold states (controller.{name}.held)
- Individual ph.auto_enabled, ec.auto_enabled scattered in settings

ONE RULE:
Automation runs = global_auto AND controller_auto
"""
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List
import os

logger = logging.getLogger(__name__)

# Controllers that support automation
CONTROLLERS = ["ph", "ec", "chiller"]

def _get_db_path() -> Path:
    override = os.getenv("RDWC_DB") or os.getenv("RDWC_DB_PATH")
    if override:
        return Path(override)
    return Path(__file__).parent.parent / "data" / "rdwc.db"

def _ensure_db():
    """Initialize controls table"""
    db_path = _get_db_path()
    db_path.parent.mkdir(exist_ok=True)
    
    with sqlite3.connect(str(db_path), timeout=10) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Default: global OFF (safety first), individual controllers OFF
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("controls.global_auto", "false"))
        for ctrl in CONTROLLERS:
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (f"controls.{ctrl}_auto", "false"))
        conn.commit()
        logger.debug("Auto-enable controls initialized")

def _get_setting(key: str, default: str = "false") -> str:
    """Get setting value"""
    _ensure_db()
    try:
        from app.db_pool import get_conn
        conn = get_conn(readonly=True)
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default
    except Exception as e:
        logger.error(f"Failed to get {key}: {e}")
        return default

def _set_setting(key: str, value: str) -> bool:
    """Set setting value"""
    _ensure_db()
    try:
        from app.db_pool import get_conn
        conn = get_conn()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to set {key}: {e}")
        return False

# === GLOBAL AUTO ENABLE ===

def is_global_auto_enabled() -> bool:
    """Check if global automation master switch is enabled"""
    return _get_setting("controls.global_auto", "false").lower() == "true"

def set_global_auto_enabled(enabled: bool) -> bool:
    """Set global automation master switch"""
    value = "true" if enabled else "false"
    ok = _set_setting("controls.global_auto", value)
    if ok:
        logger.info(f"✅ Global auto set to: {enabled}")
    return ok

# === PER-CONTROLLER AUTO ENABLE ===

def is_controller_auto_enabled(controller: str) -> bool:
    """Check if a specific controller's automation is enabled"""
    if controller not in CONTROLLERS:
        logger.warning(f"Unknown controller: {controller}")
        return False
    return _get_setting(f"controls.{controller}_auto", "false").lower() == "true"

def set_controller_auto_enabled(controller: str, enabled: bool) -> bool:
    """Set a specific controller's automation enable state"""
    if controller not in CONTROLLERS:
        logger.warning(f"Unknown controller: {controller}")
        return False
    
    value = "true" if enabled else "false"
    ok = _set_setting(f"controls.{controller}_auto", value)
    if ok:
        logger.info(f"✅ Controller '{controller}' auto set to: {enabled}")
    return ok

# === COMBINED LOGIC ===

def should_automate(controller: str) -> bool:
    """
    Determine if controller automation should run.
    
    Returns True ONLY if:
    - Global auto is enabled AND
    - Controller-specific auto is enabled
    """
    if controller not in CONTROLLERS:
        return False
    
    global_enabled = is_global_auto_enabled()
    controller_enabled = is_controller_auto_enabled(controller)
    
    return global_enabled and controller_enabled

# === STATUS ===

def get_auto_status() -> Dict:
    """Get complete auto-enable status for all controllers"""
    global_auto = is_global_auto_enabled()
    
    return {
        "global_auto": global_auto,
        "controllers": {
            ctrl: {
                "auto_enabled": is_controller_auto_enabled(ctrl),
                "will_automate": should_automate(ctrl)
            }
            for ctrl in CONTROLLERS
        }
    }

# === MIGRATION HELPERS ===

def migrate_from_legacy():
    """
    One-time migration from old systems.
    Call this during app startup to port existing settings.
    """
    _ensure_db()
    
    try:
        from app.db_pool import get_conn
        from app.settings import get_setting_key
        
        conn = get_conn()
        
        # Check if already migrated
        migrated = conn.execute("SELECT value FROM settings WHERE key='controls.migrated'").fetchone()
        if migrated and migrated[0] == "true":
            logger.debug("Auto-enable migration already complete")
            return
        
        # Migrate old unified_mode to global_auto
        old_mode = conn.execute("SELECT value FROM settings WHERE key='unified_mode'").fetchone()
        if old_mode and old_mode[0] == "auto":
            set_global_auto_enabled(True)
            logger.info("Migrated unified_mode=auto → global_auto=true")
        
        # Migrate old per-controller auto_enabled settings
        for ctrl in CONTROLLERS:
            old_key = f"{ctrl}.auto_enabled"
            old_val = get_setting_key(old_key, "false")
            if old_val and old_val.lower() == "true":
                set_controller_auto_enabled(ctrl, True)
                logger.info(f"Migrated {old_key}=true → {ctrl}_auto=true")
        
        # Mark migration complete
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('controls.migrated', 'true')")
        conn.commit()
        
        logger.info("✅ Auto-enable migration complete")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
