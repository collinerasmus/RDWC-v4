"""
Centralized relay control - THE ONLY place that touches GPIO.
Provides idempotent, rate-limited relay control with anti-flap protection.
"""
import time
import inspect
from collections import deque, defaultdict
from typing import Dict, Any, List
from datetime import datetime
import logging

try:
    from gpiozero import OutputDevice
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    # Mock for development
    class OutputDevice:
        def __init__(self, pin, active_high=True):
            self.pin = pin
            self.active_high = active_high
            self._value = False
        
        @property
        def value(self):
            return self._value
        
        @value.setter
        def value(self, val):
            self._value = val

logger = logging.getLogger(__name__)

# Relay registry: name -> BCM pin
RELAY_PINS = {
    "lights": 21,
    "chiller_pump": 16,
    "chiller_power": 20,
    "main_pump": 26,
    "dosing_grow": 6,
    "dosing_micro": 13,
    "dosing_bloom": 19,
    "dosing_ph_up": 5,
}

# Minimum ON/OFF times to prevent short-cycling (seconds)
# Reduced for better manual control responsiveness while still protecting hardware
MIN_ON = {
    "chiller_power": 60,   # 1 minute (reduced from 5 for better responsiveness)
    "chiller_pump": 30,    # 30 seconds (reduced from 2 min)
    "main_pump": 15,       # 15 seconds (reduced from 1 min)
    "lights": 10,          # 10 seconds (reduced from 30)
    "dosing_*": 0,         # No restriction
    "ph_*": 0,             # No restriction
}

MIN_OFF = {
    "chiller_power": 60,   # 1 minute (reduced from 5 for better responsiveness)
    "chiller_pump": 30,    # 30 seconds (reduced from 2 min)
    "main_pump": 10,       # 10 seconds (reduced from 30)
    "lights": 5,           # 5 seconds (reduced from 10)
    "dosing_*": 0,         # No restriction
    "ph_*": 0,             # No restriction
}

# Reason constants
REASON_APPLY_SETTINGS = "apply_settings"
REASON_SCHEDULE_ON = "schedule_on"
REASON_SCHEDULE_OFF = "schedule_off"
# REASON_CATCHUP removed - no longer supported (periodic enforcement disabled)
REASON_OVERRIDE = "override"
REASON_EMERGENCY = "emergency"
REASON_HEALTH_GUARD = "health_guard"

# Lights control whitelist - ONLY these reasons are allowed
WHITELIST_LIGHTS = {
    "schedule_on",           # REASON_SCHEDULE_ON - scheduler turns lights on
    "schedule_off",          # REASON_SCHEDULE_OFF - scheduler turns lights off  
    # "catchup" REMOVED - periodic enforcement disabled for pure edge-only control
    "schedule_guard_on",     # scheduler guard ensures lights stay on
    "schedule_guard_off",    # scheduler guard ensures lights stay off
    "apply_settings",        # REASON_APPLY_SETTINGS - settings application
    "override",              # REASON_OVERRIDE - manual override
    "emergency"              # REASON_EMERGENCY - emergency shutdown
}

# Global state
_devices: Dict[str, OutputDevice] = {}
_last_state: Dict[str, bool] = {}
_last_change_ts: Dict[str, float] = {}
_last_reason: Dict[str, str] = {}
_change_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
_antiflap_until: Dict[str, float] = {}

# Event logging for debugging
_relay_event_logs: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
_hold_until: Dict[str, float] = {}  # Temporary holds for debugging

def _get_min_time(relay_name: str, times_dict: Dict[str, int]) -> int:
    """Get minimum time for relay, supporting wildcard matching."""
    # Exact match first
    if relay_name in times_dict:
        return times_dict[relay_name]
    
    # Wildcard matching
    for pattern, time_val in times_dict.items():
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            if relay_name.startswith(prefix):
                return time_val
    
    return 0  # Default

def _elapsed(relay_name: str) -> float:
    """Get elapsed time since last change for relay."""
    if relay_name not in _last_change_ts:
        return 0
    return time.monotonic() - _last_change_ts[relay_name]

def _initialize_device(relay_name: str) -> OutputDevice:
    """Initialize GPIO device for relay."""
    if relay_name not in RELAY_PINS:
        raise ValueError(f"Unknown relay: {relay_name}")
    
    pin = RELAY_PINS[relay_name]
    # Active-low boards: TRUE = drive LOW
    device = OutputDevice(pin, active_high=False)
    return device

