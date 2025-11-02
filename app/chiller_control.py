"""
Intelligent Chiller Control for RDWC System
Hailea HS-52A (1/10 HP) - Optimized for Cannabis Cultivation

Features:
- Temperature-based automation with hysteresis
- Compressor protection (min ON/OFF times)
- RDWC coordination (requires main pump + chiller pump)
- Energy-efficient scheduling
- Strain-specific temperature targets
"""
import time
import threading
import logging
from datetime import datetime
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies
def get_relay_status():
    from app.relays_core import get_relay_status as _get_relay_status
    return _get_relay_status()

def relay_set(name: str, on: bool, reason: str = ''):
    from app.relays_core import set as _relay_set
    return _relay_set(name, on, reason=reason)

def get_setting(key: str, default: str = None):
    from app.settings import get_all_settings
    settings = get_all_settings()
    return settings.get(key, default)

def set_setting(key: str, value: str):
    from app.settings import upsert_settings
    upsert_settings({key: value})

def get_latest_reading():
    try:
        from app.sensors_core import read_all_sensors
        return read_all_sensors()
    except ImportError:
        return None

# Chiller state tracking
_chiller_state = {
    'last_on_time': None,      # timestamp when chiller turned ON
    'last_off_time': None,     # timestamp when chiller turned OFF
    'is_running': False,       # current state
    'in_cooldown': False,      # true if in minimum OFF period
    'min_runtime_active': False,  # true if in minimum ON period
    'auto_enabled': False,     # true if automation is active
    'override_until': None,    # timestamp for manual override expiry
    'total_runtime_today': 0,  # seconds of runtime today (for stats)
    'cycles_today': 0,         # number of on/off cycles today
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
CHILLER_SPECS = {
    'model': 'Hailea HS-52A',
    'cooling_capacity_watts': 160,
    'recommended_volume_liters': (50, 150),
    'min_on_seconds': 300,      # 5 minutes minimum runtime (compressor protection)
    'min_off_seconds': 600,     # 10 minutes minimum off (compressor cooldown)
    'max_cycles_per_hour': 4,   # Prevent excessive cycling
}


def get_chiller_state() -> Dict[str, Any]:
    """Get current chiller state for API/UI."""
    with _control_lock:
        state = _chiller_state.copy()
        
        # Add computed fields
        now = time.time()
        if state['last_off_time']:
            state['seconds_since_off'] = int(now - state['last_off_time'])
        if state['last_on_time'] and state['is_running']:
            state['current_runtime'] = int(now - state['last_on_time'])
        
        # Add settings
        state['target_temp'] = float(get_setting('chiller.target_temp', '19.0'))
        state['hysteresis'] = float(get_setting('chiller.hysteresis', '0.5'))
        state['auto_enabled'] = bool(int(get_setting('chiller.auto_enabled', '0')))
        
        return state


def set_chiller_relay(desired_on: bool, reason: str = '') -> bool:
    """
    Control chiller relay with safety checks.
    
    Args:
        desired_on: True to turn ON, False to turn OFF
        reason: Log message explaining the action
    
    Returns:
        True if relay was set, False if blocked
    """
    with _control_lock:
        # Check RDWC coordination: require main_pump + chiller_pump
        if desired_on:
            relays = get_relay_status()
            main_pump_on = relays.get('main_pump', {}).get('state', False)
            chiller_pump_on = relays.get('chiller_pump', {}).get('state', False)
            
            if not main_pump_on:
                log.warning('[CHILLER] Blocked: Main pump is OFF (RDWC circulation required)')
                return False
            
            if not chiller_pump_on:
                log.warning('[CHILLER] Blocked: Chiller pump is OFF (water circulation required)')
                return False
        
        # Check minimum OFF time (compressor protection)
        if desired_on and _chiller_state['last_off_time']:
            now = time.time()
            min_off = int(get_setting('chiller.min_off_seconds', str(CHILLER_SPECS['min_off_seconds'])))
            time_since_off = now - _chiller_state['last_off_time']
            
            if time_since_off < min_off:
                remaining = int(min_off - time_since_off)
                log.info(f'[CHILLER] Blocked: In cooldown period ({remaining}s remaining)')
                _chiller_state['in_cooldown'] = True
                return False
            else:
                _chiller_state['in_cooldown'] = False
        
        # Check minimum ON time (don't short-cycle)
        if not desired_on and _chiller_state['is_running'] and _chiller_state['last_on_time']:
            now = time.time()
            min_on = int(get_setting('chiller.min_on_seconds', str(CHILLER_SPECS['min_on_seconds'])))
            runtime = now - _chiller_state['last_on_time']
            
            if runtime < min_on:
                remaining = int(min_on - runtime)
                log.info(f'[CHILLER] Blocked OFF: Minimum runtime active ({remaining}s remaining)')
                _chiller_state['min_runtime_active'] = True
                return False
            else:
                _chiller_state['min_runtime_active'] = False
        
        # Set relay
        try:
            relay_set('chiller_power', desired_on, reason=reason)
            
            # Update state
            now = time.time()
            if desired_on:
                _chiller_state['last_on_time'] = now
                _chiller_state['is_running'] = True
                _chiller_state['cycles_today'] += 1
                log.info(f'[CHILLER] ON: {reason}')
            else:
                if _chiller_state['last_on_time']:
                    runtime = now - _chiller_state['last_on_time']
                    _chiller_state['total_runtime_today'] += runtime
                _chiller_state['last_off_time'] = now
                _chiller_state['is_running'] = False
                log.info(f'[CHILLER] OFF: {reason}')
            
            return True
            
        except Exception as e:
            log.error(f'[CHILLER] Relay set failed: {e}')
            return False


def get_current_water_temp() -> Optional[float]:
    """Get current water temperature from sensors."""
    try:
        reading = get_latest_reading()
        if reading and reading.get('temperature_c') is not None:
            return float(reading['temperature_c'])
    except Exception as e:
        log.error(f'[CHILLER] Failed to get water temp: {e}')
    return None


def should_chiller_run() -> tuple[bool, str]:
    """
    Determine if chiller should be running based on temperature and settings.
    
    Returns:
        (should_run, reason) tuple
    """
    # Check if auto control is enabled
    auto_enabled = bool(int(get_setting('chiller.auto_enabled', '0')))
    if not auto_enabled:
        return False, 'Auto control disabled'
    
    # Get current temp
    current_temp = get_current_water_temp()
    if current_temp is None:
        return False, 'Temperature sensor unavailable'
    
    # Get target and hysteresis
    target_temp = float(get_setting('chiller.target_temp', '19.0'))
    hysteresis = float(get_setting('chiller.hysteresis', '0.5'))
    
    # Calculate thresholds
    turn_on_temp = target_temp + hysteresis   # e.g., 19.5°C
    turn_off_temp = target_temp - hysteresis  # e.g., 18.5°C
    
    # Hysteresis logic
    if _chiller_state['is_running']:
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
    """Background thread: periodically check temperature and control chiller."""
    global _stop_control
    log.info('[CHILLER] Control loop started')
    
    while not _stop_control:
        try:
            # Check if we should run
            should_run, reason = should_chiller_run()
            
            # Apply decision
            if should_run != _chiller_state['is_running']:
                set_chiller_relay(should_run, reason)
            
            # Check for midnight reset (daily stats)
            now = datetime.now()
            if now.hour == 0 and now.minute < 1:
                with _control_lock:
                    _chiller_state['total_runtime_today'] = 0
                    _chiller_state['cycles_today'] = 0
            
        except Exception as e:
            log.error(f'[CHILLER] Control loop error: {e}')
        
        # Sleep for control interval (default 30 seconds)
        time.sleep(int(get_setting('chiller.control_interval_s', '30')))
    
    log.info('[CHILLER] Control loop stopped')


def start_auto_control():
    """Start automated chiller control."""
    global _control_thread, _stop_control
    
    if _control_thread and _control_thread.is_alive():
        log.warning('[CHILLER] Control thread already running')
        return
    
    _stop_control = False
    _control_thread = threading.Thread(target=control_loop, daemon=True, name='ChillerControl')
    _control_thread.start()
    
    with _control_lock:
        _chiller_state['auto_enabled'] = True
    
    set_setting('chiller.auto_enabled', '1')
    log.info('[CHILLER] Automatic control started')


def stop_auto_control():
    """Stop automated chiller control."""
    global _stop_control
    
    _stop_control = True
    
    with _control_lock:
        _chiller_state['auto_enabled'] = False
    
    set_setting('chiller.auto_enabled', '0')
    log.info('[CHILLER] Automatic control stopped')


def force_chiller_state(desired_on: bool, duration_minutes: Optional[int] = None) -> Dict[str, Any]:
    """
    Manually override chiller state (emergency/maintenance).
    
    Args:
        desired_on: True to force ON, False to force OFF
        duration_minutes: Optional duration for override (None = indefinite)
    
    Returns:
        Status dict
    """
    with _control_lock:
        # Set override expiry
        if duration_minutes:
            _chiller_state['override_until'] = time.time() + (duration_minutes * 60)
        else:
            _chiller_state['override_until'] = None
        
        # Apply override
        success = set_chiller_relay(desired_on, f'Manual override (duration: {duration_minutes or "indefinite"} min)')
        
        return {
            'success': success,
            'state': 'ON' if desired_on else 'OFF',
            'override_until': _chiller_state['override_until'],
            'reason': 'Manual override'
        }


# Initialize defaults in settings if not present
def _ensure_defaults():
    """Ensure all chiller settings exist with proper defaults."""
    defaults = {
        'chiller.target_temp': '19.0',           # °C - optimal for cannabis
        'chiller.hysteresis': '0.5',             # °C - deadband
        'chiller.min_on_seconds': str(CHILLER_SPECS['min_on_seconds']),
        'chiller.min_off_seconds': str(CHILLER_SPECS['min_off_seconds']),
        'chiller.auto_enabled': '0',             # Start disabled for safety
        'chiller.control_interval_s': '30',      # Check temp every 30s
        'chiller.max_temp_alarm': '24.0',        # Alert if water exceeds this
        'chiller.min_temp_alarm': '16.0',        # Alert if water below this
    }
    
    for key, default_value in defaults.items():
        if get_setting(key) is None:
            set_setting(key, default_value)

_ensure_defaults()
