"""
API endpoint tests for mode controller system.

Tests the REST API endpoints for managing controller modes.
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
    
    # Set environment variables
    os.environ["RDWC_CONTROLLER_MODES_DB"] = db_path
    os.environ["RDWC_DB"] = db_path
    os.environ["RDWC_DB_PATH"] = db_path
    
    # Initialize database with settings table
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


@pytest.fixture
def client(temp_db):
    """Create a TestClient for the FastAPI app."""
    # Import after setting environment variables
    from app.main import app
    return TestClient(app)


def test_get_all_controller_modes(client):
    """Test GET /api/controller/modes endpoint.
    
    NOTE: This endpoint is deprecated. Use GET /api/auto/status instead.
    """
    response = client.get("/api/controller/modes")
    assert response.status_code == 200
    
    data = response.json()
    assert "modes" in data
    assert "_deprecated" in data  # Now includes deprecation notice
    
    # Should have all controllers
    modes = data["modes"]
    assert "ph" in modes
    assert "ec" in modes
    assert "chiller" in modes


def test_get_specific_controller_mode(client):
    """Test GET /api/controller/{name}/mode endpoint.
    
    NOTE: This endpoint is deprecated. Use GET /api/auto/status instead.
    """
    controllers = ["ph", "ec", "chiller"]
    
    for controller in controllers:
        response = client.get(f"/api/controller/{controller}/mode")
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] is True
        assert data["controller"] == controller
        assert data["mode"] in ["auto", "hold"]  # Simplified modes
        assert "_deprecated" in data


def test_get_invalid_controller_mode(client):
    """Test GET /api/controller/{name}/mode with invalid controller."""
    response = client.get("/api/controller/invalid_controller/mode")
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "unknown_controller"
    assert data["controller"] == "invalid_controller"


def test_set_controller_mode(client):
    """Test POST /api/controller/{name}/mode endpoint.
    
    NOTE: This endpoint is deprecated. Use POST /api/auto/{controller} instead.
    """
    # Set pH to manual (disables auto for pH)
    response = client.post(
        "/api/controller/ph/mode",
        json={"mode": "manual"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert data["controller"] == "ph"
    assert data["mode"] == "hold"  # Legacy manual maps to hold
    assert "_deprecated" in data


def test_set_controller_mode_to_auto(client):
    """Test switching controller to auto mode.
    
    NOTE: This endpoint is deprecated. Use POST /api/auto/{controller} instead.
    """
    # Set EC to auto
    response = client.post(
        "/api/controller/ec/mode",
        json={"mode": "auto"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert data["mode"] == "auto"
    assert "_deprecated" in data


def test_set_controller_mode_to_maintenance(client):
    """Test switching controller to maintenance mode.
    
    NOTE: This endpoint is deprecated. Use POST /api/auto/{controller} instead.
    """
    # Set chiller to maintenance (maps to hold in simplified system)
    response = client.post(
        "/api/controller/chiller/mode",
        json={"mode": "maintenance"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert data["mode"] == "hold"  # Legacy maintenance maps to hold
    assert "_deprecated" in data


def test_set_invalid_mode(client):
    """Test POST with invalid mode value."""
    response = client.post(
        "/api/controller/ph/mode",
        json={"mode": "invalid"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is False


def test_set_mode_for_invalid_controller(client):
    """Test POST with invalid controller name."""
    response = client.post(
        "/api/controller/invalid/mode",
        json={"mode": "auto"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "unknown_controller"


def test_set_mode_without_mode_field(client):
    """Test POST without 'mode' field in body."""
    response = client.post(
        "/api/controller/ph/mode",
        json={}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is False


def test_mode_persistence_across_requests(client):
    """Test that mode changes persist across multiple requests."""
    # Set modes for multiple controllers (legacy modes map to hold)
    client.post("/api/controller/ph/mode", json={"mode": "manual"})
    client.post("/api/controller/ec/mode", json={"mode": "auto"})
    client.post("/api/controller/chiller/mode", json={"mode": "maintenance"})
    
    # Verify persistence (manual and maintenance map to hold)
    assert client.get("/api/controller/ph/mode").json()["mode"] == "hold"
    assert client.get("/api/controller/ec/mode").json()["mode"] == "auto"
    assert client.get("/api/controller/chiller/mode").json()["mode"] == "hold"


def test_all_controllers_can_be_set_independently(client):
    """Test that each controller's mode is independent.
    
    NOTE: Only ph, ec, chiller are supported in the new auto-enable system.
    lights and circulation are not individual controller targets.
    """
    # Set each to different mode (legacy modes map to hold)
    modes_to_set = {
        "ph": "manual",
        "ec": "auto",
        "chiller": "maintenance",
    }
    
    # Expected modes after mapping
    expected_modes = {
        "ph": "hold",
        "ec": "auto",
        "chiller": "hold",
    }
    
    for controller, mode in modes_to_set.items():
        response = client.post(
            f"/api/controller/{controller}/mode",
            json={"mode": mode}
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True
    
    # Verify all are set correctly (with mapping)
    for controller, expected_mode in expected_modes.items():
        response = client.get(f"/api/controller/{controller}/mode")
        assert response.json()["mode"] == expected_mode


def test_mode_transition_sequence(client):
    """Test complete mode transition sequence for a controller."""
    controller = "ph"  # Changed from lights to ph (supported controller)
    # Test transitions with legacy mode mapping
    transitions = [
        ("auto", "auto"),
        ("manual", "hold"),
        ("maintenance", "hold"),
        ("auto", "auto"),
        ("hold", "hold")
    ]
    
    for mode_to_set, expected_mode in transitions:
        # Set mode
        set_response = client.post(
            f"/api/controller/{controller}/mode",
            json={"mode": mode_to_set}
        )
        assert set_response.status_code == 200
        assert set_response.json()["ok"] is True
        
        # Verify mode (with mapping)
        get_response = client.get(f"/api/controller/{controller}/mode")
        assert get_response.json()["mode"] == expected_mode


def test_get_all_modes_reflects_changes(client):
    """Test that GET /api/controller/modes shows current state."""
    # Change some modes (legacy modes map to hold)
    client.post("/api/controller/ph/mode", json={"mode": "manual"})
    client.post("/api/controller/ec/mode", json={"mode": "maintenance"})
    
    # Get all modes
    response = client.get("/api/controller/modes")
    modes = response.json()["modes"]
    
    # Both should be hold
    assert modes["ph"] == "hold"
    assert modes["ec"] == "hold"


def test_concurrent_mode_changes_via_api(client):
    """Test rapid mode changes don't corrupt data."""
    controller = "chiller"  # Changed from circulation to chiller (supported controller)
    
    # Rapidly change modes (legacy modes map to hold)
    for _ in range(5):
        client.post(f"/api/controller/{controller}/mode", json={"mode": "auto"})
        client.post(f"/api/controller/{controller}/mode", json={"mode": "manual"})
        client.post(f"/api/controller/{controller}/mode", json={"mode": "maintenance"})
    
    # Final state should be valid (hold since last was maintenance)
    response = client.get(f"/api/controller/{controller}/mode")
    assert response.json()["mode"] in ["auto", "hold"]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