def _get_caller_info() -> str:
    """Get caller information for debugging."""
    try:
        stack = inspect.stack()
        # Skip current function and set_relay/set_lights
        for frame_info in stack[1:4]:
            filename = frame_info.filename
            if 'relays_core.py' not in filename:
                module_name = filename.split('/')[-1].replace('.py', '')
                function_name = frame_info.function
                return f"{module_name}:{function_name}"
        return "unknown:unknown"
    except Exception:
        return "error:getting_caller"

def _log_relay_event(relay_name: str, requested: bool, final_state: bool, reason: str, 
                    cooldown: int = 0, blocked: bool = False):
    """Log relay event for debugging."""
    try:
        now_iso = datetime.now().isoformat()
        caller = _get_caller_info()
        
        event = {
            "ts": now_iso,
            "requested": requested,
            "final": final_state,
            "reason": reason,
            "cooldown": cooldown,
            "blocked": blocked,
            "caller": caller
        }
        
        _relay_event_logs[relay_name].append(event)
    except Exception as e:
        logger.error(f"Failed to log relay event: {e}")

def _update_antiflap_detector(relay_name: str, new_state: bool):
    """Update anti-flap detection for relay."""
    now = time.monotonic()
    history = _change_history[relay_name]
    history.append((now, new_state))
    
    # Check for excessive changes in last 5 minutes (more reasonable for manual testing)
    cutoff = now - 300  # 5 minutes
    recent_changes = [ts for ts, _ in history if ts > cutoff]
    
    # Increased threshold from 6 to 15 changes to avoid false triggers during testing
    if len(recent_changes) > 15:
        logger.warning(f"anti-flap: excessive changes on {relay_name} ({len(recent_changes)} in 5m), suppressing non-forced toggles for 2 minutes")
        _antiflap_until[relay_name] = now + 120  # 2 minutes (reduced from 5)

def set_relay(name: str, desired_on: bool, reason: str, force: bool = False) -> Dict[str, Any]:
    """
    Core relay control function - idempotent and rate-limited.
    
    Args:
        name: Relay name from RELAY_PINS
        desired_on: Desired state (True=ON, False=OFF)
        reason: Human-readable reason for change
        force: Skip cooldown and anti-flap protection
    
    Returns:
        Dict with changed, state, reason, cooldown_remaining
    """
    if name not in RELAY_PINS:
        return {"changed": False, "reason": f"unknown_relay: {name}"}
    
    now = time.monotonic()
    
    # Initialize device if needed
    if name not in _devices:
        _devices[name] = _initialize_device(name)
    
    device = _devices[name]
    current_state = _last_state.get(name, False)
    
    # Idempotent check
    if current_state == desired_on:
        return {
            "changed": False,
            "state": current_state,
            "reason": "idempotent",
            "cooldown_remaining": 0
        }
    
    if not force:
        # Anti-flap protection
        if name in _antiflap_until and now < _antiflap_until[name]:
            remaining = int(_antiflap_until[name] - now)
            return {
                "changed": False,
                "state": current_state,
                "reason": "antiflap",
                "cooldown_remaining": remaining
            }
        
        # Cooldown protection
        elapsed = _elapsed(name)
        if current_state:  # Currently ON, check MIN_ON
            min_on = _get_min_time(name, MIN_ON)
            if elapsed < min_on:
                remaining = int(min_on - elapsed)
                return {
                    "changed": False,
                    "state": current_state,
                    "reason": "cooldown",
                    "cooldown_remaining": remaining
                }
        else:  # Currently OFF, check MIN_OFF
            min_off = _get_min_time(name, MIN_OFF)
            if elapsed < min_off:
                remaining = int(min_off - elapsed)
                return {
                    "changed": False,
                    "state": current_state,
                    "reason": "cooldown",
                    "cooldown_remaining": remaining
                }
    
    # Execute the change
    try:
        device.value = desired_on
        _last_state[name] = desired_on
        _last_change_ts[name] = now
        _last_reason[name] = reason
        
        # Update anti-flap detector
        _update_antiflap_detector(name, desired_on)
        
        logger.info(f"relay {name} -> {'ON' if desired_on else 'OFF'} (reason={reason})")
        
        return {
            "changed": True,
            "state": desired_on,
            "reason": reason,
            "cooldown_remaining": 0
        }
    
    except Exception as e:
        logger.error(f"Failed to set relay {name}: {e}")
        return {
            "changed": False,
            "state": current_state,
            "reason": f"error: {e}",
            "cooldown_remaining": 0
        }

