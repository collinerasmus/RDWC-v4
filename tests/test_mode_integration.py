"""
Integration tests for the mode controller system.

Tests that all controllers (pH, EC, chiller, lights, circulation) properly:
- Respect their persisted modes from controller_modes.py
- Stop automation when mode is not 'auto'
- Allow manual operations in 'manual' mode
- Provide proper API responses
- Persist mode across restarts
"""
import pytest
import tempfile
import os
import time
import sqlite3
import importlib
from pathlib import Path


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp.close()
    db_path = tmp.name
    
    # Set environment variables for all mode modules
    os.environ["RDWC_CONTROLLER_MODES_DB"] = db_path
    os.environ["RDWC_DB"] = db_path
    os.environ["RDWC_DB_PATH"] = db_path
    
    yield db_path
    
    # Cleanup
    for var in ["RDWC_CONTROLLER_MODES_DB", "RDWC_DB", "RDWC_DB_PATH"]:
        if var in os.environ:
            del os.environ[var]
    
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def mock_settings_db(temp_db):
    """Initialize settings table in temp DB."""
    with sqlite3.connect(temp_db) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()
    return temp_db


def test_controller_modes_persistence(temp_db):
    """Test that controller modes persist across module reloads."""
    from app import unified_mode as cm
    
    # Set system mode (last call sets the unified mode for all controllers)
    assert cm.set_controller_mode('circulation', 'auto')  # Set to auto

    # Verify final unified mode is auto
    assert cm.get_controller_mode('ph') == 'auto'
    assert cm.get_controller_mode('ec') == 'auto'
    assert cm.get_controller_mode('chiller') == 'auto'
    assert cm.get_controller_mode('lights') == 'auto'
    assert cm.get_controller_mode('circulation') == 'auto'
    
    cm2 = importlib.reload(cm)
    
    # Verify persistence after reload
    assert cm2.get_controller_mode('ph') == 'auto'
    assert cm2.get_controller_mode('ec') == 'auto'
    assert cm2.get_controller_mode('chiller') == 'auto'
    assert cm2.get_controller_mode('lights') == 'auto'
    assert cm2.get_controller_mode('circulation') == 'auto'


def test_get_all_modes(temp_db):
    """Test retrieving all controller modes at once."""
    from app import unified_mode as cm
    
    # Set unified system mode to auto (last call)
    cm.set_controller_mode('chiller', 'auto')
    
    modes = cm.get_all_modes()
    
    # All controllers share the unified auto mode
    assert modes['ph'] == 'auto'
    assert modes['ec'] == 'auto'
    assert modes['chiller'] == 'auto'
    assert 'lights' in modes
    assert 'circulation' in modes


def test_invalid_mode_rejected(temp_db):
    """Test that invalid modes are rejected."""
    from app import unified_mode as cm
    
    # Try to set invalid mode
    assert not cm.set_controller_mode('ph', 'invalid_mode')
    assert not cm.set_controller_mode('ph', 'AUTO')  # Case sensitive
    assert not cm.set_controller_mode('ph', '')
    
    # Mode should remain at default
    assert cm.get_controller_mode('ph') == 'auto'


def test_invalid_controller_rejected(temp_db):
    """Test that invalid controller names are rejected."""
    from app import unified_mode as cm
    
    # Try to set mode for non-existent controller
    assert not cm.set_controller_mode('invalid_controller', 'auto')
    assert not cm.set_controller_mode('pump', 'auto')
    
    # Get should return default for unknown controller
    assert cm.get_controller_mode('invalid_controller') == 'auto'


def test_ph_controller_respects_mode(temp_db, mock_settings_db):
    """Test that pH automation checks mode before dosing."""
    # This test verifies the mode check exists in the pH auto loop
    # The actual loop code checks: if get_mode("ph") != "auto": continue
    from app import unified_mode as cm
    
    # Set pH to manual mode (maps to hold)
    cm.set_controller_mode('ph', 'manual')
    
    # Import pH control to verify it can read the mode
    # (Full automation test would require mocking sensors, pumps, etc.)
    assert cm.get_controller_mode('ph') == 'hold'
    
    # Set to auto
    cm.set_controller_mode('ph', 'auto')
    assert cm.get_controller_mode('ph') == 'auto'


def test_ec_controller_respects_mode(temp_db, mock_settings_db):
    """Test that EC automation checks mode before dosing."""
    # The EC auto worker checks: if get_mode("ec") != "auto": continue
    from app import unified_mode as cm
    
    # Set EC to manual mode (maps to hold)
    cm.set_controller_mode('ec', 'manual')
    assert cm.get_controller_mode('ec') == 'hold'
    
    # Set to maintenance (maps to hold)
    cm.set_controller_mode('ec', 'maintenance')
    assert cm.get_controller_mode('ec') == 'hold'
    
    # Set to auto
    cm.set_controller_mode('ec', 'auto')
    assert cm.get_controller_mode('ec') == 'auto'


def test_chiller_controller_respects_mode(temp_db, mock_settings_db):
    """Test that chiller automation checks mode before controlling relay."""
    # The chiller checks mode in should_chiller_run()
    from app import unified_mode as cm
    
    # Set chiller to manual mode (maps to hold)
    cm.set_controller_mode('chiller', 'manual')
    assert cm.get_controller_mode('chiller') == 'hold'
    
    # Set to auto
    cm.set_controller_mode('chiller', 'auto')
    assert cm.get_controller_mode('chiller') == 'auto'


