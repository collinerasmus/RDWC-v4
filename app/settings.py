"""
RDWC-v4 Settings Management
Handles persistent settings storage in SQLite with validation and caching
"""
import sqlite3
import re
from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import pytz

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

# South African timezone
SA_TZ = pytz.timezone('Africa/Johannesburg')

@dataclass
class Settings:
    """System settings dataclass"""
    system_volume_liters: float
    lights_on_time: str  # "HH:MM" format
    lights_duration_hours: int
    
    def __post_init__(self):
        """Validate settings after initialization"""
        if self.system_volume_liters <= 0:
            raise ValueError("System volume must be greater than 0")
        if not re.match(r'^\d{2}:\d{2}$', self.lights_on_time):
            raise ValueError("Lights on time must be in HH:MM format")
        if not (1 <= self.lights_duration_hours <= 24):
            raise ValueError("Lights duration must be between 1 and 24 hours")


# Cache for settings
_settings_cache: Optional[Settings] = None


def _init_settings_table():
    """Initialize settings table if it doesn't exist"""
    DB_PATH.parent.mkdir(exist_ok=True)
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        
        # Create settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Insert defaults if missing (production defaults)
        defaults = {
            'system_volume_liters': '25.0',
            'lights_on_time': '20:00',
            'lights_duration_hours': '16'
        }
        
        for key, default_value in defaults.items():
            cursor.execute("""
                INSERT OR IGNORE INTO settings (key, value) 
                VALUES (?, ?)
            """, (key, default_value))
        
        conn.commit()

def get_setting_key(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a raw setting value by key (string), or default if missing."""
    _init_settings_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        if row and row[0] is not None:
            return str(row[0])
        return default

def set_setting_key(key: str, value: str) -> None:
    """Set a raw setting value by key (string)."""
    _init_settings_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()


def _load_settings_from_db() -> Settings:
    """Load settings from database"""
    _init_settings_table()
    
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT key, value FROM settings")
        rows = cursor.fetchall()
        
        settings_dict = {key: value for key, value in rows}
        
        return Settings(
            system_volume_liters=float(settings_dict.get('system_volume_liters', '25.0')),
            lights_on_time=settings_dict.get('lights_on_time', '20:00'),
            lights_duration_hours=int(settings_dict.get('lights_duration_hours', '16'))
        )


def get_settings() -> Settings:
    """Get current settings (cached)"""
    global _settings_cache
    
    if _settings_cache is None:
        _settings_cache = _load_settings_from_db()
    
    return _settings_cache


def update_settings(
    system_volume_liters: Optional[float] = None,
    lights_on_time: Optional[str] = None,
    lights_duration_hours: Optional[int] = None
) -> Settings:
    """Update settings in database and refresh cache"""
    global _settings_cache
    
    # Get current settings
    current = get_settings()
    
    # Create new settings with updates
    new_settings = Settings(
        system_volume_liters=system_volume_liters if system_volume_liters is not None else current.system_volume_liters,
        lights_on_time=lights_on_time if lights_on_time is not None else current.lights_on_time,
        lights_duration_hours=lights_duration_hours if lights_duration_hours is not None else current.lights_duration_hours
    )
    
    # Validation happens in __post_init__
    
    # Save to database
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        
        updates = {}
        if system_volume_liters is not None:
            updates['system_volume_liters'] = str(system_volume_liters)
        if lights_on_time is not None:
            updates['lights_on_time'] = lights_on_time
        if lights_duration_hours is not None:
            updates['lights_duration_hours'] = str(lights_duration_hours)
        
        for key, value in updates.items():
            cursor.execute("""
                INSERT OR REPLACE INTO settings (key, value) 
                VALUES (?, ?)
            """, (key, value))
        
        conn.commit()
    
    # Update cache
    _settings_cache = new_settings
    
    return new_settings


def lights_window(today_date: datetime) -> Tuple[datetime, datetime]:
    """
    Calculate lights on/off times for a given date
    Returns (on_datetime, off_datetime) in local timezone (Africa/Johannesburg)
    """
    settings = get_settings()
    
    # Parse time string
    hour, minute = map(int, settings.lights_on_time.split(':'))
    
    # Normalize date to timezone-aware base in SA_TZ
    if today_date.tzinfo is None:
        base = SA_TZ.localize(today_date)
    else:
        base = today_date.astimezone(SA_TZ)

    # Create on time for the given date in SA_TZ
    on_dt = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # Calculate off time
    off_dt = on_dt + timedelta(hours=settings.lights_duration_hours)
    
    return on_dt, off_dt


def get_todays_lights_window() -> Tuple[datetime, datetime]:
    """Get today's lights window in local timezone"""
    now = datetime.now(SA_TZ)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return lights_window(today)