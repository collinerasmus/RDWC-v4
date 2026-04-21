"""Test scheduler midnight boundary handling and edge-only behavior."""
import types
from unittest.mock import patch
from app.scheduler import Scheduler
from app.hardware import RelayBank


def test_is_within_window_cross_midnight():
    """Test window detection spanning midnight."""
    rb = RelayBank()
    s = Scheduler(rb)
    # 18:00 -> 06:00 spans midnight
    on_min = 18*60
    off_min = 6*60
    # Before window same day
    assert s.is_within_window(17*60, on_min, off_min) is False
    # Inside before midnight
    assert s.is_within_window(23*60, on_min, off_min) is True
    # Inside after midnight
    assert s.is_within_window(0*60 + 30, on_min, off_min) is True
    # After off edge in morning
    assert s.is_within_window(7*60, on_min, off_min) is False


def test_is_within_window_same_day():
    """Test window detection within same day (no midnight crossing)."""
    rb = RelayBank()
    s = Scheduler(rb)
    # 06:00 -> 22:00 (same day window)
    on_min = 6*60
    off_min = 22*60
    
    # Before ON edge
    assert s.is_within_window(5*60 + 59, on_min, off_min) is False
    # At ON edge (boundary)
    assert s.is_within_window(6*60, on_min, off_min) is True
    # Inside window
    assert s.is_within_window(12*60, on_min, off_min) is True
    # Just before OFF edge
    assert s.is_within_window(21*60 + 59, on_min, off_min) is True
    # At OFF edge (excluded)
    assert s.is_within_window(22*60, on_min, off_min) is False
    # After OFF edge
    assert s.is_within_window(23*60, on_min, off_min) is False


def test_midnight_boundary_exact():
    """Test exact midnight moment (00:00:00)."""
    rb = RelayBank()
    s = Scheduler(rb)
    # Window spanning midnight: 20:00 -> 04:00
    on_min = 20*60
    off_min = 4*60
    
    # At midnight exactly
    assert s.is_within_window(0, on_min, off_min) is True
    # One minute after midnight
    assert s.is_within_window(1, on_min, off_min) is True
    # One minute before midnight (23:59)
    assert s.is_within_window(23*60 + 59, on_min, off_min) is True


def test_lights_edge_only_no_catchup():
    """Test that lights only trigger at exact edges, not during catchup."""
    rb = RelayBank()
    s = Scheduler(rb)
    
    # Mock the lights settings
    s._current_lights_on_time = "18:00"
    s._current_lights_off_time = "06:00"
    
    # Track edge triggers
    edge_calls = []
    
    def mock_set_lights(state, reason):
        edge_calls.append({'state': state, 'reason': reason})
        return {'changed': True}
    
    # Simulate multiple ticks at the same time (should only trigger once at s=0)
    with patch('app.scheduler.load_cfg', return_value={'enabled': True, 'entries': [], 'daily_caps': {}}):
        with patch.object(s, '_update_lights_schedule'):
            with patch('app.controller_modes.get_mode', return_value='auto'):
                with patch('app.relays_core.set_lights', side_effect=mock_set_lights):
                    with patch('app.scheduler._now_tuple') as mock_time:
                        # Simulate ON edge at 18:00:00
                        mock_time.return_value = (0, 18, 0, 0)  # Mon, 18:00:00
                        s._tick()

                        # Only 1 edge call should happen at s=0
                        assert len([c for c in edge_calls if 'schedule_on' in c['reason']]) == 1

                        edge_calls.clear()

                        # Simulate guards (s=1..5) - should call set_lights but with guard reason
                        for sec in range(1, 6):
                            mock_time.return_value = (0, 18, 0, sec)
                            s._tick()

                        # Guards should have been called 5 times
                        guard_calls = [c for c in edge_calls if 'guard' in c['reason']]
                        assert len(guard_calls) == 5

                        edge_calls.clear()

                        # Simulate time outside guard window (s > 5)
                        mock_time.return_value = (0, 18, 0, 10)
                        s._tick()

                        # No calls should happen outside edge and guard windows
                        assert len(edge_calls) == 0


