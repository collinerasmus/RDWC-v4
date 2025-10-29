"""
Manual Override System for RDWC-v4
Provides manual control for critical components like chiller pump
"""

import sqlite3
from dataclasses import dataclass
from typing import Optional, Literal
from datetime import datetime, timedelta
from pathlib import Path
import pytz

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

# South African timezone
SA_TZ = pytz.timezone('Africa/Johannesburg')

ChillerMode = Literal["auto", "force_on", "force_off"]

@dataclass
class Overrides:
    """System overrides configuration"""
    chiller_mode: ChillerMode = "auto"
    hold_until: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate overrides after initialization"""
        if self.chiller_mode not in ("auto", "force_on", "force_off"):
            raise ValueError(f"Invalid chiller_mode: {self.chiller_mode}")
        
        # Ensure timezone-aware datetime
        if self.hold_until and self.hold_until.tzinfo is None:
            self.hold_until = SA_TZ.localize(self.hold_until)


# Cache for overrides
_overrides_cache: Optional[Overrides] = None


def _init_overrides_table():
    """Initialize overrides table if it doesn't exist"""
    DB_PATH.parent.mkdir(exist_ok=True)
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        
        # Create overrides table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS overrides (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Insert defaults if missing
        defaults = {
            'chiller_mode': 'auto',
            'hold_until': None
        }
        
        for key, default_value in defaults.items():
            if default_value is not None:
                cursor.execute("""
                    INSERT OR IGNORE INTO overrides (key, value) 
                    VALUES (?, ?)
                """, (key, str(default_value)))
            else:
                cursor.execute("""
                    INSERT OR IGNORE INTO overrides (key, value) 
                    VALUES (?, ?)
                """, (key, ""))
        
        conn.commit()


def _load_overrides_from_db() -> Overrides:
    """Load overrides from database"""
    _init_overrides_table()
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT key, value FROM overrides")
        rows = cursor.fetchall()
        
        overrides_dict = {key: value for key, value in rows}
        
        # Parse hold_until
        hold_until = None
        hold_until_str = overrides_dict.get('hold_until', '')
        if hold_until_str:
            try:
                hold_until = datetime.fromisoformat(hold_until_str)
                if hold_until.tzinfo is None:
                    hold_until = SA_TZ.localize(hold_until)
            except (ValueError, TypeError):
                pass  # Invalid datetime, use None
        
        return Overrides(
            chiller_mode=overrides_dict.get('chiller_mode', 'auto'),
            hold_until=hold_until
        )


def get_overrides() -> Overrides:
    """Get current overrides (cached)"""
    global _overrides_cache
    
    if _overrides_cache is None:
        _overrides_cache = _load_overrides_from_db()
    
    return _overrides_cache


def set_overrides(
    chiller_mode: Optional[ChillerMode] = None,
    hold_until: Optional[datetime] = None,
    hold_minutes: Optional[int] = None
) -> Overrides:
    """Update overrides in database and refresh cache"""
    global _overrides_cache
    
    # Get current overrides
    current = get_overrides()
    
    # Calculate hold_until from hold_minutes if provided
    if hold_minutes is not None:
        now = datetime.now(SA_TZ)
        hold_until = now + timedelta(minutes=hold_minutes)
    
    # Normalize hold_until if in the past
    if hold_until and hold_until < datetime.now(SA_TZ):
        hold_until = None
    
    # Create new overrides with updates
    new_overrides = Overrides(
        chiller_mode=chiller_mode if chiller_mode is not None else current.chiller_mode,
        hold_until=hold_until if hold_until is not None else current.hold_until
    )
    
    # Validation happens in __post_init__
    
    # Save to database
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        
        if chiller_mode is not None:
            cursor.execute("""
                INSERT OR REPLACE INTO overrides (key, value) 
                VALUES (?, ?)
            """, ('chiller_mode', chiller_mode))
        
        if hold_until is not None or hold_minutes is not None:
            hold_str = hold_until.isoformat() if hold_until else ""
            cursor.execute("""
                INSERT OR REPLACE INTO overrides (key, value) 
                VALUES (?, ?)
            """, ('hold_until', hold_str))
        
        conn.commit()
    
    # Update cache
    _overrides_cache = new_overrides
    
    return new_overrides


def is_active(now: Optional[datetime] = None) -> ChillerMode:
    """
    Get effective chiller mode, treating expired hold_until as auto
    
    Args:
        now: Current time (defaults to datetime.now(SA_TZ))
        
    Returns:
        Effective chiller mode: "auto", "force_on", or "force_off"
    """
    if now is None:
        now = datetime.now(SA_TZ)
    elif now.tzinfo is None:
        now = SA_TZ.localize(now)
    
    overrides = get_overrides()
    
    # Check if hold period has expired
    if overrides.hold_until and now >= overrides.hold_until:
        # Hold period expired, return to auto and clear hold_until
        set_overrides(chiller_mode="auto", hold_until=None)
        return "auto"
    
    return overrides.chiller_mode


def get_override_status(now: Optional[datetime] = None) -> dict:
    """
    Get human-readable override status
    
    Returns:
        Dict with mode, active status, and time remaining
    """
    if now is None:
        now = datetime.now(SA_TZ)
    elif now.tzinfo is None:
        now = SA_TZ.localize(now)
    
    overrides = get_overrides()
    effective_mode = is_active(now)
    
    status = {
        "chiller_mode": overrides.chiller_mode,
        "effective_mode": effective_mode,
        "hold_until": overrides.hold_until.isoformat() if overrides.hold_until else None,
        "is_override_active": effective_mode != "auto",
        "time_remaining": None
    }
    
    # Calculate time remaining
    if overrides.hold_until and effective_mode != "auto":
        remaining = overrides.hold_until - now
        if remaining.total_seconds() > 0:
            remaining_minutes = int(remaining.total_seconds() / 60)
            hours, minutes = divmod(remaining_minutes, 60)
            if hours > 0:
                status["time_remaining"] = f"{hours}h {minutes}m"
            else:
                status["time_remaining"] = f"{minutes}m"
    
    return status


def clear_expired_holds():
    """Clear any expired hold periods (call periodically)"""
    now = datetime.now(SA_TZ)
    overrides = get_overrides()
    
    if overrides.hold_until and now >= overrides.hold_until:
        set_overrides(chiller_mode="auto", hold_until=None)


def control_chiller(reason: str):
    """
    Central chiller control function - enforces override precedence.
    Modes: auto | force_on | force_off
    
    Args:
        reason: Human-readable reason for this control check
    """
    from app.relays_core import set_chiller_power, set_chiller_pump, REASON_OVERRIDE
    
    # Clear any expired holds first
    clear_expired_holds()
    
    mode = is_active()
    
    if mode == 'force_on':
        set_chiller_power(True, REASON_OVERRIDE)
        set_chiller_pump(True, REASON_OVERRIDE)
        return
    
    if mode == 'force_off':
        set_chiller_pump(False, REASON_OVERRIDE)
        set_chiller_power(False, REASON_OVERRIDE)
        return
    
    # AUTO mode:
    # Do NOT toggle based on temperature. Do nothing here.
    # Only emergency logic (if explicitly enabled) may override with force=True.
    # The external chiller thermostat handles temperature control in AUTO mode.