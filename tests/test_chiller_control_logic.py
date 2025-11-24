import time
from app.chiller_control import (
    _chiller_state, set_chiller_relay, should_chiller_run,
    set_setting, CHILLER_SPECS
)
from app.unified_mode import set_controller_mode

# NOTE: Direct access to _chiller_state is intentional for unit logic tests.


def _reset_state():
    _chiller_state['last_on_time'] = None
    _chiller_state['last_off_time'] = None
    _chiller_state['is_running'] = False
    _chiller_state['in_cooldown'] = False
    _chiller_state['min_runtime_active'] = False


def test_hysteresis_thresholds():
    _reset_state()
    set_setting('chiller.target_temp', '19.0')
    set_setting('chiller.hysteresis', '0.7')
    set_setting('chiller.auto_enabled', '1')
    set_controller_mode('chiller', '')

    # Simulate temperature via monkeypatch by temporarily overriding get_current_water_temp
    from app import chiller_control as cc

    def fake_temp(val):
        def _inner():
            return val
        return _inner

    # OFF state: below turn-on (target + hysteresis = 19.7)
    cc.get_current_water_temp = fake_temp(19.6)
    should_run, reason = should_chiller_run()
    assert should_run is False, reason

    # OFF state: at or above threshold 19.7 triggers run
    cc.get_current_water_temp = fake_temp(19.8)
    should_run, reason = should_chiller_run()
    assert should_run is True, reason

    # Turn ON (should succeed - not in cooldown)
    # Mock relay status to satisfy pump prerequisites
    cc.get_relay_status = lambda: {
        'main_pump': {'state': True},
        'chiller_pump': {'state': True}
    }
    assert set_chiller_relay(True, 'unit-test turn on') is True
    assert _chiller_state['is_running'] is True

    # ON state: above turn-off threshold (target - hysteresis = 18.3) so stays running
    cc.get_current_water_temp = fake_temp(19.0)
    should_run, reason = should_chiller_run()
    assert should_run is True, reason

    # ON state: below turn-off threshold -> desire OFF
    cc.get_current_water_temp = fake_temp(18.2)
    should_run, reason = should_chiller_run()
    assert should_run is False, reason


def test_min_on_enforcement():
    _reset_state()
    set_setting('chiller.target_temp', '19.0')
    set_setting('chiller.hysteresis', '0.7')
    set_setting('chiller.min_on_seconds', str(CHILLER_SPECS['min_on_seconds']))
    set_setting('chiller.auto_enabled', '1')
    set_controller_mode('chiller', '')

    from app import chiller_control as cc

    cc.get_current_water_temp = lambda: 21.0  # Force ON condition
    should_run, _ = should_chiller_run()
    assert should_run is True
    cc.get_relay_status = lambda: {
        'main_pump': {'state': True},
        'chiller_pump': {'state': True}
    }
    assert set_chiller_relay(True, 'unit-test on for min_on test') is True
    assert _chiller_state['is_running'] is True

    # Immediately try to turn OFF before min_on_seconds elapsed -> blocked
    cc.get_current_water_temp = lambda: 17.0  # Force OFF condition
    should_run, _ = should_chiller_run()
    assert should_run is False
    off_attempt = set_chiller_relay(False, 'attempt early off')
    assert off_attempt is False  # blocked by min runtime
    assert _chiller_state['is_running'] is True

    # Simulate runtime exceeding min_on_seconds
    _chiller_state['last_on_time'] -= (CHILLER_SPECS['min_on_seconds'] + 1)
    off_attempt2 = set_chiller_relay(False, 'off after min runtime')
    assert off_attempt2 is True
    assert _chiller_state['is_running'] is False


def test_min_off_enforcement():
    _reset_state()
    set_setting('chiller.target_temp', '19.0')
    set_setting('chiller.hysteresis', '0.7')
    set_setting('chiller.min_off_seconds', str(CHILLER_SPECS['min_off_seconds']))
    set_setting('chiller.auto_enabled', '1')
    set_controller_mode('chiller', '')

    from app import chiller_control as cc

    # Start ON then turn OFF cleanly to begin cooldown
    cc.get_current_water_temp = lambda: 21.0
    cc.get_relay_status = lambda: {
        'main_pump': {'state': True},
        'chiller_pump': {'state': True}
    }
    assert set_chiller_relay(True, 'start for min_off test') is True
    _chiller_state['last_on_time'] -= (CHILLER_SPECS['min_on_seconds'] + 5)  # ensure we can turn off
    cc.get_current_water_temp = lambda: 18.0
    assert set_chiller_relay(False, 'init off') is True

    # Attempt early ON inside cooldown window -> blocked
    _chiller_state['last_off_time'] = time.time() - (CHILLER_SPECS['min_off_seconds'] - 10)
    cc.get_current_water_temp = lambda: 22.0  # Force ON condition
    should_run, _ = should_chiller_run()
    assert should_run is True  # desire ON
    on_attempt = set_chiller_relay(True, 'attempt early on during cooldown')
    assert on_attempt is False
    assert _chiller_state['is_running'] is False

    # Move past cooldown -> allow ON
    _chiller_state['last_off_time'] -= (CHILLER_SPECS['min_off_seconds'] + 5)
    on_attempt2 = set_chiller_relay(True, 'on after cooldown')
    assert on_attempt2 is True
    assert _chiller_state['is_running'] is True