def initialize_all_safe_off():
    """Initialize all relays to safe OFF state at boot."""
    logger.info("Initializing all relays to safe OFF state")
    for relay_name in RELAY_PINS:
        if relay_name == "lights":
            # Use emergency reason for lights (whitelisted)
            set_lights(False, "emergency", force=True)
        else:
            # Use boot_safe_off for other relays
            set_relay(relay_name, False, "boot_safe_off", force=True)

def get_relay_status() -> Dict[str, Dict[str, Any]]:
    """Get status of all relays for diagnostics."""
    now = time.monotonic()
    status = {}
    
    for name in RELAY_PINS:
        state = _last_state.get(name, False)
        last_change = _last_change_ts.get(name, 0)
        seconds_since_change = int(now - last_change) if last_change else 0
        
        status[name] = {
            "state": state,
            "last_reason": _last_reason.get(name, "unknown"),
            "seconds_since_change": seconds_since_change,
            "antiflap_active": name in _antiflap_until and now < _antiflap_until[name]
        }
    
    return status

def get_antiflap_relays() -> list:
    """Get list of relays currently under anti-flap protection."""
    now = time.monotonic()
    return [name for name, until_time in _antiflap_until.items() if now < until_time]

# Convenience functions for specific relays
def set_lights(on: bool, reason: str, force: bool = False) -> Dict[str, Any]:
    """Set lights with strict whitelist protection and event logging."""
    current_state = _last_state.get("lights", False)
    
    # Check whitelist
    if reason not in WHITELIST_LIGHTS:
        logger.warning(f"lights BLOCKED: reason='{reason}' not whitelisted")
        _log_relay_event("lights", on, current_state, reason, 0, blocked=True)
        return {"changed": False, "reason": "blocked", "state": current_state}
    
    # Check temporary hold
    now = time.monotonic()
    if "lights" in _hold_until and now < _hold_until["lights"]:
        if on != current_state:
            remaining = int(_hold_until["lights"] - now)
            _log_relay_event("lights", on, current_state, reason, remaining, blocked=True)
            return {"changed": False, "reason": "hold_active", "cooldown_remaining": remaining}
    
    # Call normal relay control
    result = set_relay("lights", on, reason, force)
    
    # Log the event
    cooldown = result.get("cooldown_remaining", 0)
    blocked = not result.get("changed", False) and result.get("reason") in ("cooldown", "antiflap")
    _log_relay_event("lights", on, result.get("state", current_state), reason, cooldown, blocked)
    
    return result

def set_chiller_power(on: bool, reason: str, force: bool = False) -> Dict[str, Any]:
    return set_relay("chiller_power", on, reason, force)

def set_chiller_pump(on: bool, reason: str, force: bool = False) -> Dict[str, Any]:
    return set_relay("chiller_pump", on, reason, force)

def set_main_pump(on: bool, reason: str, force: bool = False) -> Dict[str, Any]:
    return set_relay("main_pump", on, reason, force)

def set_dosing_grow(on: bool, reason: str, force: bool = False) -> Dict[str, Any]:
    return set_relay("dosing_grow", on, reason, force)

def set_dosing_micro(on: bool, reason: str, force: bool = False) -> Dict[str, Any]:
    return set_relay("dosing_micro", on, reason, force)

def set_dosing_bloom(on: bool, reason: str, force: bool = False) -> Dict[str, Any]:
    return set_relay("dosing_bloom", on, reason, force)

def set_dosing_ph_up(on: bool, reason: str, force: bool = False) -> Dict[str, Any]:
    return set_relay("dosing_ph_up", on, reason, force)

# Generic set function
def set(name: str, on: bool, reason: str, force: bool = False) -> Dict[str, Any]:
    return set_relay(name, on, reason, force)

# Debug and monitoring functions
def get_relay_event_log(name: str = "lights", last: int = 100) -> List[Dict[str, Any]]:
    """Get recent event log for a relay."""
    events = list(_relay_event_logs.get(name, []))
    return events[-last:] if events else []

def allowed_lights_reasons() -> List[str]:
    """Get list of allowed reasons for lights control."""
    return sorted(list(WHITELIST_LIGHTS))

def set_hold(name: str, seconds: int):
    """Set temporary hold on relay for debugging."""
    _hold_until[name] = time.monotonic() + seconds

def set_lights_hold(seconds: int):
    """Set temporary hold on lights for debugging."""
    set_hold("lights", seconds)
    return {"hold_until": time.time() + seconds}