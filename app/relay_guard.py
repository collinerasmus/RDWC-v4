"""
Relay Guard Module - Safe GPIO control with active-low logic, shadow state, and anomaly detection.

Prime directive: No unintended relay toggles ever.
Active-low: HIGH = OFF (safe), LOW = ON (energized).
"""
import RPi.GPIO as GPIO
import time
import logging
import traceback
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# BCM pin mapping (active-low relays)
RELAY_PINS = {
    'dosing_grow': 6,
    'dosing_micro': 13,
    'dosing_bloom': 19,
    'dosing_ph_up': 5,
    'main_pump': 26,
    'chiller_pump': 16,
    'chiller': 20,
    'lights': 21,
}

# Shadow state: logical ON/OFF (not pin levels)
_shadow_state: Dict[str, bool] = {}
_initialized = False
_anomaly_count = 0
_anomalies = []

def init_safe(relays: Optional[Dict[str, int]] = None):
    """
    Initialize GPIO pins to safe OFF state (active-low HIGH).
    Called once at app startup AFTER ExecStartPre safe-off script.
    
    Args:
        relays: Optional relay mapping; defaults to RELAY_PINS if None
    """
    global _shadow_state, _initialized
    
    if _initialized:
        logger.warning("relay_guard already initialized; skipping re-init")
        return
    
    pins_map = relays or RELAY_PINS
    
    try:
        # Use BCM numbering
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Set each pin to OUTPUT with initial HIGH (OFF)
        # Note: pull_up_down is not valid for outputs
        for name, pin in pins_map.items():
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
            _shadow_state[name] = False  # Logical OFF
            logger.info(f"[GuardInit] {name} (BCM {pin}) → OUTPUT HIGH (OFF)")
        
        _initialized = True
        logger.info(f"[GuardInit] Initialized {len(pins_map)} relays; all safe OFF")
        
    except Exception as e:
        logger.error(f"[GuardInit] FAILED: {e}", exc_info=True)
        raise


def safe_set(name: str, desired_on: bool, reason: str, actor: str) -> bool:
    """
    Set relay state with active-low translation and no-op duplicate prevention.
    
    Args:
        name: Relay name (e.g., 'dosing_grow')
        desired_on: Logical state (True=ON, False=OFF)
        reason: Why this action (e.g., 'manual_dose', 'auto_ph_up')
        actor: Who triggered (e.g., 'user:192.168.88.46', 'controller:ph')
    
    Returns:
        True if state changed, False if no-op
    """
    global _shadow_state, _anomaly_count
    
    if not _initialized:
        logger.error(f"[GuardSet] REJECTED {name}={desired_on}: relay_guard not initialized")
        return False
    
    if name not in RELAY_PINS:
        logger.error(f"[GuardSet] REJECTED unknown relay: {name}")
        return False
    
    # Check current shadow state
    current_on = _shadow_state.get(name, False)
    if current_on == desired_on:
        # No-op: already in desired state
        logger.debug(f"[GuardSet] NO-OP {name} already {'ON' if desired_on else 'OFF'}")
        return False
    
    # Translate logical to pin level (active-low)
    pin = RELAY_PINS[name]
    pin_level = GPIO.LOW if desired_on else GPIO.HIGH
    
    # Single write
    try:
        GPIO.output(pin, pin_level)
        _shadow_state[name] = desired_on
        
        # Structured log with monotonic timestamp and caller trace
        caller_frame = traceback.extract_stack()[-2]
        caller_loc = f"{caller_frame.filename}:{caller_frame.lineno}"
        mono_ts = time.monotonic()
        
        logger.info(
            f"[GuardSet] {name} (BCM {pin}) → {'ON' if desired_on else 'OFF'} | "
            f"reason={reason} actor={actor} caller={caller_loc} mono_ts={mono_ts:.3f}"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"[GuardSet] FAILED {name}: {e}", exc_info=True)
        _anomaly_count += 1
        _anomalies.append({
            'ts': datetime.utcnow().isoformat(),
            'relay': name,
            'error': str(e),
            'desired_on': desired_on,
            'reason': reason,
            'actor': actor
        })
        return False


def get_shadow_state() -> Dict[str, bool]:
    """Return current logical ON/OFF map (shadow state)."""
    return _shadow_state.copy()


def get_pin_levels() -> Dict[str, str]:
    """Read actual GPIO pin levels (for watchdog verification)."""
    if not _initialized:
        return {}
    
    levels = {}
    for name, pin in RELAY_PINS.items():
        try:
            level = GPIO.input(pin)
            # Translate to string for clarity
            levels[name] = 'LOW' if level == GPIO.LOW else 'HIGH'
        except Exception as e:
            levels[name] = f'ERROR:{e}'
            logger.error(f"[GuardRead] Failed to read {name} (BCM {pin}): {e}")
    
    return levels


def force_off(name: str, anomaly_reason: str):
    """
    Force a relay OFF and log as ANOMALY.
    Called by watchdog when unexpected energization detected.
    """
    global _anomaly_count, _anomalies
    
    logger.warning(f"[GuardANOMALY] Forcing {name} OFF: {anomaly_reason}")
    
    success = safe_set(name, False, reason=f"anomaly:{anomaly_reason}", actor="watchdog")
    
    _anomaly_count += 1
    _anomalies.append({
        'ts': datetime.utcnow().isoformat(),
        'relay': name,
        'anomaly': anomaly_reason,
        'forced_off': success
    })


def get_anomalies() -> Dict:
    """Return anomaly count and recent anomaly log."""
    return {
        'count': _anomaly_count,
        'anomalies': _anomalies[-50:]  # Last 50 anomalies
    }


def cleanup():
    """Cleanup GPIO on shutdown (optional; systemd handles restart)."""
    global _initialized
    if _initialized:
        try:
            GPIO.cleanup()
            logger.info("[GuardCleanup] GPIO cleanup complete")
        except Exception as e:
            logger.error(f"[GuardCleanup] Failed: {e}")
        finally:
            _initialized = False