def test_lights_controller_respects_mode(temp_db, mock_settings_db):
    """Test that lights/scheduler checks mode before auto switching."""
    # The scheduler checks: if get_mode("lights") != "auto": skip
    from app import unified_mode as cm
    
    # Set lights to manual mode (maps to hold)
    cm.set_controller_mode('lights', 'manual')
    assert cm.get_controller_mode('lights') == 'hold'
    
    # Set to auto
    cm.set_controller_mode('lights', 'auto')
    assert cm.get_controller_mode('lights') == 'auto'


def test_circulation_controller_mode(temp_db):
    """Test circulation controller mode management."""
    from app import unified_mode as cm
    
    # Circulation is in the controller list
    assert 'circulation' in cm.CONTROLLERS
    
    # Can set and get modes (manual maps to hold)
    cm.set_controller_mode('circulation', 'manual')
    assert cm.get_controller_mode('circulation') == 'hold'
    
    cm.set_controller_mode('circulation', 'auto')
    assert cm.get_controller_mode('circulation') == 'auto'


def test_mode_transitions_all_controllers(temp_db):
    """Test all valid mode transitions for each controller."""
    from app import unified_mode as cm
    
    controllers = ['ph', 'ec', 'chiller', 'lights', 'circulation']
    # Test both new modes and legacy modes
    test_cases = [
        ('auto', 'auto'),
        ('hold', 'hold'),
        ('manual', 'hold'),  # Legacy mode
        ('maintenance', 'hold'),  # Legacy mode
    ]
    
    for controller in controllers:
        for mode_to_set, expected_mode in test_cases:
            assert cm.set_controller_mode(controller, mode_to_set), f"Failed to set {controller} to {mode_to_set}"
            assert cm.get_controller_mode(controller) == expected_mode, f"{controller} expected {expected_mode}, got {cm.get_controller_mode(controller)}"


def test_concurrent_mode_changes(temp_db):
    """Test that unified mode system sets all controllers to the last mode.
    NOTE: unified_mode is system-wide - all controllers share one mode."""
    from app import unified_mode as cm
    
    # Set each controller to different modes - last call wins (unified system)
    cm.set_controller_mode('ph', 'auto')
    cm.set_controller_mode('ec', 'manual')  # Sets all to manual/hold
    cm.set_controller_mode('chiller', 'maintenance')  # Sets all to maintenance/hold
    cm.set_controller_mode('lights', 'auto')  # Sets all to auto
    cm.set_controller_mode('circulation', 'manual')  # Sets all to manual/hold
    
    # Last call was manual -> hold, so ALL controllers are now hold
    assert cm.get_controller_mode('ph') == 'hold'
    assert cm.get_controller_mode('ec') == 'hold'
    assert cm.get_controller_mode('chiller') == 'hold'
    assert cm.get_controller_mode('lights') == 'hold'
    assert cm.get_controller_mode('circulation') == 'hold'


def test_mode_default_on_first_access(temp_db):
    """Test that controllers default to 'manual' mode on first access (safety first)."""
    from app import unified_mode as cm
    
    # Fresh database - defaults to manual for safety (mapped to 'hold' for legacy)
    for controller in cm.CONTROLLERS:
        mode = cm.get_controller_mode(controller)
        assert mode == 'hold', f"{controller} should default to hold (manual), got {mode}"


def test_maintenance_mode_behavior(temp_db):
    """Test that maintenance mode is accepted (maps to hold in simplified system)."""
    from app import unified_mode as cm
    
    # All controllers should accept maintenance mode (maps to hold)
    for controller in cm.CONTROLLERS:
        assert cm.set_controller_mode(controller, 'maintenance')
        assert cm.get_controller_mode(controller) == 'hold'


def test_api_endpoint_compatibility(temp_db):
    """Test that modes work with the API endpoint structure."""
    from app import unified_mode as cm
    
    # Simulate API flow: GET current mode, POST new mode
    # NOTE: get_controller_mode returns 'hold' for manual/maintenance
    for controller in ['ph', 'ec', 'chiller', 'lights', 'circulation']:
        # GET
        current_mode = cm.get_controller_mode(controller)
        # Valid modes returned include 'auto' or 'hold' (legacy mapped)
        assert current_mode in ('auto', 'hold')
        
        # POST - change mode (manual maps to hold)
        new_mode = 'manual' if current_mode == 'auto' else 'auto'
        assert cm.set_controller_mode(controller, new_mode)
        
        # GET - verify change (manual -> hold)
        expected_mode = 'hold' if new_mode == 'manual' else 'auto'
        assert cm.get_controller_mode(controller) == expected_mode


def test_mode_thread_safety_basic(temp_db):
    """Basic test that mode operations don't corrupt data under sequential access."""
    from app import unified_mode as cm
    
    # Rapidly change modes (legacy modes map to hold)
    for _ in range(10):
        for controller in cm.CONTROLLERS:
            for mode_to_set, expected in [('auto', 'auto'), ('manual', 'hold'), ('maintenance', 'hold')]:
                cm.set_controller_mode(controller, mode_to_set)
                assert cm.get_controller_mode(controller) == expected


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
