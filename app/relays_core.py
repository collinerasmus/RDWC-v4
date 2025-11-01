"""
Centralized relay control - THE ONLY place that touches GPIO.
Provides idempotent, rate-limited relay control with anti-flap protection.
"""
import time
import inspect
import json
import os
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
# Optimized for responsive manual control with minimal protection
MIN_ON = {
    # Tuned per request: quick manual response; only chiller power needs 60s
    "chiller_power": 60,   # 60 seconds ON minimum (compressor safety)
    "chiller_pump": 0,     # match main_pump: no switch-off hold
    "main_pump": 0,        # allow immediate OFF after ON
    "lights": 10,          # 10 seconds ON minimum
    "dosing_*": 0,         # No restriction
    "ph_*": 0,             # No restriction
}

MIN_OFF = {
    # Tuned per request: only chiller power needs 60s cooldown
    "chiller_power": 60,   # 60 seconds OFF minimum (compressor anti-short-cycle)
    "chiller_pump": 5,     # same as main pump
    "main_pump": 5,        # 5 seconds
    "lights": 5,           # 5 seconds OFF minimum
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
    "emergency",             # REASON_EMERGENCY - emergency shutdown
    "restore"                # State restoration after restart/power failure
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
_estop_active: bool = False  # Global emergency stop (latching)

# Persistence
_STATE_FILE = os.path.expanduser("~/.rdwc/relay_state.json")

def _refresh_lockouts_from_settings():
    """Refresh MIN_ON/MIN_OFF from namespaced settings if available.
    Keeps existing defaults if keys are missing or settings module unavailable.
    """
    try:
        from app.settings import get_setting_key
        def geti(key, default):
            try:
                v = int(float(get_setting_key(key, str(default)) or default))
                return max(0, v)
            except Exception:
                return default
        # Update OFF lockouts
        MIN_OFF.update({
            "main_pump": geti("safety.main_pump_min_off_s", MIN_OFF.get("main_pump", 5)),
            "chiller_pump": geti("safety.chiller_pump_min_off_s", MIN_OFF.get("chiller_pump", 5)),
            "chiller_power": geti("safety.chiller_min_off_s", MIN_OFF.get("chiller_power", 60)),
        })
        # Update ON minimums
        MIN_ON.update({
            "chiller_power": geti("safety.chiller_min_on_s", MIN_ON.get("chiller_power", 60)),
        })
    except Exception:
        # Silent fallback to hardcoded defaults
        pass

def _save_state():
    """Save relay states to disk and database for persistence across restarts."""
    try:
        # Legacy file-based persistence
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        state = {name: _last_state.get(name, False) for name in RELAY_PINS.keys()}
        with open(_STATE_FILE, 'w') as f:
            json.dump(state, f)
        
        # Database persistence for system_mode auto-restore
        from app.system_mode import save_relay_state
        for name, state_val in state.items():
            save_relay_state(name, state_val)
    except Exception as e:
        logger.error(f"Failed to save relay state: {e}")

def _load_state():
    """Load and restore relay states from disk after restart (legacy file-based)."""
    try:
        if os.path.exists(_STATE_FILE):
            with open(_STATE_FILE, 'r') as f:
                state = json.load(f)
            logger.info(f"Restoring relay states from {_STATE_FILE}")
            for name, desired_state in state.items():
                if name in RELAY_PINS:
                    # Restore state with force=True to bypass cooldowns
                    set_relay(name, desired_state, reason="restore", force=True)
            logger.info("Relay state restoration complete")
    except Exception as e:
        logger.error(f"Failed to load relay state: {e}")

def smart_restore_critical_relays():
    """
    Smart restoration of critical relays respecting lockouts.
    Called on boot if system_mode is 'auto'.
    Only restores critical relays (main_pump, chiller_pump, chiller_power, lights).
    Respects MIN_OFF timings - if a relay can't be turned on immediately, it stays off.
    """
    from app.system_mode import should_auto_restore, get_critical_relay_states
    
    if not should_auto_restore():
        logger.info("System mode is manual - skipping auto-restore")
        return
    
    logger.info("System mode is auto - beginning smart restore of critical relays")
    
    saved_states = get_critical_relay_states()
    
    for relay_name, (desired_state, saved_ts) in saved_states.items():
        if not desired_state:
            # Relay was OFF - keep it OFF
            logger.debug(f"Relay {relay_name} was OFF - keeping OFF")
            continue
        
        # Relay was ON - try to restore
        logger.info(f"Attempting to restore {relay_name} to ON (was ON at {saved_ts})")
        
        # Try to set with reason="restore" and force=False to respect lockouts
        result = set_relay(relay_name, True, reason="restore", force=False)
        
        if result.get("changed"):
            logger.info(f"✓ Restored {relay_name} to ON")
        else:
            reason = result.get("reason", "unknown")
            cooldown = result.get("cooldown_remaining", 0)
            
            if reason == "cooldown":
                logger.warning(
                    f"✗ Cannot restore {relay_name} - min-off protection active "
                    f"(cooldown: {cooldown}s remaining)"
                )
            elif reason == "antiflap":
                logger.warning(
                    f"✗ Cannot restore {relay_name} - antiflap protection active "
                    f"({cooldown}s remaining)"
                )
            else:
                logger.info(f"Relay {relay_name} already in desired state")
    
    logger.info("Critical relay restoration complete")

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
        # Return a large value to allow immediate toggling on first use
        return 999999
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
    """Update anti-flap detection for relay (production policy)."""
    now = time.monotonic()
    history = _change_history[relay_name]
    history.append((now, new_state))

    # Production policy: back off if >6 toggles in 10 minutes
    cutoff = now - 600  # 10 minutes
    recent_changes = [ts for ts, _ in history if ts > cutoff]

    if len(recent_changes) > 6:
        logger.warning(
            f"anti-flap: excessive changes on {relay_name} ({len(recent_changes)} in 10m), suppressing non-forced toggles for 5 minutes"
        )
        _antiflap_until[relay_name] = now + 300  # 5 minutes

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

    # Emergency stop behavior: latching block for ON; force OFF allowed
    if _estop_active:
        if desired_on:
            _log_relay_event(name, True, current_state, "estop_active", 0, blocked=True)
            return {
                "changed": False,
                "state": current_state,
                "reason": "estop_active",
                "cooldown_remaining": 0
            }
        else:
            # Force OFF regardless of cooldown/antiflap
            force = True
    
    # Idempotent check (skip only when not forcing)
    # When force=True (e.g., during E-STOP or boot safe-off), we still drive
    # the physical pin to the desired state to guarantee hardware sync even
    # if our cached _last_state already matches.
    if current_state == desired_on and not force:
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
        
        # Save state to disk for persistence across restarts
        _save_state()
        
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
    # Backdate timestamps so UI/tests don't see initial cooldown locks
    now = time.monotonic()
    for relay_name in RELAY_PINS:
        _last_change_ts[relay_name] = now - 1000

# Refresh lockouts on import
_refresh_lockouts_from_settings()

def get_relay_status() -> Dict[str, Dict[str, Any]]:
    """Get status of all relays for diagnostics with lockout information."""
    now = time.monotonic()
    status = {}
    
    for name in RELAY_PINS:
        state = _last_state.get(name, False)
        last_change = _last_change_ts.get(name, 0)
        seconds_since_change = int(now - last_change) if last_change else 0
        
        # Calculate lockout information
        lockout_info = {
            "active": False,
            "seconds_remaining": 0,
            "reason": None
        }
        
        # Check antiflap protection
        if name in _antiflap_until and now < _antiflap_until[name]:
            lockout_info["active"] = True
            lockout_info["seconds_remaining"] = int(_antiflap_until[name] - now)
            lockout_info["reason"] = "antiflap"
        else:
            # Check MIN_ON/MIN_OFF cooldowns
            elapsed = seconds_since_change
            if state:  # Currently ON, check MIN_ON
                min_on = _get_min_time(name, MIN_ON)
                if elapsed < min_on:
                    lockout_info["active"] = True
                    lockout_info["seconds_remaining"] = int(min_on - elapsed)
                    lockout_info["reason"] = "min_on"
            else:  # Currently OFF, check MIN_OFF
                min_off = _get_min_time(name, MIN_OFF)
                if elapsed < min_off:
                    lockout_info["active"] = True
                    lockout_info["seconds_remaining"] = int(min_off - elapsed)
                    lockout_info["reason"] = "min_off"
        
        status[name] = {
            "state": state,
            "last_reason": _last_reason.get(name, "unknown"),
            "seconds_since_change": seconds_since_change,
            "antiflap_active": name in _antiflap_until and now < _antiflap_until[name],
            "lockout": lockout_info
        }
    
    return status

def get_antiflap_relays() -> list:
    """Get list of relays currently under anti-flap protection."""
    now = time.monotonic()
    return [name for name, until_time in _antiflap_until.items() if now < until_time]

# --- Emergency Stop (latching) ----------------------------------------------
def engage_estop() -> Dict[str, Any]:
    """Engage E-Stop: latch active, force all relays OFF immediately."""
    global _estop_active
    _estop_active = True
    results = {}
    try:
        # Clear antiflap to avoid residual lockouts post-release
        _antiflap_until.clear()
        # Turn everything OFF with force, using lights-specific helper for whitelist
        for relay_name in RELAY_PINS.keys():
            if relay_name == "lights":
                res = set_lights(False, REASON_EMERGENCY, force=True)
            else:
                res = set_relay(relay_name, False, REASON_EMERGENCY, force=True)
            results[relay_name] = {"changed": res.get("changed", False), "state": res.get("state", False)}
        # Backdate last change timestamps so UI shows no cooldown
        now = time.monotonic()
        for relay_name in RELAY_PINS.keys():
            _last_change_ts[relay_name] = now - 1000
    except Exception as e:
        logger.error(f"engage_estop error: {e}")
    return {"active": True, "results": results}

def release_estop() -> Dict[str, Any]:
    """Release E-Stop latch: allow normal operation again (does not auto-restore)."""
    global _estop_active
    _estop_active = False
    return {"active": False}

def get_estop_status() -> bool:
    return bool(_estop_active)

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