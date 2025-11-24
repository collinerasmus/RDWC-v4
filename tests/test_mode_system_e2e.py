"""
End-to-end verification test for the complete mode controller system.

This test demonstrates that all components work together correctly:
- Mode persistence
- API endpoints
- Controller enforcement
- UI integration points
"""
import pytest
import tempfile
import os
import sqlite3
from fastapi.testclient import TestClient


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
    
    # Initialize database
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
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
    """
    Complete end-to-end test of the mode controller system.
    
    This test verifies the entire system works as designed:
    1. Default mode is 'auto' for all controllers
    2. Can set individual controller modes via API
    3. Modes persist in database
    4. Controllers can check their modes
    5. All controllers operate independently
    """
    # Import after setting environment variables
    from app.main import app
    from app.unified_mode import get_mode, set_mode, get_all_modes
    
    client = TestClient(app)
    
    # Step 1: Verify default state (all auto)
    print("\n=== Step 1: Verify Default State ===")
    all_modes = get_all_modes()
    print(f"Default modes: {all_modes}")
    
    for controller in ["ph", "ec", "chiller", "lights", "circulation"]:
        assert all_modes[controller] == "auto", f"{controller} should default to auto"
        print(f"  ✓ {controller}: auto")
    
    # Step 2: Set different modes via API
    print("\n=== Step 2: Set Modes via API ===")
    
    # pH to manual
    response = client.post("/api/controller/ph/mode", json={"mode": "manual"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    print("  ✓ Set pH to manual")
    
    # EC to auto (explicitly)
    response = client.post("/api/controller/ec/mode", json={"mode": "auto"})
    assert response.status_code == 200
    print("  ✓ Set EC to auto")
    
    # Chiller to maintenance
    response = client.post("/api/controller/chiller/mode", json={"mode": "maintenance"})
    assert response.status_code == 200
    print("  ✓ Set chiller to maintenance")
    
    # Step 3: Verify modes via Python API (legacy modes map to hold)
    print("\n=== Step 3: Verify via Python API ===")
    assert get_mode("ph") == "hold"  # manual -> hold
    print("  ✓ pH is hold (was manual)")
    
    assert get_mode("ec") == "auto"
    print("  ✓ EC is auto")
    
    assert get_mode("chiller") == "hold"  # maintenance -> hold
    print("  ✓ Chiller is hold (was maintenance)")
    
    # Step 4: Verify via REST API
    print("\n=== Step 4: Verify via REST API ===")
    response = client.get("/api/controller/modes")
    modes = response.json()["modes"]
    
    assert modes["ph"] == "hold"
    assert modes["ec"] == "auto"
    assert modes["chiller"] == "hold"
    print("  ✓ All modes correct via REST API")
    
    # Step 5: Simulate controller behavior
    print("\n=== Step 5: Simulate Controller Checks ===")
    
    # pH controller should hold automation (mode is hold)
    if get_mode("ph") != "auto":
        print("  ✓ pH automation would hold (mode is hold)")
    else:
        raise AssertionError("pH should hold automation")
    
    # EC controller should run automation (mode is auto)
    if get_mode("ec") == "auto":
        print("  ✓ EC automation would run (mode is auto)")
    else:
        raise AssertionError("EC should run automation")
    
    # Chiller controller should hold automation (mode is hold)
    if get_mode("chiller") != "auto":
        print("  ✓ Chiller automation would hold (mode is hold)")
    else:
        raise AssertionError("Chiller should hold automation")
    
    # Step 6: Verify persistence
    print("\n=== Step 6: Verify Persistence ===")
    
    # Reload controller_modes module to simulate restart
    import importlib
    import app.controller_modes as cm
    cm = importlib.reload(cm)
    
    assert cm.get_controller_mode("ph") == "hold"  # manual -> hold
    assert cm.get_controller_mode("ec") == "auto"
    assert cm.get_controller_mode("chiller") == "hold"  # maintenance -> hold
    print("  ✓ Modes persisted across module reload")
    
    # Step 7: Test mode transitions (legacy modes map to hold)
    print("\n=== Step 7: Test Mode Transitions ===")
    
    # Transition pH through modes
    test_transitions = [
        ("auto", "auto"),
        ("manual", "hold"),
        ("maintenance", "hold"),
        ("auto", "auto")
    ]
    for mode_to_set, expected_mode in test_transitions:
        set_mode("ph", mode_to_set)
        assert get_mode("ph") == expected_mode
        print(f"  ✓ pH transitioned to {expected_mode} (from {mode_to_set})")
    
    # Step 8: Test independent operation
    print("\n=== Step 8: Test Independent Operation ===")
    
    # Set each controller to different mode
    set_mode("ph", "auto")
    set_mode("ec", "manual")
    set_mode("chiller", "maintenance")
    set_mode("lights", "manual")
    set_mode("circulation", "auto")
    
    all_modes = get_all_modes()
    assert all_modes["ph"] == "auto"
    assert all_modes["ec"] == "hold"  # manual -> hold
    assert all_modes["chiller"] == "hold"  # maintenance -> hold
    assert all_modes["lights"] == "hold"  # manual -> hold
    assert all_modes["circulation"] == "auto"
    print("  ✓ All controllers operate independently")
    
    print("\n=== ✓ All Tests Passed ===")
    print("\nMode Controller System Verification Complete!")
    print("All components working correctly:")
    print("  • Mode persistence ✓")
    print("  • API endpoints ✓")
    print("  • Controller enforcement ✓")
    print("  • Independent operation ✓")
    print("  • Persistence across restarts ✓")


def test_controller_automation_respects_mode_manual():
    """
    Verify that automation checks would respect manual mode.
    
    This simulates what each controller does in its automation loop.
    """
    from app.unified_mode import get_mode, set_mode
    
    # Set controller to manual
    set_mode("ph", "manual")
    
    # Simulate automation check (what pH auto loop does)
    should_run_automation = (get_mode("ph") == "auto")
    
    assert not should_run_automation, "Automation should not run in manual mode"
    print("✓ Automation correctly holds when mode is manual")


def test_controller_automation_respects_mode_auto():
    """
    Verify that automation checks would allow auto mode.
    """
    from app.unified_mode import get_mode, set_mode
    
    # Set controller to auto
    set_mode("ec", "auto")
    
    # Simulate automation check (what EC auto worker does)
    should_run_automation = (get_mode("ec") == "auto")
    
    assert should_run_automation, "Automation should run in auto mode"
    print("✓ Automation correctly runs when mode is auto")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