def test_midnight_transition_no_phantom_edges():
    """Test that crossing midnight doesn't create phantom edges."""
    rb = RelayBank()
    s = Scheduler(rb)
    
    # Lights: 20:00 ON -> 04:00 OFF (spans midnight)
    s._current_lights_on_time = "20:00"
    s._current_lights_off_time = "04:00"
    
    edge_calls = []
    
    def mock_set_lights(state, reason):
        edge_calls.append({'state': state, 'reason': reason})
        return {'changed': True}
    
    with patch('app.scheduler.load_cfg', return_value={'enabled': True, 'entries': [], 'daily_caps': {}}):
        with patch.object(s, '_update_lights_schedule'):
            with patch('app.controller_modes.get_mode', return_value='auto'):
                with patch('app.relays_core.set_lights', side_effect=mock_set_lights):
                    with patch('app.scheduler._now_tuple') as mock_time:
                        # Just before midnight
                        mock_time.return_value = (0, 23, 59, 0)
                        s._tick()

                        # At midnight exactly (no edge expected here)
                        mock_time.return_value = (1, 0, 0, 0)  # Next day
                        s._tick()

                        # One minute after midnight
                        mock_time.return_value = (1, 0, 1, 0)
                        s._tick()

                        # Should have NO edge calls at midnight transition
                        assert len(edge_calls) == 0


def test_exactly_two_edges_per_day():
    """Test that lights produce exactly two edges per day (ON and OFF)."""
    rb = RelayBank()
    s = Scheduler(rb)
    
    # Standard schedule: 06:00 ON -> 22:00 OFF
    s._current_lights_on_time = "06:00"
    s._current_lights_off_time = "22:00"
    
    edge_calls = []
    
    def mock_set_lights(state, reason):
        edge_calls.append({'state': state, 'reason': reason})
        return {'changed': True}
    
    with patch('app.scheduler.load_cfg', return_value={'enabled': True, 'entries': [], 'daily_caps': {}}):
        with patch.object(s, '_update_lights_schedule'):
            with patch('app.controller_modes.get_mode', return_value='auto'):
                with patch('app.relays_core.set_lights', side_effect=mock_set_lights):
                    with patch('app.scheduler._now_tuple') as mock_time:
                        # Simulate a full day, checking every minute at s=0 only
                        for hour in range(24):
                            for minute in range(60):
                                mock_time.return_value = (0, hour, minute, 0)
                                s._tick()

                        # Count actual edge triggers (not guards)
                        on_edges = [c for c in edge_calls if 'schedule_on' in c['reason'] and 'guard' not in c['reason']]
                        off_edges = [c for c in edge_calls if 'schedule_off' in c['reason'] and 'guard' not in c['reason']]

                        # Should have exactly 1 ON edge and 1 OFF edge
                        assert len(on_edges) == 1, f"Expected 1 ON edge, got {len(on_edges)}"
                        assert len(off_edges) == 1, f"Expected 1 OFF edge, got {len(off_edges)}"


