"""
Basic tests for relay_guard module focusing on state queries and anomaly tracking.
Tests non-GPIO logic: shadow state, anomaly counters, event ring buffer.
"""


def test_get_shadow_state_empty_initially():
    """Shadow state should be empty dict before initialization."""
    # Re-import to get fresh state
    import app.relay_guard as rg
    # Guard may be initialized by conftest, check if empty or populated
    state = rg.get_shadow_state()
    assert isinstance(state, dict)
    # If already initialized, should have relay entries
    if rg._initialized:
        assert len(state) > 0
    else:
        assert len(state) == 0


def test_get_shadow_state_returns_copy():
    """get_shadow_state should return a copy, not the internal dict."""
    import app.relay_guard as rg
    state1 = rg.get_shadow_state()
    state2 = rg.get_shadow_state()
    assert state1 is not state2  # Different objects
    assert state1 == state2  # Same content


def test_get_anomalies_structure():
    """get_anomalies should return dict with count and anomalies list."""
    import app.relay_guard as rg
    result = rg.get_anomalies()
    assert isinstance(result, dict)
    assert "count" in result
    assert "anomalies" in result
    assert isinstance(result["count"], int)
    assert isinstance(result["anomalies"], list)


def test_get_recent_guard_events_structure():
    """get_recent_guard_events should return dict with events list."""
    import app.relay_guard as rg
    result = rg.get_recent_guard_events()
    assert isinstance(result, dict)
    assert "events" in result
    assert isinstance(result["events"], list)


def test_get_recent_guard_events_limit():
    """get_recent_guard_events should respect limit parameter."""
    import app.relay_guard as rg
    # Request small limit
    result = rg.get_recent_guard_events(limit=5)
    assert len(result["events"]) <= 5


def test_get_recent_guard_events_clamps_limit():
    """get_recent_guard_events should clamp limit to RECENT_MAX."""
    import app.relay_guard as rg
    # Request excessive limit
    result = rg.get_recent_guard_events(limit=1000)
    assert len(result["events"]) <= rg._RECENT_MAX


def test_level_str_low():
    """level_str should convert GPIO.LOW to 'LOW'."""
    import app.relay_guard as rg
    from app.relay_guard import GPIO
    assert rg.level_str(GPIO.LOW) == 'LOW'


def test_level_str_high():
    """level_str should convert GPIO.HIGH to 'HIGH'."""
    import app.relay_guard as rg
    from app.relay_guard import GPIO
    assert rg.level_str(GPIO.HIGH) == 'HIGH'


def test_get_pin_levels_returns_dict():
    """get_pin_levels should return dict mapping relay names to level strings."""
    import app.relay_guard as rg
    levels = rg.get_pin_levels()
    assert isinstance(levels, dict)
    # If initialized, should have entries for known relays
    if rg._initialized:
        assert len(levels) > 0
        # Check that values are strings (LOW/HIGH/ERROR:...)
        for name, level in levels.items():
            assert isinstance(level, str)


def test_append_recent_maintains_buffer():
    """Internal _append_recent should maintain ring buffer at RECENT_MAX."""
    import app.relay_guard as rg
    
    # Record initial count
    initial_count = len(rg._recent_events)
    
    # Add one event
    rg._append_recent({"test": "event", "ts": "2025-01-01T00:00:00Z"})
    
    # Should have added exactly one (or stayed at max)
    new_count = len(rg._recent_events)
    assert new_count <= rg._RECENT_MAX
    if initial_count < rg._RECENT_MAX:
        assert new_count == initial_count + 1
    else:
        assert new_count == rg._RECENT_MAX


def test_relay_pins_defined():
    """RELAY_PINS should contain expected relay names."""
    import app.relay_guard as rg
    
    assert isinstance(rg.RELAY_PINS, dict)
    # Check for known relays
    expected_relays = ['dosing_grow', 'dosing_micro', 'dosing_bloom', 'dosing_ph_up', 
                       'main_pump', 'chiller_pump', 'chiller_power', 'lights']
    for relay in expected_relays:
        assert relay in rg.RELAY_PINS, f"Expected relay '{relay}' not in RELAY_PINS"
        assert isinstance(rg.RELAY_PINS[relay], int), f"Pin for '{relay}' should be int"
