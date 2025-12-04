"""
Centralized settings helper functions.

This module provides reusable helper functions for accessing settings
to avoid code duplication across controllers (pH, EC, dosing, etc.).
"""
from typing import Dict


def get_settings_dict() -> Dict[str, str]:
    """Get all settings as string dict."""
    try:
        from app.settings import get_all_settings
        return get_all_settings()
    except Exception:
        return {}


def get_str(key: str, default: str = "") -> str:
    """Get setting value as string or default."""
    sett = get_settings_dict()
    return sett.get(key, default)


def get_float(key: str, default: float = 0.0) -> float:
    """Get setting value as float or default."""
    try:
        return float(get_str(key, str(default)))
    except Exception:
        return default


def get_int(key: str, default: int = 0) -> int:
    """Get setting value as int or default."""
    try:
        return int(float(get_str(key, str(default))))
    except Exception:
        return default


def get_bool(key: str, default: bool = False) -> bool:
    """Get setting value as bool or default."""
    try:
        val = get_str(key, str(default)).lower()
        return val in ("true", "1", "yes", "on")
    except Exception:
        return default
