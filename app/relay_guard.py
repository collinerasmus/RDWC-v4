"""
Relay Guard Module - Safe GPIO control with active-low logic, shadow state, and anomaly detection.

Prime directive: No unintended relay toggles ever.

Electrical model (mixed NO/NC wiring after hardware change):
    - All physical relay boards are still active-low electrically (coil energized when BCM pin drives LOW).
    - MOST loads (dosing pumps, lights) remain on the relay's Normally Open (NO) contact:
                LOW (energize) -> closes NO -> device ON
                HIGH (de-energize) -> NO open -> device OFF
    - Critical circulation/cooling loads (main_pump, chiller_pump, chiller_power) have been rewired to Normally Closed (NC):
                LOW (energize) -> opens NC -> device OFF
                HIGH (de-energize) -> NC closed -> device ON (fail-safe on Pi crash / power loss)

Logical abstraction:
    desired_on == True  means "device should be ON" regardless of NO/NC wiring.
    We translate desired_on -> pin_level with per-relay inversion for NC group.

Resulting mapping implemented below:
    NO relays: desired_on -> GPIO.LOW, desired_off -> GPIO.HIGH
    NC relays: desired_on -> GPIO.HIGH, desired_off -> GPIO.LOW

Shadow state (_shadow_state[name]) always tracks logical device ON/OFF, never raw pin level.
"""
try:  # Hardware GPIO path (Pi)
    import RPi.GPIO as GPIO  # type: ignore
    _GPIO_AVAILABLE = True
except Exception:  # Fallback shim for dev/CI (Windows, non-Pi)
    _GPIO_AVAILABLE = False
    class _ShimGPIO:  # pragma: no cover - simulation only
        BCM = 11
        BOARD = 10
        OUT = 0
        IN = 1
        HIGH = 1
        LOW = 0
        def setmode(self, mode): pass
        def setwarnings(self, flag): pass
        def setup(self, pin, direction, initial=None): pass
        def output(self, pin, level): pass
        def input(self, pin): return self.HIGH  # default safe OFF
        def cleanup(self): pass
    GPIO = _ShimGPIO()  # type: ignore
    import logging as _lg
    _lg.getLogger(__name__).info("relay_guard using GPIO shim (RPi.GPIO not available)")
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
    # Use unified naming "chiller_power" to match relays_core
    'chiller_power': 20,
    'lights': 21,
}

# Relays rewired to NC (fail-safe ON when controller inactive / Pi crash)
NC_RELAYS = {'main_pump', 'chiller_pump', 'chiller_power'}
NO_RELAYS = {name for name in RELAY_PINS.keys() if name not in NC_RELAYS}

# Shadow state: logical ON/OFF (not pin levels)
_shadow_state: Dict[str, bool] = {}
_initialized = False
_anomaly_count = 0
_anomalies = []
# Recent guard events ring buffer (last N successful or attempted state changes)
_recent_events = []  # list[dict]; truncated to max 60 entries
_RECENT_MAX = 60

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
            # For NC loads OFF requires energizing coil (LOW). For NO loads OFF is HIGH.
            initial_level = GPIO.HIGH if name in NO_RELAYS else GPIO.LOW
            GPIO.setup(pin, GPIO.OUT, initial=initial_level)
            _shadow_state[name] = False  # Logical OFF regardless of pin wiring
            logger.info(f"[GuardInit] {name} (BCM {pin}) → OUTPUT {'HIGH' if initial_level==GPIO.HIGH else 'LOW'} (device OFF; wiring={'NC' if name in NC_RELAYS else 'NO'})")
        
        _initialized = True
        logger.info(f"[GuardInit] Initialized {len(pins_map)} relays; all safe OFF")
        
    except Exception as e:
        logger.error(f"[GuardInit] FAILED: {e}", exc_info=True)
        raise


