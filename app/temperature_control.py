"""
Intelligent temperature Control for RDWC System
Hailea HS-52A (1/10 HP) - Optimized for Cannabis Cultivation

Features:
- Temperature-based automation with hysteresis
- Compressor protection (min ON/OFF times)
- RDWC coordination (requires main pump + temperature pump)
- Energy-efficient scheduling
- Strain-specific temperature targets
"""
import time
import threading
import logging
import os
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies
def get_relay_status():
    from app.relays_core import get_relay_status as _get_relay_status
    return _get_relay_status()

def relay_set(name: str, on: bool, reason: str = '', actor: str = 'temperature-ctl'):
    from app.relays_core import set_relay as _set_relay
    return _set_relay(name, on, reason=reason, actor=actor)

def get_setting(key: str, default: str = ""):
    from app.settings import get_all_settings
    settings = get_all_settings()
    val = settings.get(key)
    return val if val is not None else default

def set_setting(key: str, value: str):
    from app.settings import upsert_settings
    upsert_settings({key: value})

def should_automate_temperature():
    """Check if temperature automation should run using the CLEAN auto-enable system.
    
    Returns True ONLY if:
    - Global auto is enabled AND
    - chiller-specific auto is enabled
    
    Note: Uses "chiller" key to match unified auto system controller naming.
    """
    from app.auto_control import should_automate
    return should_automate("chiller")

def get_latest_reading():
    """Get cached sensor reading from main app's background loop."""
    try:
        # Import the cached sensor data from main.py
        from app.main import _last, _last_t
        import time
        
        # Check if cache is reasonably fresh (within 60 seconds)
        age = time.time() - _last_t
        if age < 60:
            return {
                'temperature_c': _last.get('temp_c'),
                'ec_mscm': _last.get('ec_ms_cm'),
                'ph': _last.get('ph'),
                'online': True,
                'age_seconds': age
            }
        return None
    except ImportError:
        return None

# temperature state tracking
_temperature_state = {
    'last_on_time': None,      # timestamp when temperature turned ON
    'last_off_time': None,     # timestamp when temperature turned OFF
    'is_running': False,       # current state
    'in_cooldown': False,      # true if in minimum OFF period
    'min_runtime_active': False,  # true if in minimum ON period
    'override_until': None,    # timestamp for manual override expiry
    'total_runtime_today': 0,  # seconds of runtime today (for stats)
    'cycles_today': 0,         # number of on/off cycles today
    # NOTE: 'auto_enabled' is computed dynamically from unified auto_control system (single source of truth)
}

_control_lock = threading.Lock()
_control_thread = None
_stop_control = False

# Cannabis-specific optimal water temperatures (°C)
# Source: Industry best practices for DWC/RDWC systems
CANNABIS_TEMP_RANGES = {
    'optimal': {
        'veg': (18.0, 20.0),      # Vegetative stage
        'flower': (18.0, 20.0),    # Flowering stage
        'default': (18.0, 20.0)    # General recommendation
    },
    'acceptable': {
        'min': 16.0,  # Below this: slow growth, nutrient uptake issues
        'max': 24.0,  # Above this: root rot risk, dissolved O2 drops
    },
    'critical': {
        'min': 14.0,  # Below this: plant stress
        'max': 26.0,  # Above this: serious pathogen risk
    }
}

# Hailea HS-52A Specifications
# Cooling Capacity: 160W (for water volume ~50-150L)
# Compressor: Rotary type (requires proper cycling)
# Typical cycle: 5-15 minutes ON per cycle
temperature_SPECS = {
    'model': 'Hailea HS-52A',
    'cooling_capacity_watts': 160,
    'recommended_volume_liters': (50, 150),
    # Defaults per approved brief (compressor-safe but responsive):
    # min_off_seconds: 300 (5 min cooldown), min_on_seconds: 60 (≥1 min runtime), hysteresis default 0.7°C
    'min_on_seconds': 60,
    'min_off_seconds': 300,
    'max_cycles_per_hour': 8,   # Allow up to 8 safe cycles/hour given shorter min_on
}


# --- Events logging (SQLite) -------------------------------------------------
_EVENTS_TABLE = "temperature_events"

