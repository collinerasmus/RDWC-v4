"""
Tests for chiller circulation safety interlock.

Validates three-layer safety system:
1. Main pump prerequisite for chiller activation
2. Chiller pump auto-start when chiller turns ON
3. Pump protection while chiller running
4. Continuous validation and auto-remediation
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.chiller_control import get_chiller_state


class TestChillerInterlockValidation:
    """Test continuous interlock validation in get_chiller_state()."""
    
    def test_interlock_ok_when_all_conditions_met(self):
        """Test interlock_ok=True when chiller running with both pumps ON."""
        with patch('app.chiller_control.get_relay_status') as mock_relays, \
             patch('app.chiller_control._chiller_state', {
                 'is_running': True,
                 'auto_enabled': True,
                 'last_off_time': None,
                 'last_on_time': None
             }), \
             patch('app.chiller_control.get_setting') as mock_setting:
            
            # Mock relay status: both pumps ON
            mock_relays.return_value = {
                'main_pump': {'state': True},
                'chiller_pump': {'state': True}
            }
            mock_setting.side_effect = lambda k, d: {
                'chiller.target_temp': '19.0',
                'chiller.hysteresis': '0.5',
                'chiller.auto_enabled': '1'
            }.get(k, d)
            
            state = get_chiller_state()
            
            assert state['interlock_ok'] is True
            assert state['interlock_details']['main_pump_on'] is True
            assert state['interlock_details']['chiller_pump_on'] is True
            assert state['interlock_details']['chiller_running'] is True
            assert state['interlock_details']['violations'] is None
    
    def test_interlock_violation_chiller_running_without_main_pump(self):
        """Test violation detected when chiller running without main pump."""
        with patch('app.chiller_control.get_relay_status') as mock_relays, \
             patch('app.chiller_control._chiller_state', {
                 'is_running': True,
                 'auto_enabled': True,
                 'last_off_time': None,
                 'last_on_time': None
             }), \
             patch('app.chiller_control.get_setting') as mock_setting:
            
            # Mock relay status: main pump OFF, chiller running
            mock_relays.return_value = {
                'main_pump': {'state': False},
                'chiller_pump': {'state': True}
            }
            mock_setting.side_effect = lambda k, d: {
                'chiller.target_temp': '19.0',
                'chiller.hysteresis': '0.5',
                'chiller.auto_enabled': '1'
            }.get(k, d)
            
            state = get_chiller_state()
            
            assert state['interlock_ok'] is False
            assert 'main_pump_off_while_chiller_running' in state['interlock_details']['violations']
    
    def test_interlock_violation_chiller_running_without_chiller_pump(self):
        """Test violation detected when chiller running without chiller pump."""
        with patch('app.chiller_control.get_relay_status') as mock_relays, \
             patch('app.chiller_control._chiller_state', {
                 'is_running': True,
                 'auto_enabled': True,
                 'last_off_time': None,
                 'last_on_time': None
             }), \
             patch('app.chiller_control.get_setting') as mock_setting:
            
            # Mock relay status: chiller pump OFF, chiller running
            mock_relays.return_value = {
                'main_pump': {'state': True},
                'chiller_pump': {'state': False}
            }
            mock_setting.side_effect = lambda k, d: {
                'chiller.target_temp': '19.0',
                'chiller.hysteresis': '0.5',
                'chiller.auto_enabled': '1'
            }.get(k, d)
            
            state = get_chiller_state()
            
            assert state['interlock_ok'] is False
            assert 'chiller_pump_off_while_chiller_running' in state['interlock_details']['violations']
    
    def test_interlock_violation_auto_mode_chiller_pump_off(self):
        """Test violation when AUTO mode but chiller pump OFF despite main pump ON."""
        with patch('app.chiller_control.get_relay_status') as mock_relays, \
             patch('app.chiller_control._chiller_state', {
                 'is_running': False,
                 'auto_enabled': True,
                 'last_off_time': None,
                 'last_on_time': None
             }), \
             patch('app.chiller_control.get_setting') as mock_setting:
            
            # Mock relay status: AUTO mode, main pump ON, chiller pump OFF
            mock_relays.return_value = {
                'main_pump': {'state': True},
                'chiller_pump': {'state': False}
            }
            mock_setting.side_effect = lambda k, d: {
                'chiller.target_temp': '19.0',
                'chiller.hysteresis': '0.5',
                'chiller.auto_enabled': '1'
            }.get(k, d)
            
            state = get_chiller_state()
            
            assert state['interlock_ok'] is False
            assert 'chiller_pump_off_in_auto_mode' in state['interlock_details']['violations']
    
    def test_interlock_ok_when_chiller_off(self):
        """Test interlock_ok=True when chiller OFF (no circulation requirement)."""
        with patch('app.chiller_control.get_relay_status') as mock_relays, \
             patch('app.chiller_control._chiller_state', {
                 'is_running': False,
                 'auto_enabled': False,
                 'last_off_time': None,
                 'last_on_time': None
             }), \
             patch('app.chiller_control.get_setting') as mock_setting:
            
            # Mock relay status: all OFF
            mock_relays.return_value = {
                'main_pump': {'state': False},
                'chiller_pump': {'state': False}
            }
            mock_setting.side_effect = lambda k, d: {
                'chiller.target_temp': '19.0',
                'chiller.hysteresis': '0.5',
                'chiller.auto_enabled': '0'
            }.get(k, d)
            
            state = get_chiller_state()
            
            # When chiller is OFF, interlock should be OK
            assert state['interlock_ok'] is True
            assert state['interlock_details']['violations'] is None


class TestChillerInterlockEnforcement:
    """Test interlock enforcement in set_chiller_power() and set_chiller_pump()."""
    
    def test_chiller_blocked_without_main_pump(self):
        """Test chiller cannot turn ON without main pump."""
        from app.relays_core import set_chiller_power
        
        with patch('app.relays_core._last_state', {'main_pump': False}):
            result = set_chiller_power(True, "test")
            
            assert result['changed'] is False
            assert result['reason'] == 'interlock_main_pump_off'
            assert 'main pump must be ON first' in result['message']
    
    def test_chiller_pump_blocked_while_chiller_running(self):
        """Test chiller pump cannot turn OFF while chiller running."""
        from app.relays_core import set_chiller_pump
        
        with patch('app.relays_core._last_state', {'chiller_power': True}):
            result = set_chiller_pump(False, "test")
            
            assert result['changed'] is False
            assert result['state'] is True  # Pump stays ON
            assert result['reason'] == 'interlock_chiller_running'
            assert 'turn OFF chiller first' in result['message']
    
    def test_chiller_auto_starts_pump(self):
        """Test chiller automatically starts chiller pump when turning ON."""
        from app.relays_core import set_chiller_power
        
        with patch('app.relays_core._last_state', {'main_pump': True}), \
             patch('app.relays_core.set_relay') as mock_set_relay:
            
            # Mock successful relay operations
            mock_set_relay.return_value = {'changed': True, 'state': True}
            
            result = set_chiller_power(True, "test")
            
            # Verify chiller pump was auto-started
            assert 'chiller_pump_autostart' in result
            # set_relay should be called twice: once for chiller_power, once for chiller_pump
            assert mock_set_relay.call_count >= 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