def safe_set(name: str, desired_on: bool, reason: str, actor: str) -> dict:
    """
    Set relay state with active-low translation and no-op duplicate prevention.
    
    Args:
        name: Relay name (e.g., 'dosing_grow')
        desired_on: Logical state (True=ON, False=OFF)
        reason: Why this action (e.g., 'manual_dose', 'auto_ph_up')
        actor: Who triggered (e.g., 'user:192.168.88.46', 'controller:ph')
    
    Returns dict:
        {"changed": bool, "ok": bool, "coerced": bool, "mismatch_retries": int, "shadow": bool}
    """
    global _shadow_state, _anomaly_count
    
    if not _initialized:
        logger.error(f"[GuardSet] REJECTED {name}={desired_on}: relay_guard not initialized")
        return {"changed": False, "ok": False, "coerced": False, "mismatch_retries": 0, "shadow": _shadow_state.get(name, False)}
    
    if name not in RELAY_PINS:
        logger.error(f"[GuardSet] REJECTED unknown relay: {name}")
        return {"changed": False, "ok": False, "coerced": False, "mismatch_retries": 0, "shadow": _shadow_state.get(name, False)}
    
    # Check current shadow state
    current_on = _shadow_state.get(name, False)
    if current_on == desired_on:
        # No-op: already in desired state; still record an event for audit clarity
        logger.debug(f"[GuardSet] NO-OP {name} already {'ON' if desired_on else 'OFF'}")
        _append_recent({
            'ts': datetime.utcnow().isoformat(),
            'relay': name,
            'desired_on': desired_on,
            'final_on': current_on,
            'changed': False,
            'reason': reason,
            'actor': actor,
            'coerced': False,
            'mismatch_retries': 0,
            'status': 'noop'
        })
        return {"changed": False, "ok": True, "coerced": False, "mismatch_retries": 0, "shadow": current_on}
    
    # Translate logical to pin level with NO/NC awareness (still active-low electrically)
    pin = RELAY_PINS[name]
    if name in NC_RELAYS:
        # NC: ON => de-energize (HIGH), OFF => energize (LOW)
        pin_level = GPIO.HIGH if desired_on else GPIO.LOW
    else:
        # NO: ON => energize (LOW), OFF => de-energize (HIGH)
        pin_level = GPIO.LOW if desired_on else GPIO.HIGH
    
    # Single write
    mismatch_retries = 0
    try:
        GPIO.output(pin, pin_level)
        time.sleep(0.01)  # 10ms settle
        level_after = GPIO.input(pin)
        logical_after = (level_after == GPIO.LOW)
        if logical_after != desired_on:
            # First mismatch - retry once
            logger.warning(f"[GuardSet] GUARD_MISMATCH initial name={name} bcm={pin} expected={'LOW' if desired_on else 'HIGH'} actual={level_str(level_after)} reason={reason} actor={actor} retry=1")
            mismatch_retries = 1
            GPIO.output(pin, pin_level)
            time.sleep(0.01)
            level_after2 = GPIO.input(pin)
            logical_after2 = (level_after2 == GPIO.LOW)
            if logical_after2 != desired_on:
                # Persistent mismatch - coerce shadow to actual, record anomaly
                logger.error(f"[GuardSet] GUARD_MISMATCH persistent name={name} bcm={pin} expected={'LOW' if desired_on else 'HIGH'} actual={level_str(level_after2)} reason={reason} actor={actor} COERCE_SHADOW")
                _anomaly_count += 1
                _anomalies.append({
                    'ts': datetime.utcnow().isoformat(),
                    'relay': name,
                    'anomaly': 'mismatch_persistent',
                    'expected_on': desired_on,
                    'actual_on': logical_after2,
                    'reason': reason,
                    'actor': actor
                })
                _shadow_state[name] = logical_after2
                caller_frame = traceback.extract_stack()[-2]
                caller_loc = f"{caller_frame.filename}:{caller_frame.lineno}"
                mono_ts = time.monotonic()
                _append_recent({
                    'ts': datetime.utcnow().isoformat(),
                    'relay': name,
                    'desired_on': desired_on,
                    'final_on': logical_after2,
                    'changed': logical_after2 != current_on,
                    'reason': reason,
                    'actor': actor,
                    'coerced': True,
                    'mismatch_retries': mismatch_retries,
                    'status': 'mismatch_persistent'
                })
                return {"changed": logical_after2 != current_on, "ok": False, "coerced": True, "mismatch_retries": mismatch_retries, "shadow": _shadow_state[name], "caller": caller_loc, "mono_ts": mono_ts}
        # Success path
        _shadow_state[name] = desired_on
        caller_frame = traceback.extract_stack()[-2]
        caller_loc = f"{caller_frame.filename}:{caller_frame.lineno}"
        mono_ts = time.monotonic()
        logger.info(
            f"[RelayGuard] {name} bcm={pin} → {'ON' if desired_on else 'OFF'} reason={reason} actor={actor} caller={caller_loc} mono_ts={mono_ts:.3f} retries={mismatch_retries}"
        )
        _append_recent({
            'ts': datetime.utcnow().isoformat(),
            'relay': name,
            'desired_on': desired_on,
            'final_on': desired_on,
            'changed': True,
            'reason': reason,
            'actor': actor,
            'coerced': False,
            'mismatch_retries': mismatch_retries,
            'status': 'ok'
        })
        return {"changed": True, "ok": True, "coerced": False, "mismatch_retries": mismatch_retries, "shadow": desired_on, "caller": caller_loc, "mono_ts": mono_ts}
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
        _append_recent({
            'ts': datetime.utcnow().isoformat(),
            'relay': name,
            'desired_on': desired_on,
            'final_on': current_on,
            'changed': False,
            'reason': reason,
            'actor': actor,
            'coerced': False,
            'mismatch_retries': mismatch_retries,
            'status': 'error',
            'error': str(e)
        })
        return {"changed": False, "ok": False, "coerced": False, "mismatch_retries": mismatch_retries, "shadow": current_on}


