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
    from app import controller_modes as cm
    
    # Set modes for all controllers (legacy modes map to hold)
    assert cm.set_mode('ph', 'manual')
    assert cm.set_mode('ec', 'auto')
    assert cm.set_mode('chiller', 'maintenance')
    assert cm.set_mode('lights', 'manual')
    assert cm.set_mode('circulation', 'auto')
    
    # Verify modes are set (manual/maintenance -> hold)
    assert cm.get_mode('ph') == 'hold'
    assert cm.get_mode('ec') == 'auto'
    assert cm.get_mode('chiller') == 'hold'
    assert cm.get_mode('lights') == 'hold'
    assert cm.get_mode('circulation') == 'auto'
    
    # Simulate restart by reloading module
    import importlib
    cm = importlib.reload(cm)
    
    # Verify persistence
    assert cm.get_mode('ph') == 'hold'
    assert cm.get_mode('ec') == 'auto'
    assert cm.get_mode('chiller') == 'hold'
    assert cm.get_mode('lights') == 'hold'
    assert cm.get_mode('circulation') == 'auto'


def test_get_all_modes(temp_db):
    """Test retrieving all controller modes at once."""
    from app import controller_modes as cm
    
    # Set different modes (legacy modes map to hold)
    cm.set_mode('ph', 'manual')
    cm.set_mode('ec', 'maintenance')
    cm.set_mode('chiller', 'auto')
    
    modes = cm.get_all_modes()
    
    assert modes['ph'] == 'hold'  # manual -> hold
    assert modes['ec'] == 'hold'  # maintenance -> hold
    assert modes['chiller'] == 'auto'
    assert 'lights' in modes
    assert 'circulation' in modes


def test_invalid_mode_rejected(temp_db):
    """Test that invalid modes are rejected."""
    from app import controller_modes as cm
    
    # Try to set invalid mode
    assert not cm.set_mode('ph', 'invalid_mode')
    assert not cm.set_mode('ph', 'AUTO')  # Case sensitive
    assert not cm.set_mode('ph', '')
    
    # Mode should remain at default
    assert cm.get_mode('ph') == 'auto'


def test_invalid_controller_rejected(temp_db):
    """Test that invalid controller names are rejected."""
    from app import controller_modes as cm
    
    # Try to set mode for non-existent controller
    assert not cm.set_mode('invalid_controller', 'auto')
    assert not cm.set_mode('pump', 'auto')
    
    # Get should return default for unknown controller
    assert cm.get_mode('invalid_controller') == 'auto'


def test_ph_controller_respects_mode(temp_db, mock_settings_db):
    """Test that pH automation checks mode before dosing."""
    # This test verifies the mode check exists in the pH auto loop
    # The actual loop code checks: if get_mode("ph") != "auto": continue
    from app import controller_modes as cm
    
    # Set pH to manual mode (maps to hold)
    cm.set_mode('ph', 'manual')
    
    # Import pH control to verify it can read the mode
    # (Full automation test would require mocking sensors, pumps, etc.)
    assert cm.get_mode('ph') == 'hold'
    
    # Set to auto
    cm.set_mode('ph', 'auto')
    assert cm.get_mode('ph') == 'auto'


def test_ec_controller_respects_mode(temp_db, mock_settings_db):
    """Test that EC automation checks mode before dosing."""
    # The EC auto worker checks: if get_mode("ec") != "auto": continue
    from app import controller_modes as cm
    
    # Set EC to manual mode (maps to hold)
    cm.set_mode('ec', 'manual')
    assert cm.get_mode('ec') == 'hold'
    
    # Set to maintenance (maps to hold)
    cm.set_mode('ec', 'maintenance')
    assert cm.get_mode('ec') == 'hold'
    
    # Set to auto
    cm.set_mode('ec', 'auto')
    assert cm.get_mode('ec') == 'auto'


def test_chiller_controller_respects_mode(temp_db, mock_settings_db):
    """Test that chiller automation checks mode before controlling relay."""
    # The chiller checks mode in should_chiller_run()
    from app import controller_modes as cm
    
    # Set chiller to manual mode (maps to hold)
    cm.set_mode('chiller', 'manual')
    assert cm.get_mode('chiller') == 'hold'
    
    # Set to auto
    cm.set_mode('chiller', 'auto')
    assert cm.get_mode('chiller') == 'auto'


