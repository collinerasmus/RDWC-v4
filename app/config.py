import os
from dataclasses import dataclass
from typing import List, Optional

# Relay polarity (most 4/8-ch boards are active-LOW). Override via env if needed.
RELAY_ACTIVE_LOW = os.getenv("RELAY_ACTIVE_LOW", "1") in ("1","true","True","yes")

# Canonical GPIO map from project docs (BCM numbering)
PINMAP = {
    "ph_up":        int(os.getenv("PIN_PH_UP",        "5")),   # phys 29
    "grow_pump":    int(os.getenv("PIN_GROW_PUMP",    "6")),   # phys 31
    "micro_pump":   int(os.getenv("PIN_MICRO_PUMP",   "13")),  # phys 33
    "bloom_pump":   int(os.getenv("PIN_BLOOM_PUMP",   "19")),  # phys 35
    "main_pump":    int(os.getenv("PIN_MAIN_PUMP",    "26")),  # phys 37
    "chiller_pump": int(os.getenv("PIN_CHILLER_PUMP", "16")),  # phys 36
    "water_chiller":int(os.getenv("PIN_WATER_CHILLER","20")),  # phys 38
    "grow_lights":  int(os.getenv("PIN_GROW_LIGHTS",  "21")),  # phys 40
}

# Back-compat for old endpoints that used only "main/chiller":
DEFAULT_MAIN   = PINMAP["main_pump"]
DEFAULT_CHILLER= PINMAP["chiller_pump"]

# Alert and monitoring configuration


@dataclass(frozen=True)
class Config:
    """Frozen configuration dataclass with environment-driven settings"""
    
    # Alert system toggles
    alert_enable_telegram: bool
    alert_enable_email: bool
    
    # Telegram settings
    telegram_bot_token: str
    telegram_chat_id: str
    
    # SMTP settings
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    alert_recipients: List[str]
    
    # Sensor thresholds with hysteresis
    ph_low: float
    ph_high: float
    ph_hyst: float
    
    ec_low: float
    ec_high: float
    ec_hyst: float
    
    temp_low: float
    temp_high: float
    temp_hyst: float
    
    # Alert timing
    alert_debounce_min: int
    alert_recovery_grace_min: int
    
    # System settings
    readiness_require_camera: bool


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    """Parse boolean from environment variable"""
    return value.lower() in ('true', '1', 'yes', 'on') if value else default


def _parse_recipients(value: str) -> List[str]:
    """Parse comma-separated email recipients"""
    if not value:
        return []
    return [email.strip() for email in value.split(',') if email.strip()]


def cfg() -> Config:
    """Get frozen configuration from environment variables"""
    return Config(
        # Alert toggles
        alert_enable_telegram=_parse_bool(os.environ.get("ALERT_ENABLE_TELEGRAM"), False),
        alert_enable_email=_parse_bool(os.environ.get("ALERT_ENABLE_EMAIL"), False),
        
        # Telegram
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        
        # SMTP
        smtp_host=os.environ.get("SMTP_HOST", ""),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_pass=os.environ.get("SMTP_PASS", ""),
        alert_recipients=_parse_recipients(os.environ.get("ALERT_RECIPIENTS", "")),
        
        # pH thresholds
        ph_low=float(os.environ.get("PH_LOW", "5.5")),
        ph_high=float(os.environ.get("PH_HIGH", "6.3")),
        ph_hyst=float(os.environ.get("PH_HYST", "0.05")),
        
        # EC thresholds
        ec_low=float(os.environ.get("EC_LOW", "1.2")),
        ec_high=float(os.environ.get("EC_HIGH", "2.0")),
        ec_hyst=float(os.environ.get("EC_HYST", "0.05")),
        
        # Temperature thresholds
        temp_low=float(os.environ.get("TEMP_LOW", "18.0")),
        temp_high=float(os.environ.get("TEMP_HIGH", "22.0")),
        temp_hyst=float(os.environ.get("TEMP_HYST", "0.3")),
        
        # Timing
        alert_debounce_min=int(os.environ.get("ALERT_DEBOUNCE_MIN", "10")),
        alert_recovery_grace_min=int(os.environ.get("ALERT_RECOVERY_GRACE_MIN", "5")),
        
        # System
        readiness_require_camera=_parse_bool(os.environ.get("READINESS_REQUIRE_CAMERA"), False),
    )