def get_shadow_state() -> Dict[str, bool]:
    """Return current logical ON/OFF map (shadow state)."""
    return _shadow_state.copy()


def sync_from_actual():
    """
    Sync shadow state from actual pin levels (for startup reconciliation).
    Call this after relays_core initialization to avoid false anomalies.
    """
    global _shadow_state
    
    if not _initialized:
        logger.warning("relay_guard not initialized; cannot sync from actual")
        return
    
    for name, pin in RELAY_PINS.items():
        try:
            level = GPIO.input(pin)
            if name in NC_RELAYS:
                # NC wiring: HIGH (de-energized) closes NC -> device ON
                logical_on = (level == GPIO.HIGH)
            else:
                # NO wiring: LOW (energized) closes NO -> device ON
                logical_on = (level == GPIO.LOW)
            _shadow_state[name] = logical_on
            logger.info(f"[GuardSync] {name}: actual={level_str(level)} → shadow={'ON' if logical_on else 'OFF'}")
        except Exception as e:
            logger.error(f"[GuardSync] Failed to read {name} (BCM {pin}): {e}")

def level_str(level):
    """Helper to convert GPIO level to string"""
    return 'LOW' if level == GPIO.LOW else 'HIGH'

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

def _append_recent(ev: dict):
    """Internal: append event to ring buffer."""
    try:
        _recent_events.append(ev)
        # Trim if exceeded
        if len(_recent_events) > _RECENT_MAX:
            del _recent_events[0:len(_recent_events)-_RECENT_MAX]
    except Exception:
        pass

def get_recent_guard_events(limit: int = 50) -> Dict[str, list]:
    """Return recent guard events (up to limit)."""
    lim = max(1, min(limit, _RECENT_MAX))
    return {"events": _recent_events[-lim:]}


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
