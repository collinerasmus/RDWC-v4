"""Test chiller interlock status API and enforcement."""
from app.chiller_control import get_interlock_status, get_chiller_state, set_chiller_relay, _chiller_state
from app.controller_modes import set_mode
from app.settings import upsert_settings


def _mock_relay_status(main_pump=False, chiller_pump=False, chiller_power=False):
    """Mock relay status for testing."""
    def _inner():
        return {
            'main_pump': {'state': main_pump},
            'chiller_pump': {'state': chiller_pump},
            'chiller_power': {'state': chiller_power}
        }
    return _inner


def _reset_chiller_state():
    """Reset chiller internal state."""
    _chiller_state['last_on_time'] = None
    _chiller_state['last_off_time'] = None
    _chiller_state['is_running'] = False
    _chiller_state['in_cooldown'] = False
    _chiller_state['min_runtime_active'] = False


def test_interlock_status_all_ok():
    """Test interlock status when all conditions are met."""
    from app import chiller_control as cc
    
    # Set up: all pumps and chiller running
    cc.get_relay_status = _mock_relay_status(main_pump=True, chiller_pump=True, chiller_power=True)
    upsert_settings({'chiller.auto_enabled': '1'})
    set_mode('chiller', 'auto')
    
    status = get_interlock_status()
    
    assert status['interlock_ok'] is True
    assert status['interlock_details']['main_pump_on'] is True
    assert status['interlock_details']['chiller_pump_on'] is True
    assert status['interlock_details']['chiller_running'] is True
    assert status['interlock_details']['auto_enabled'] is True
    assert status['interlock_details']['violations'] is None


def test_interlock_status_main_pump_violation():
    """Test interlock status when main pump is off but chiller running."""
    from app import chiller_control as cc
    
    # Chiller running without main pump
    cc.get_relay_status = _mock_relay_status(main_pump=False, chiller_pump=True, chiller_power=True)
    
    status = get_interlock_status()
    
    assert status['interlock_ok'] is False
    assert 'main_pump_off' in status['interlock_details']['violations']


def test_interlock_status_chiller_pump_violation():
    """Test interlock status when chiller pump is off but chiller running."""
    from app import chiller_control as cc
    
    # Chiller running without chiller pump
    cc.get_relay_status = _mock_relay_status(main_pump=True, chiller_pump=False, chiller_power=True)
    
    status = get_interlock_status()
    
    assert status['interlock_ok'] is False
    assert 'chiller_pump_off' in status['interlock_details']['violations']


def test_interlock_status_both_pumps_violation():
    """Test interlock status when both pumps are off but chiller running."""
    from app import chiller_control as cc
    
    # Chiller running without any pumps
    cc.get_relay_status = _mock_relay_status(main_pump=False, chiller_pump=False, chiller_power=True)
    
    status = get_interlock_status()
    
    assert status['interlock_ok'] is False
    assert 'main_pump_off' in status['interlock_details']['violations']
    assert 'chiller_pump_off' in status['interlock_details']['violations']


def test_interlock_status_chiller_off_ok():
    """Test interlock status when chiller is off (no violations expected)."""
    from app import chiller_control as cc
    
    # Chiller off, pumps state doesn't matter for interlock
    cc.get_relay_status = _mock_relay_status(main_pump=False, chiller_pump=False, chiller_power=False)
    
    status = get_interlock_status()
    
    # No violations when chiller is off
    assert status['interlock_ok'] is True
    assert status['interlock_details']['violations'] is None


def test_chiller_state_includes_interlock():
    """Test that get_chiller_state includes interlock status."""
    from app import chiller_control as cc
    
    _reset_chiller_state()
    cc.get_relay_status = _mock_relay_status(main_pump=True, chiller_pump=True, chiller_power=False)
    upsert_settings({'chiller.auto_enabled': '1'})
    set_mode('chiller', 'auto')
    
    state = get_chiller_state()
    
    # Check interlock fields are present
    assert 'interlock_ok' in state
    assert 'interlock_details' in state
    assert isinstance(state['interlock_details'], dict)
    assert 'main_pump_on' in state['interlock_details']
    assert 'chiller_pump_on' in state['interlock_details']
    assert 'chiller_running' in state['interlock_details']
    assert 'auto_enabled' in state['interlock_details']
    assert 'violations' in state['interlock_details']


def test_set_chiller_relay_enforces_main_pump():
    """Test that set_chiller_relay blocks when main pump is off."""
    from app import chiller_control as cc
    
    _reset_chiller_state()
    # Main pump OFF, chiller pump ON
    cc.get_relay_status = _mock_relay_status(main_pump=False, chiller_pump=True, chiller_power=False)
    
    # Attempt to turn chiller ON should be blocked
    result = set_chiller_relay(True, 'test turn on')
    
    assert result is False
    assert _chiller_state['is_running'] is False


def test_set_chiller_relay_enforces_chiller_pump():
    """Test that set_chiller_relay blocks when chiller pump is off."""
    from app import chiller_control as cc
    
    _reset_chiller_state()
    # Main pump ON, chiller pump OFF
    cc.get_relay_status = _mock_relay_status(main_pump=True, chiller_pump=False, chiller_power=False)
    
    # Attempt to turn chiller ON should be blocked
    result = set_chiller_relay(True, 'test turn on')
    
    assert result is False
    assert _chiller_state['is_running'] is False


def test_set_chiller_relay_allows_with_both_pumps():
    """Test that set_chiller_relay allows when both pumps are on."""
    from app import chiller_control as cc
    
    _reset_chiller_state()
    # Both pumps ON
    cc.get_relay_status = _mock_relay_status(main_pump=True, chiller_pump=True, chiller_power=False)
    
    # Attempt to turn chiller ON should succeed
    result = set_chiller_relay(True, 'test turn on')
    
    assert result is True
    assert _chiller_state['is_running'] is True