def test_midnight_spanning_schedule_two_edges():
    """Test midnight-spanning schedule produces exactly two edges per day."""
    rb = RelayBank()
    s = Scheduler(rb)
    
    # Midnight-spanning schedule: 20:00 ON -> 04:00 OFF
    s._current_lights_on_time = "20:00"
    s._current_lights_off_time = "04:00"
    
    edge_calls = []
    hour_seen = []
    
    def mock_set_lights(state, reason):
        h, m = mock_time.return_value[1], mock_time.return_value[2]
        edge_calls.append({'state': state, 'reason': reason, 'hour': h, 'minute': m})
        hour_seen.append(h)
        return {'changed': True}
    
    with patch('app.scheduler.load_cfg', return_value={'enabled': True, 'entries': [], 'daily_caps': {}}):
        with patch.object(s, '_update_lights_schedule'):
            with patch('app.controller_modes.get_mode', return_value='auto'):
                with patch('app.relays_core.set_lights', side_effect=mock_set_lights):
                    with patch('app.scheduler._now_tuple') as mock_time:
                        # Simulate a full 24-hour period at s=0 only
                        for hour in range(24):
                            for minute in range(60):
                                mock_time.return_value = (0, hour, minute, 0)
                                s._tick()

                        # Count edge triggers (excluding guards)
                        on_edges = [c for c in edge_calls if 'schedule_on' in c['reason'] and 'guard' not in c['reason']]
                        off_edges = [c for c in edge_calls if 'schedule_off' in c['reason'] and 'guard' not in c['reason']]

                        # Should have exactly 1 ON edge at 20:00 and 1 OFF edge at 04:00
                        assert len(on_edges) == 1, f"Expected 1 ON edge, got {len(on_edges)}"
                        assert len(off_edges) == 1, f"Expected 1 OFF edge, got {len(off_edges)}"

                        # Verify timing
                        assert on_edges[0]['hour'] == 20 and on_edges[0]['minute'] == 0
                        assert off_edges[0]['hour'] == 4 and off_edges[0]['minute'] == 0


def test_lights_edge_tolerates_jitter_within_guard_window():
    rb = RelayBank()
    s = Scheduler(rb)
    s._current_lights_on_time = "18:00"
    s._current_lights_off_time = "06:00"

    calls = []

    def mock_set_lights(state, reason):
        calls.append({"state": state, "reason": reason})
        return {"changed": True}

    with patch('app.scheduler.load_cfg', return_value={'enabled': True, 'entries': [], 'daily_caps': {}}):
        with patch.object(s, '_update_lights_schedule'):
            with patch('app.scheduler.log_event'):
                with patch('app.auto_control.should_automate', return_value=True):
                    with patch('app.relays_core.set_lights', side_effect=mock_set_lights):
                        with patch('app.relay_guard.sync_from_actual'):
                            with patch('app.scheduler._now_tuple', return_value=(0, 18, 0, 2)):
                                s._tick()

    edge_calls = [c for c in calls if c['reason'] == 'schedule_on']
    guard_calls = [c for c in calls if c['reason'] == 'schedule_guard_on']
    assert len(edge_calls) == 1
    assert len(guard_calls) == 1


def test_tick_refreshes_lights_schedule_when_settings_change():
    rb = RelayBank()
    s = Scheduler(rb)

    settings_seq = [
        types.SimpleNamespace(lights_on_time='06:00', lights_duration_hours=16),
        types.SimpleNamespace(lights_on_time='08:00', lights_duration_hours=12),
    ]
    window_seq = [
        ('06:00', '22:00'),
        ('08:00', '20:00'),
    ]

    def fake_get_settings():
        if settings_seq:
            return settings_seq.pop(0)
        return types.SimpleNamespace(lights_on_time='08:00', lights_duration_hours=12)

    def fake_get_window():
        on_s, off_s = window_seq.pop(0)

        class FakeDt:
            def __init__(self, hm):
                self.hm = hm
            def strftime(self, fmt):
                return self.hm
            def isoformat(self):
                return self.hm

        return FakeDt(on_s), FakeDt(off_s)

    with patch('app.scheduler.load_cfg', return_value={'enabled': True, 'entries': [], 'daily_caps': {}}):
        with patch('app.scheduler.log_event'):
            with patch('app.auto_control.should_automate', return_value=False):
                with patch('app.settings.get_settings', side_effect=fake_get_settings):
                    with patch('app.settings.get_todays_lights_window', side_effect=fake_get_window):
                        with patch('app.scheduler._now_tuple', return_value=(0, 12, 0, 0)):
                            s._update_lights_schedule()
                            assert s._current_lights_on_time == '06:00'
                            assert s._current_lights_off_time == '22:00'

                            s._tick()
                            assert s._current_lights_on_time == '08:00'
                            assert s._current_lights_off_time == '20:00'