# === NEW UNIFIED AUTO-ENABLE SYSTEM TESTS ===

def test_get_auto_status(client):
    """Test GET /api/auto/status endpoint."""
    response = client.get("/api/auto/status")
    assert response.status_code == 200
    
    data = response.json()
    assert "global_auto" in data
    assert "controllers" in data
    assert isinstance(data["global_auto"], bool)
    
    # Should have all controllers
    controllers = data["controllers"]
    assert "ph" in controllers
    assert "ec" in controllers
    assert "chiller" in controllers
    
    # Each controller should have auto_enabled and will_automate
    for ctrl in ["ph", "ec", "chiller"]:
        assert "auto_enabled" in controllers[ctrl]
        assert "will_automate" in controllers[ctrl]


def test_set_global_auto_enabled(client):
    """Test POST /api/auto/global endpoint."""
    # Enable global auto
    response = client.post("/api/auto/global", json={"enabled": True})
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert data["global_auto"] is True
    
    # Verify via status
    status = client.get("/api/auto/status").json()
    assert status["global_auto"] is True
    
    # Disable global auto
    response = client.post("/api/auto/global", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["global_auto"] is False


def test_set_controller_auto_enabled(client):
    """Test POST /api/auto/{controller} endpoint."""
    # Enable pH auto
    response = client.post("/api/auto/ph", json={"enabled": True})
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert data["controller"] == "ph"
    assert data["auto_enabled"] is True
    
    # Verify via status
    status = client.get("/api/auto/status").json()
    assert status["controllers"]["ph"]["auto_enabled"] is True


def test_auto_requires_both_global_and_controller(client):
    """Test that automation only runs when both global and controller auto are enabled."""
    # Disable global, enable pH
    client.post("/api/auto/global", json={"enabled": False})
    client.post("/api/auto/ph", json={"enabled": True})
    
    status = client.get("/api/auto/status").json()
    assert status["global_auto"] is False
    assert status["controllers"]["ph"]["auto_enabled"] is True
    assert status["controllers"]["ph"]["will_automate"] is False  # Should not automate
    
    # Enable global
    client.post("/api/auto/global", json={"enabled": True})
    
    status = client.get("/api/auto/status").json()
    assert status["controllers"]["ph"]["will_automate"] is True  # Now should automate


def test_auto_invalid_controller(client):
    """Test POST /api/auto/{controller} with invalid controller."""
    response = client.post("/api/auto/invalid", json={"enabled": True})
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "unknown_controller"


def test_auto_missing_enabled_field(client):
    """Test POST /api/auto/global without enabled field."""
    response = client.post("/api/auto/global", json={})
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "missing_enabled_field"
