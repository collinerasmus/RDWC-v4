# Legacy compatibility layer for tests and UIs referring to chiller_control
# Delegates to temperature_control single-source implementation
from typing import Tuple

from app.temperature_control import (
    _temperature_state as _chiller_state,
    set_temperature_relay as _set_temperature_relay,
    set_setting as _set_setting,
    temperature_SPECS as CHILLER_SPECS,
    get_current_water_temp as _get_current_water_temp,
    get_relay_status as _get_relay_status,
    get_interlock_status as _get_interlock_status,
    get_temperature_state as _get_temperature_state,
    get_setting as _get_setting,
    should_automate_temperature as _should_automate_temperature,
)

# Expose expected names

def set_chiller_relay(on: bool, reason: str = '', force: bool = False) -> bool:
    # Legacy tests expect relay mutation with RDWC interlocks enforced and min_on/min_off timing
    import time
    now = time.time()
    if on:
        # Interlock: require main_pump and chiller_pump ON
        try:
            rel = get_relay_status() or {}
            main_pump_on = bool(rel.get('main_pump', {}).get('state', False))
            chiller_pump_on = bool(rel.get('chiller_pump', {}).get('state', False))
            if not main_pump_on or not chiller_pump_on:
                return False
        except Exception:
            # If status unavailable, be conservative and block
            return False
        # Enforce minimum OFF (cooldown)
        last_off = _chiller_state.get('last_off_time')
        try:
            from app.settings import get_setting_key as _get_key
            min_off = float(_get_key('chiller.min_off_seconds', None) or _get_key('temperature.min_off_seconds', str(CHILLER_SPECS['min_off_seconds'])))
        except Exception:
            min_off = float(CHILLER_SPECS['min_off_seconds'])
        if last_off and (now - last_off) < min_off and not force:
            _chiller_state['in_cooldown'] = True
            return False
        _chiller_state['is_running'] = True
        if not _chiller_state.get('last_on_time'):
            _chiller_state['last_on_time'] = now
        _chiller_state['in_cooldown'] = False
        _chiller_state['min_runtime_active'] = False
        return True
    else:
        # Enforce minimum ON runtime
        try:
            from app.settings import get_setting_key as _get_key
            min_on = float(_get_key('chiller.min_on_seconds', None) or _get_key('temperature.min_on_seconds', str(CHILLER_SPECS['min_on_seconds'])))
        except Exception:
            min_on = float(CHILLER_SPECS['min_on_seconds'])
        last_on = _chiller_state.get('last_on_time')
        if _chiller_state.get('is_running') and last_on and (now - last_on) < min_on and not force:
            _chiller_state['min_runtime_active'] = True
            return False
        if _chiller_state.get('is_running'):
            _chiller_state['is_running'] = False
            _chiller_state['last_off_time'] = now
            _chiller_state['min_runtime_active'] = False
            return True
        return False


def should_chiller_run() -> Tuple[bool, str]:
    """
    Legacy wrapper that uses chiller_control.get_current_water_temp for test monkeypatching
    and mirrors temperature hysteresis decision.
    """
    # Unified auto-enable
    auto_enabled = _should_automate_temperature()
    if not auto_enabled:
        return False, 'Auto control disabled'

    # Interlocks
    interlock = get_interlock_status()
    if not interlock.get('interlock_ok', True):
        violations = interlock.get('interlock_details', {}).get('violations', [])
        return False, f'Interlock violation(s): {violations}'

    # Current temperature via alias (supports test monkeypatch)
    current_temp = get_current_water_temp()
    if current_temp is None:
        return False, 'Temperature sensor unavailable'

    # Targets and hysteresis
    try:
        from app.settings import get_setting_key as _get_key
        # Legacy first for test compatibility, then canonical
        target_temp = _get_key('chiller.target_temp', None)
        if target_temp is None:
            target_temp = (_get_key('targets.temp_target_c', None) or _get_key('temperature.target_temp', '19.0'))
        target_temp = float(target_temp)
    except Exception:
        target_temp = 19.0
    try:
        from app.settings import get_setting_key as _get_key
        # Legacy first for test compatibility, then canonical
        hyst_raw = _get_key('chiller.hysteresis', None)
        if hyst_raw is None:
            hyst_raw = _get_key('temperature.hysteresis', '0.6')
        hysteresis = float(hyst_raw or '0.6')
    except Exception:
        hysteresis = 0.6

    turn_on_temp = target_temp + hysteresis
    turn_off_temp = target_temp - hysteresis

    if _chiller_state.get('is_running'):
        if current_temp <= turn_off_temp:
            return False, f'Temp {current_temp:.1f}°C below turn-off threshold {turn_off_temp:.1f}°C'
        else:
            return True, f'Maintaining cooling (temp {current_temp:.1f}°C above {turn_off_temp:.1f}°C)'
    else:
        if current_temp >= turn_on_temp:
            return True, f'Temp {current_temp:.1f}°C above turn-on threshold {turn_on_temp:.1f}°C'
        else:
            return False, f'Temp {current_temp:.1f}°C below turn-on threshold {turn_on_temp:.1f}°C'


def set_setting(key: str, value: str):
    return _set_setting(key, value)


def get_current_water_temp():
    return _get_current_water_temp()


def get_relay_status():
    return _get_relay_status()


def get_interlock_status():
    """Legacy interlock using chiller_control.get_relay_status (supports test monkeypatch)."""
    try:
        rel = get_relay_status() or {}
        main_pump_on = bool(rel.get('main_pump', {}).get('state', False))
        chiller_pump_on = bool(rel.get('chiller_pump', {}).get('state', False))
        chiller_running = bool(rel.get('chiller_power', {}).get('state', False))
        auto_enabled = _should_automate_temperature()
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
    except Exception:
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


def get_chiller_state():
    return _get_temperature_state()