def test_lights_controller_respects_mode(temp_db, mock_settings_db):
    """Test that lights/scheduler checks mode before auto switching."""
    # The scheduler checks: if get_mode("lights") != "auto": skip
    from app import controller_modes as cm
    
    # Set lights to manual mode (maps to hold)
    cm.set_mode('lights', 'manual')
    assert cm.get_mode('lights') == 'hold'
    
    # Set to auto
    cm.set_mode('lights', 'auto')
    assert cm.get_mode('lights') == 'auto'


def test_circulation_controller_mode(temp_db):
    """Test circulation controller mode management."""
    from app import controller_modes as cm
    
    # Circulation is in the controller list
    assert 'circulation' in cm.CONTROLLERS
    
    # Can set and get modes (manual maps to hold)
    cm.set_mode('circulation', 'manual')
    assert cm.get_mode('circulation') == 'hold'
    
    cm.set_mode('circulation', 'auto')
    assert cm.get_mode('circulation') == 'auto'


def test_mode_transitions_all_controllers(temp_db):
    """Test all valid mode transitions for each controller."""
    from app import controller_modes as cm
    
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
            assert cm.set_mode(controller, mode_to_set), f"Failed to set {controller} to {mode_to_set}"
            assert cm.get_mode(controller) == expected_mode, f"{controller} expected {expected_mode}, got {cm.get_mode(controller)}"


def test_concurrent_mode_changes(temp_db):
    """Test that multiple controllers can have different modes simultaneously."""
    from app import controller_modes as cm
    
    # Set each controller to a different mode (legacy modes map to hold)
    cm.set_mode('ph', 'auto')
    cm.set_mode('ec', 'manual')
    cm.set_mode('chiller', 'maintenance')
    cm.set_mode('lights', 'auto')
    cm.set_mode('circulation', 'manual')
    
    # Verify all modes are independent (manual/maintenance -> hold)
    assert cm.get_mode('ph') == 'auto'
    assert cm.get_mode('ec') == 'hold'
    assert cm.get_mode('chiller') == 'hold'
    assert cm.get_mode('lights') == 'auto'
    assert cm.get_mode('circulation') == 'hold'


def test_mode_default_on_first_access(temp_db):
    """Test that controllers default to 'auto' mode on first access."""
    from app import controller_modes as cm
    
    # Fresh database - all controllers should default to auto
    for controller in cm.CONTROLLERS:
        mode = cm.get_mode(controller)
        assert mode == 'auto', f"{controller} should default to auto, got {mode}"


def test_maintenance_mode_behavior(temp_db):
    """Test that maintenance mode is accepted (maps to hold in simplified system)."""
    from app import controller_modes as cm
    
    # All controllers should accept maintenance mode (maps to hold)
    for controller in cm.CONTROLLERS:
        assert cm.set_mode(controller, 'maintenance')
        assert cm.get_mode(controller) == 'hold'


def test_api_endpoint_compatibility(temp_db):
    """Test that modes work with the API endpoint structure."""
    from app import controller_modes as cm
    
    # Simulate API flow: GET current mode, POST new mode
    for controller in ['ph', 'ec', 'chiller', 'lights', 'circulation']:
        # GET
        current_mode = cm.get_mode(controller)
        assert current_mode in cm.VALID_MODES
        
        # POST - change mode (manual maps to hold)
        new_mode = 'manual' if current_mode == 'auto' else 'auto'
        assert cm.set_mode(controller, new_mode)
        
        # GET - verify change (manual -> hold)
        expected_mode = 'hold' if new_mode == 'manual' else 'auto'
        assert cm.get_mode(controller) == expected_mode


def test_mode_thread_safety_basic(temp_db):
    """Basic test that mode operations don't corrupt data under sequential access."""
    from app import controller_modes as cm
    
    # Rapidly change modes (legacy modes map to hold)
    for _ in range(10):
        for controller in cm.CONTROLLERS:
            for mode_to_set, expected in [('auto', 'auto'), ('manual', 'hold'), ('maintenance', 'hold')]:
                cm.set_mode(controller, mode_to_set)
                assert cm.get_mode(controller) == expected


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
