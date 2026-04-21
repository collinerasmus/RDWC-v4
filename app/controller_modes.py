"""Compatibility shim for legacy controller_modes imports.

Canonical mode management lives in app.unified_mode.
This module preserves historical import paths used by tests/tools.
"""

from typing import Dict

from app.unified_mode import (
    CONTROLLERS,
    get_mode as _get_global_mode,
    set_mode as _set_global_mode,
    get_all_modes,
    get_controller_mode,
    set_controller_mode,
)


def get_mode() -> str:
    """Legacy API: return global mode."""
    return _get_global_mode()


def set_mode(mode: str) -> bool:
    """Legacy API: set global mode."""
    return _set_global_mode(mode)


def get_modes() -> Dict[str, str]:
    """Legacy helper for all controller modes."""
    return get_all_modes()


def get_controller(controller: str) -> str:
    """Legacy helper for a single controller mode."""
    return get_controller_mode(controller)


def set_controller(controller: str, mode: str) -> bool:
    """Legacy helper for setting a single controller mode."""
    return set_controller_mode(controller, mode)
