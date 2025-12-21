"""
End-to-end verification test for the unified mode system.
"""
import pytest
import tempfile
import os
import sqlite3


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp.close()
    db_path = tmp.name
    
    # Set environment variables for all components
    os.environ["RDWC_CONTROLLER_MODES_DB"] = db_path
    os.environ["RDWC_DB"] = db_path
    os.environ["RDWC_DB_PATH"] = db_path
    
    # Initialize database with defaults
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Set default unified mode to manual (safety first)
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("unified_mode", "manual")
        )
        conn.commit()
    
    yield db_path
    
    # Cleanup
    for var in ["RDWC_CONTROLLER_MODES_DB", "RDWC_DB", "RDWC_DB_PATH"]:
        if var in os.environ:
            del os.environ[var]
    
    try:
        os.unlink(db_path)
    except Exception:
        pass


def test_complete_mode_system_workflow(temp_db):
    """Test unified mode persistence and transitions."""
    from app.unified_mode import get_mode, set_mode, get_all_modes
    
    # Step 1: Verify we can read/write modes
    print("\n=== Step 1: Test Mode Set/Get ===")
    set_mode("manual")
    assert get_mode() == "manual"
    print("  OK: Manual mode set and verified")
    
    # Step 2: Switch to auto
    print("\n=== Step 2: Test Auto Mode ===")
    set_mode("auto")
    assert get_mode() == "auto"
    print("  OK: Auto mode set and verified")
    
    # Step 3: Verify get_all_modes maps correctly
    print("\n=== Step 3: Test All Modes Mapping ===")
    all_modes = get_all_modes()
    assert all_modes["ph"] == "auto"
    assert all_modes["chiller"] == "auto"
    print("  OK: All controllers show auto mode")
    
    # Step 4: Switch to maintenance (should map to 'hold' in get_all_modes)
    print("\n=== Step 4: Test Maintenance Mode ===")
    set_mode("maintenance")
    assert get_mode() == "maintenance"
    all_modes = get_all_modes()
    assert all_modes["ph"] == "hold", f"Expected 'hold' but got {all_modes['ph']}"
    print("  OK: Maintenance mode maps to 'hold' in get_all_modes")
    
    # Step 5: Switch back to auto
    print("\n=== Step 5: Return to Auto ===")
    set_mode("auto")
    assert get_mode() == "auto"
    all_modes = get_all_modes()
    assert all_modes["chiller"] == "auto"
    print("  OK: System returned to auto mode")
    
    print("\n=== All Tests Passed ===")


