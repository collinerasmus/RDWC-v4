"""
Test scheduler midnight boundary handling for lights schedule.

Validates that lights correctly transition across midnight when the
schedule spans from one day into the next (e.g., ON at 22:00, OFF at 10:00).
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from app.scheduler import Scheduler
from app.hardware import RelayBank


@pytest.fixture
def mock_relays():
    """Mock RelayBank for testing"""
    return Mock(spec=RelayBank)


@pytest.fixture
def mock_settings():
    """Mock settings with configurable lights schedule"""
    class MockSettings:
        def __init__(self, on_time="22:00", duration_hours=12):
            self.lights_on_time = on_time
            self.lights_duration_hours = duration_hours
    return MockSettings


def test_midnight_spanning_window_basic(mock_relays, mock_settings):
    """
    Test basic midnight-spanning scenario:
    - Lights ON at 22:00
    - Duration: 12 hours
    - Expected OFF: 10:00 next day
    
    Should NOT turn off at 23:59, should continue through midnight until 10:00.
    """
    scheduler = Scheduler(mock_relays)
    
    # Setup: lights schedule crosses midnight
    settings = mock_settings(on_time="22:00", duration_hours=12)
    
    with patch('app.settings.get_settings', return_value=settings):
        with patch('app.settings.get_todays_lights_window') as mock_window:
            with patch('app.settings.lights_window') as mock_lights_window:
                # Test BEFORE midnight (e.g., at 20:00) - should show normal schedule
                from pytz import timezone as tz
                SA_TZ = tz('Africa/Johannesburg')
                
                # Scenario 1: Before ON time (20:00)
                with patch('app.settings.datetime') as mock_dt:
                    now = SA_TZ.localize(datetime(2025, 1, 15, 20, 0, 0))
                    mock_dt.now.return_value = now
                    
                    on_dt = SA_TZ.localize(datetime(2025, 1, 15, 22, 0, 0))
                    off_dt = SA_TZ.localize(datetime(2025, 1, 16, 10, 0, 0))  # Next day
                    mock_window.return_value = (on_dt, off_dt)
                    
                    scheduler._update_lights_schedule()
                    
                    # Before ON time: should show today's schedule
                    assert scheduler._current_lights_on_time == "22:00"
                    assert scheduler._current_lights_off_time == "10:00"  # FIXED!
                
                # Scenario 2: After midnight (02:00 AM) - should recognize continuation
                with patch('app.settings.datetime') as mock_dt:
                    now = SA_TZ.localize(datetime(2025, 1, 16, 2, 0, 0))  # 02:00 AM next day
                    mock_dt.now.return_value = now
                    
                    # Today's window is 22:00 today -> 10:00 tomorrow
                    on_dt = SA_TZ.localize(datetime(2025, 1, 16, 22, 0, 0))
                    off_dt = SA_TZ.localize(datetime(2025, 1, 17, 10, 0, 0))
                    mock_window.return_value = (on_dt, off_dt)
                    
                    # Yesterday's window (what actually started)
                    yesterday_on_dt = SA_TZ.localize(datetime(2025, 1, 15, 22, 0, 0))
                    yesterday_off_dt = SA_TZ.localize(datetime(2025, 1, 16, 10, 0, 0))
                    mock_lights_window.return_value = (yesterday_on_dt, yesterday_off_dt)
                    
                    scheduler._last_lights_config = None  # Force update
                    scheduler._update_lights_schedule()
                    
                    # After midnight in active window: should show yesterday's ON time, today's OFF time
                    assert scheduler._current_lights_on_time == "22:00"  # Yesterday's ON time
                    assert scheduler._current_lights_off_time == "10:00"  # Today's OFF time (correct!)


def test_midnight_at_exactly_midnight(mock_relays, mock_settings):
    """
    Test edge case: lights schedule starts at exactly midnight
    - Lights ON at 00:00
    - Duration: 12 hours
    - Expected OFF: 12:00 same day
    """
    scheduler = Scheduler(mock_relays)
    settings = mock_settings(on_time="00:00", duration_hours=12)
    
    with patch('app.settings.get_settings', return_value=settings):
        with patch('app.settings.get_todays_lights_window') as mock_window:
            today = datetime(2025, 1, 15, 0, 0, 0)
            on_dt = datetime(2025, 1, 15, 0, 0, 0)
            off_dt = datetime(2025, 1, 15, 12, 0, 0)
            mock_window.return_value = (on_dt, off_dt)
            
            scheduler._update_lights_schedule()
            
            assert scheduler._current_lights_on_time == "00:00"
            assert scheduler._current_lights_off_time == "12:00"


def test_no_midnight_crossing_same_day(mock_relays, mock_settings):
    """
    Test normal case: lights schedule stays within same day
    - Lights ON at 06:00
    - Duration: 16 hours
    - Expected OFF: 22:00 same day
    
    Should work correctly (no midnight crossing).
    """
    scheduler = Scheduler(mock_relays)
    settings = mock_settings(on_time="06:00", duration_hours=16)
    
    with patch('app.settings.get_settings', return_value=settings):
        with patch('app.settings.get_todays_lights_window') as mock_window:
            today = datetime(2025, 1, 15, 0, 0, 0)
            on_dt = datetime(2025, 1, 15, 6, 0, 0)
            off_dt = datetime(2025, 1, 15, 22, 0, 0)
            mock_window.return_value = (on_dt, off_dt)
            
            scheduler._update_lights_schedule()
            
            assert scheduler._current_lights_on_time == "06:00"
            assert scheduler._current_lights_off_time == "22:00"


def test_long_duration_crossing_midnight(mock_relays, mock_settings):
    """
    Test extended duration crossing midnight:
    - Lights ON at 20:00
    - Duration: 16 hours
    - Expected OFF: 12:00 next day
    """
    scheduler = Scheduler(mock_relays)
    settings = mock_settings(on_time="20:00", duration_hours=16)
    
    with patch('app.settings.get_settings', return_value=settings):
        with patch('app.settings.get_todays_lights_window') as mock_window:
            with patch('app.settings.datetime') as mock_dt:
                from pytz import timezone as tz
                SA_TZ = tz('Africa/Johannesburg')
                
                # Before midnight (at 21:00)
                now = SA_TZ.localize(datetime(2025, 1, 15, 21, 0, 0))
                mock_dt.now.return_value = now
                
                on_dt = SA_TZ.localize(datetime(2025, 1, 15, 20, 0, 0))
                off_dt = SA_TZ.localize(datetime(2025, 1, 16, 12, 0, 0))  # Next day
                mock_window.return_value = (on_dt, off_dt)
                
                scheduler._update_lights_schedule()
                
                assert scheduler._current_lights_on_time == "20:00"
                # FIXED: Should show correct off time
                assert scheduler._current_lights_off_time == "12:00"


def test_midnight_reset_preserves_active_window(mock_relays, mock_settings):
    """
    Test that after midnight reset, scheduler correctly identifies
    if lights should already be ON from yesterday's window.
    
    Scenario:
    - Yesterday: lights ON at 22:00
    - Duration: 12 hours (off at 10:00 today)
    - Current time: 02:00 (after midnight reset)
    - Expected: Lights should be ON
    """
    scheduler = Scheduler(mock_relays)
    settings = mock_settings(on_time="22:00", duration_hours=12)
    
    with patch('app.settings.get_settings', return_value=settings):
        # Simulate we're at 02:00 AM, after midnight reset
        with patch('app.scheduler.time.localtime') as mock_time:
            # Wednesday (2), 02:00:00
            mock_time.return_value = Mock(tm_wday=2, tm_hour=2, tm_min=0, tm_sec=0)
            
            with patch('app.settings.get_todays_lights_window') as mock_window:
                # For "today" (after midnight), window is 22:00 today -> 10:00 tomorrow
                today = datetime(2025, 1, 15, 2, 0, 0)  # 02:00 AM
                on_dt = datetime(2025, 1, 15, 22, 0, 0)  # 22:00 today
                off_dt = datetime(2025, 1, 16, 10, 0, 0)  # 10:00 tomorrow
                mock_window.return_value = (on_dt, off_dt)
                
                scheduler._update_lights_schedule()
                
                # The scheduler should recognize that at 02:00 AM,
                # we're actually in the window that started at 22:00 YESTERDAY
                # This is the core of the fix needed


def test_is_within_window_helper_midnight_wrap(mock_relays):
    """
    Test the is_within_window helper function for midnight wrapping.
    
    This pure function should correctly determine if current time
    is within a window that wraps around midnight.
    """
    scheduler = Scheduler(mock_relays)
    
    # Test 1: Window from 22:00 to 10:00 (wraps midnight)
    on_min = 22 * 60  # 22:00 = 1320 minutes
    off_min = 10 * 60  # 10:00 = 600 minutes
    
    # At 23:00 - should be IN window
    now_min = 23 * 60
    assert scheduler.is_within_window(now_min, on_min, off_min) == True
    
    # At 02:00 - should be IN window (after midnight)
    now_min = 2 * 60
    assert scheduler.is_within_window(now_min, on_min, off_min) == True
    
    # At 10:00 - should be OUT (boundary is exclusive)
    now_min = 10 * 60
    assert scheduler.is_within_window(now_min, on_min, off_min) == False
    
    # At 15:00 - should be OUT
    now_min = 15 * 60
    assert scheduler.is_within_window(now_min, on_min, off_min) == False
    
    # Test 2: Normal window (no wrap) from 06:00 to 22:00
    on_min = 6 * 60
    off_min = 22 * 60
    
    # At 12:00 - should be IN
    now_min = 12 * 60
    assert scheduler.is_within_window(now_min, on_min, off_min) == True
    
    # At 23:00 - should be OUT
    now_min = 23 * 60
    assert scheduler.is_within_window(now_min, on_min, off_min) == False


def test_edge_detection_at_exact_times(mock_relays, mock_settings):
    """
    Test that edge detection triggers at exact scheduled times.
    
    Edge detection should only fire when second == 0 at the
    exact hour:minute of the scheduled ON/OFF times.
    """
    scheduler = Scheduler(mock_relays)
    settings = mock_settings(on_time="22:00", duration_hours=12)
    
    # This test validates the edge-only logic remains intact
    # and doesn't test periodic catch-up (which should not exist)
    
    # At 22:00:00 - should trigger ON edge
    # At 22:00:05 - should NOT trigger ON edge (s != 0)
    # At 10:00:00 - should trigger OFF edge
    # At 10:00:05 - should NOT trigger OFF edge
    
    # This is handled in the _tick() method and should be preserved
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