def _db_conn():
    path = os.environ.get("RDWC_DB", "data/rdwc.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_events_table():
    try:
        with _db_conn() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_EVENTS_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_utc INTEGER NOT NULL,
                    prev_state TEXT NOT NULL,
                    new_state TEXT NOT NULL,
                    reason TEXT
                )
                """
            )
            conn.commit()
    except Exception as e:
        log.error(f"[temperature] Failed to ensure events table: {e}")

def _log_event(prev_state: str, new_state: str, reason: str = ""):
    """Persist a temperature state transition event."""
    try:
        with _db_conn() as conn:
            conn.execute(
                f"INSERT INTO {_EVENTS_TABLE} (ts_utc, prev_state, new_state, reason) VALUES (?,?,?,?)",
                (int(time.time()), prev_state, new_state, reason)
            )
            conn.commit()
    except Exception as e:
        log.error(f"[temperature] Failed to log event: {e}")

def get_temperature_events(limit: int = 200) -> list[dict]:
    """Return most recent temperature state transition events (newest first)."""
    try:
        with _db_conn() as conn:
            cur = conn.execute(
                f"SELECT ts_utc, prev_state, new_state, reason FROM {_EVENTS_TABLE} ORDER BY ts_utc DESC LIMIT ?",
                (int(limit),)
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        log.error(f"[temperature] Failed to fetch events: {e}")
        return []


def get_interlock_status() -> Dict[str, Any]:
    """
    Check current interlock conditions for temperature operation.
    
    Returns:
        Dict with interlock_ok (bool) and interlock_details (dict)
    """
    try:
        relays = get_relay_status()
        main_pump_on = relays.get('main_pump', {}).get('state', False)
        chiller_pump_on = relays.get('chiller_pump', {}).get('state', False)
        chiller_running = relays.get('chiller_power', {}).get('state', False)
        
        # NEW: Use unified auto-enable system
        auto_enabled = should_automate_temperature()
        
        # Determine violations
        violations = []
        if chiller_running and not main_pump_on:
            violations.append('main_pump_off')
        if chiller_running and not chiller_pump_on:
            violations.append('chiller_pump_off')
        
        interlock_ok = len(violations) == 0
        
        return {
            'interlock_ok': interlock_ok,
            'interlock_details': {
                'main_pump_on': main_pump_on,
                'chiller_pump_on': chiller_pump_on,
                'chiller_running': chiller_running,
                'auto_enabled': auto_enabled,
                'violations': violations if violations else None
            }
        }
    except Exception as e:
        log.error(f'[temperature] Failed to get interlock status: {e}')
        return {
            'interlock_ok': False,
            'interlock_details': {
                'main_pump_on': False,
                'chiller_pump_on': False,
                'chiller_running': False,
                'auto_enabled': False,
                'violations': ['error_reading_status']
            }
        }


def get_temperature_state() -> Dict[str, Any]:
    """Get current temperature state for API/UI."""
    with _control_lock:
        state = _temperature_state.copy()
        # Reconcile with actual relay state to avoid stale/is_running mismatches
        try:
            rel = get_relay_status().get('temperature_power', {})
            relay_on = bool(rel.get('state')) or bool(rel.get('is_on'))  # support both key styles
        except Exception:
            relay_on = state.get('is_running', False)
        now_reconcile = time.time()
        # If relay physically ON but internal state says OFF, treat as ON transition
        if relay_on and not state.get('is_running'):
            _temperature_state['is_running'] = True
            # If we have no last_on_time this is a fresh ON transition not yet counted
            if not _temperature_state.get('last_on_time'):
                _temperature_state['last_on_time'] = now_reconcile
                _temperature_state['cycles_today'] += 1  # count cycle only once
            _temperature_state['last_off_time'] = None
            _temperature_state['in_cooldown'] = False
            state = _temperature_state.copy()
        # If relay physically OFF but internal state says ON, treat as OFF transition
        elif (not relay_on) and state.get('is_running'):
            _temperature_state['is_running'] = False
            _temperature_state['last_off_time'] = now_reconcile
            _temperature_state['min_runtime_active'] = False
            state = _temperature_state.copy()
        
        # Add computed fields
        now = time.time()
        if state['last_off_time']:
            state['seconds_since_off'] = int(now - state['last_off_time'])
        if state['last_on_time'] and state['is_running']:
            state['current_runtime'] = int(now - state['last_on_time'])
        
        # Add settings
        # Unified target temp: prefer temperature.target_temp, fallback to legacy targets.temp_target_c
        _t = get_setting('temperature.target_temp', None)
        if _t is None:
            _t = get_setting('targets.temp_target_c', '19.0')
        state['target_temp'] = float(_t)
        state['hysteresis'] = float(get_setting('temperature.hysteresis', '0.5'))
        state['stage'] = get_setting('temperature.stage', 'default')
        # NEW: Use unified auto-enable system
        state['auto_enabled'] = should_automate_temperature()
        
        # Add interlock status
        interlock_status = get_interlock_status()
        state.update(interlock_status)
        
        return state


def set_temperature_relay(desired_on: bool, reason: str = '') -> bool:
    """
    Control temperature relay with safety checks.
    
    Args:
        desired_on: True to turn ON, False to turn OFF
        reason: Log message explaining the action
    
    Returns:
        True if relay was set, False if blocked
    """
    with _control_lock:
        # Check RDWC coordination: require main_pump + temperature_pump
        if desired_on:
            relays = get_relay_status()
            main_pump_on = relays.get('main_pump', {}).get('state', False)
            temperature_pump_on = relays.get('temperature_pump', {}).get('state', False)
            
            if not main_pump_on:
                log.warning('[temperature] Blocked: Main pump is OFF (RDWC circulation required)')
                return False
            
            if not temperature_pump_on:
                log.warning('[temperature] Blocked: temperature pump is OFF (water circulation required)')
                return False
        
        # Check minimum OFF time (compressor protection)
        if desired_on and _temperature_state['last_off_time']:
            now = time.time()
            min_off = int(get_setting('temperature.min_off_seconds', str(temperature_SPECS['min_off_seconds'])))
            time_since_off = now - _temperature_state['last_off_time']
            
            if time_since_off < min_off:
                remaining = int(min_off - time_since_off)
                log.info(f'[temperature] Blocked: In cooldown period ({remaining}s remaining)')
                _temperature_state['in_cooldown'] = True
                return False
            else:
                _temperature_state['in_cooldown'] = False
        
        # Check minimum ON time (don't short-cycle)
        if not desired_on and _temperature_state['is_running'] and _temperature_state['last_on_time']:
            now = time.time()
            min_on = int(get_setting('temperature.min_on_seconds', str(temperature_SPECS['min_on_seconds'])))
            runtime = now - _temperature_state['last_on_time']
            
            if runtime < min_on:
                remaining = int(min_on - runtime)
                log.info(f'[temperature] Blocked OFF: Minimum runtime active ({remaining}s remaining)')
                _temperature_state['min_runtime_active'] = True
                return False
            else:
                _temperature_state['min_runtime_active'] = False
        
        # Set relay
        try:
            relay_set('chiller_power', desired_on, reason=reason, actor='temperature-ctl')
            
            # Update state
            now = time.time()
            prev = 'ON' if _temperature_state['is_running'] else 'OFF'
            if desired_on:
                _temperature_state['last_on_time'] = now
                _temperature_state['is_running'] = True
                _temperature_state['cycles_today'] += 1
                log.info(f'[temperature] ON: {reason}')
                _log_event(prev, 'ON', reason)
            else:
                if _temperature_state['last_on_time']:
                    runtime = now - _temperature_state['last_on_time']
                    _temperature_state['total_runtime_today'] += runtime
                _temperature_state['last_off_time'] = now
                _temperature_state['is_running'] = False
                log.info(f'[temperature] OFF: {reason}')
                _log_event(prev, 'OFF', reason)
            
            return True
            
        except Exception as e:
            log.error(f'[temperature] Relay set failed: {e}')
            return False


def get_current_water_temp() -> Optional[float]:
    """Get current water temperature from sensors, with database fallback."""
    try:
        # Try live sensor reading first
        reading = get_latest_reading()
        if reading and reading.get('temperature_c') is not None:
            return float(reading['temperature_c'])
    except Exception as e:
        log.warning(f'[temperature] Live sensor read failed: {e}')
    
    # Fallback to last database reading (within 5 minutes)
    try:
        from app.services.sensors_fallback import get_last_reading
        db_reading = get_last_reading()
        if db_reading and db_reading.get('temperature_c') is not None:
            stale_seconds = db_reading.get('stale_seconds', 999999)
            if stale_seconds is not None and stale_seconds < 300:  # Max 5 minutes old
                log.info(f'[temperature] Using database temp (age: {stale_seconds}s)')
                return float(db_reading['temperature_c'])
            else:
                log.warning(f'[temperature] Database temp too stale ({stale_seconds}s)')
    except Exception as e:
        log.error(f'[temperature] Database fallback failed: {e}')
    
    return None


def should_temperature_run() -> tuple[bool, str]:
    """
    Determine if temperature should be running based on temperature and settings.
    
    Returns:
        (should_run, reason) tuple
    """
    # NEW: Use unified auto-enable system
    auto_enabled = should_automate_temperature()
    if not auto_enabled:
        return False, 'Auto control disabled'
    
    # Check interlocks first
    interlock_status = get_interlock_status()
    if not interlock_status['interlock_ok']:
        violations = interlock_status['interlock_details'].get('violations', [])
        return False, f'Interlock violation(s): {violations}'
    
    # Get current temp
    current_temp = get_current_water_temp()
    if current_temp is None:
        return False, 'Temperature sensor unavailable'
    
    # Get target and hysteresis
    target_temp = float(get_setting('temperature.target_temp', '19.0'))
    hysteresis = float(get_setting('temperature.hysteresis', '0.5'))
    
    # Calculate thresholds
    turn_on_temp = target_temp + hysteresis   # e.g., 19.5°C
    turn_off_temp = target_temp - hysteresis  # e.g., 18.5°C
    
    # Hysteresis logic
    if _temperature_state['is_running']:
        # Currently running: turn off when below turn_off_temp
        if current_temp <= turn_off_temp:
            return False, f'Temp {current_temp:.1f}°C below turn-off threshold {turn_off_temp:.1f}°C'
        else:
            return True, f'Maintaining cooling (temp {current_temp:.1f}°C above {turn_off_temp:.1f}°C)'
    else:
        # Currently off: turn on when above turn_on_temp
        if current_temp >= turn_on_temp:
            return True, f'Temp {current_temp:.1f}°C above turn-on threshold {turn_on_temp:.1f}°C'
        else:
            return False, f'Temp {current_temp:.1f}°C below turn-on threshold {turn_on_temp:.1f}°C'


def control_loop():
    """Background thread: periodically check temperature and control temperature."""
    global _stop_control
    log.info('[temperature] Control loop started')
    
    while not _stop_control:
        try:
            # Check if we should run
            should_run, reason = should_temperature_run()
            log.debug(f'[temperature] Control check: should_run={should_run}, reason={reason}')
            
            # Apply decision
            if should_run != _temperature_state['is_running']:
                log.info(f'[temperature] State change: {_temperature_state["is_running"]} -> {should_run}, {reason}')
                set_temperature_relay(should_run, reason)
            
            # Check for midnight reset (daily stats)
            now = datetime.now()
            if now.hour == 0 and now.minute < 1:
                with _control_lock:
                    _temperature_state['total_runtime_today'] = 0
                    _temperature_state['cycles_today'] = 0
            
        except Exception as e:
            log.error(f'[temperature] Control loop error: {e}', exc_info=True)
        
        # Sleep for control interval (default 30 seconds)
        time.sleep(int(get_setting('temperature.control_interval_s', '30')))
    
    log.info('[temperature] Control loop stopped')


def start_auto_control():
    """Start automated temperature control.
    
    NOTE: This starts the background control thread. The actual automation
    will only run if should_automate("chiller") returns True (requires both
    global_auto and chiller_auto to be enabled in the unified auto-control system).
    """
    global _control_thread, _stop_control
    
    if _control_thread and _control_thread.is_alive():
        log.warning('[temperature] Control thread already running')
        return
    
    _stop_control = False
    _control_thread = threading.Thread(target=control_loop, daemon=True, name='temperatureControl')
    _control_thread.start()
    
    # Enable chiller automation in the unified system (single source of truth)
    from app.auto_control import set_controller_auto_enabled
    set_controller_auto_enabled("chiller", True)
    log.info('[temperature] Automatic control started')


def stop_auto_control():
    """Stop automated temperature control."""
    global _stop_control
    
    _stop_control = True
    
    # Disable chiller automation in the unified system (single source of truth)
    from app.auto_control import set_controller_auto_enabled
    set_controller_auto_enabled("chiller", False)
    log.info('[temperature] Automatic control stopped')


def force_temperature_state(desired_on: bool, duration_minutes: Optional[int] = None) -> Dict[str, Any]:
    """
    Manually override temperature state (emergency/maintenance).
    
    Args:
        desired_on: True to force ON, False to force OFF
        duration_minutes: Optional duration for override (None = indefinite)
    
    Returns:
        Status dict
    """
    with _control_lock:
        # Set override expiry
        if duration_minutes:
            _temperature_state['override_until'] = time.time() + (duration_minutes * 60)
        else:
            _temperature_state['override_until'] = None
        
        # Apply override
        success = set_temperature_relay(desired_on, f'Manual override (duration: {duration_minutes or "indefinite"} min)')
        
        return {
            'success': success,
            'state': 'ON' if desired_on else 'OFF',
            'override_until': _temperature_state['override_until'],
            'reason': 'Manual override'
        }


# Initialize defaults in settings if not present
def _ensure_defaults():
    """Ensure all temperature settings exist with proper defaults (aligned with brief).
    
    NOTE: temperature.auto_enabled is no longer used - automation is controlled
    via the unified auto-enable system in app/auto_control.py
    """
    defaults = {
        'temperature.target_temp': '19.0',            # °C - optimal for cannabis
        'temperature.hysteresis': '0.7',              # °C - deadband per brief
        'temperature.min_on_seconds': str(temperature_SPECS['min_on_seconds']),
        'temperature.min_off_seconds': str(temperature_SPECS['min_off_seconds']),
        'temperature.control_interval_s': '30',       # Check temp every 30s
        'temperature.max_temp_alarm': '24.0',         # Alert if water exceeds this
        'temperature.min_temp_alarm': '16.0',         # Alert if water below this
    }

    for key, default_value in defaults.items():
        if get_setting(key) is None:
            set_setting(key, default_value)

_ensure_defaults()
_ensure_events_table()

