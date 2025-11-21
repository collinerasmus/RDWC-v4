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
    """Test GET /api/controller/modes endpoint."""
    response = client.get("/api/controller/modes")
    assert response.status_code == 200
    
    data = response.json()
    assert "modes" in data
    assert "valid" in data
    
    # Should have all controllers
    modes = data["modes"]
    assert "ph" in modes
    assert "ec" in modes
    assert "chiller" in modes
    assert "lights" in modes
    assert "circulation" in modes
    
    # Valid modes should be listed (simplified to auto and hold)
    valid = data["valid"]
    assert "auto" in valid
    assert "hold" in valid


def test_get_specific_controller_mode(client):
    """Test GET /api/controller/{name}/mode endpoint."""
    controllers = ["ph", "ec", "chiller", "lights", "circulation"]
    
    for controller in controllers:
        response = client.get(f"/api/controller/{controller}/mode")
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] is True
        assert data["controller"] == controller
        assert data["mode"] in ["auto", "hold"]  # Simplified modes
        assert "valid" in data


def test_get_invalid_controller_mode(client):
    """Test GET /api/controller/{name}/mode with invalid controller."""
    response = client.get("/api/controller/invalid_controller/mode")
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "unknown_controller"
    assert data["controller"] == "invalid_controller"


def test_set_controller_mode(client):
    """Test POST /api/controller/{name}/mode endpoint."""
    # Set pH to manual (maps to hold in simplified system)
    response = client.post(
        "/api/controller/ph/mode",
        json={"mode": "manual"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert data["controller"] == "ph"
    assert data["mode"] == "hold"  # Legacy manual maps to hold
    
    # Verify it persisted
    response = client.get("/api/controller/ph/mode")
    assert response.status_code == 200
    assert response.json()["mode"] == "hold"


def test_set_controller_mode_to_auto(client):
    """Test switching controller to auto mode."""
    # Set EC to auto
    response = client.post(
        "/api/controller/ec/mode",
        json={"mode": "auto"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert data["mode"] == "auto"


def test_set_controller_mode_to_maintenance(client):
    """Test switching controller to maintenance mode."""
    # Set chiller to maintenance (maps to hold in simplified system)
    response = client.post(
        "/api/controller/chiller/mode",
        json={"mode": "maintenance"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["ok"] is True
    assert data["mode"] == "hold"  # Legacy maintenance maps to hold


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
    """Test that each controller's mode is independent."""
    # Set each to different mode (legacy modes map to hold)
    modes_to_set = {
        "ph": "manual",
        "ec": "auto",
        "chiller": "maintenance",
        "lights": "manual",
        "circulation": "auto"
    }
    
    # Expected modes after mapping
    expected_modes = {
        "ph": "hold",
        "ec": "auto",
        "chiller": "hold",
        "lights": "hold",
        "circulation": "auto"
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
    controller = "lights"
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
    controller = "circulation"
    
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
