"""
API endpoint tests for simplified Hold button system.

Tests the new /api/controller/{name}/hold and /api/controller/hold/all endpoints.
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


def test_hold_toggle_from_auto(client):
    """Test toggling hold from auto state (no body = toggle)."""
    # Start in auto (default)
    response = client.get("/api/controller/ph/mode")
    assert response.json()["mode"] == "auto"
    
    # Toggle to hold
    response = client.post("/api/controller/ph/hold", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["held"] is True
    assert data["mode"] == "hold"
    
    # Verify it persisted
    response = client.get("/api/controller/ph/mode")
    assert response.json()["mode"] == "hold"


def test_hold_toggle_from_hold(client):
    """Test toggling hold from hold state (toggle back to auto)."""
    # Set to hold
    client.post("/api/controller/ph/mode", json={"mode": "hold"})
    
    # Toggle back to auto
    response = client.post("/api/controller/ph/hold", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["held"] is False
    assert data["mode"] == "auto"


def test_hold_explicit_set_true(client):
    """Test explicitly setting hold to true."""
    response = client.post("/api/controller/ec/hold", json={"hold": True})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["held"] is True
    assert data["mode"] == "hold"


def test_hold_explicit_set_false(client):
    """Test explicitly setting hold to false (resume)."""
    # First set to hold
    client.post("/api/controller/ec/hold", json={"hold": True})
    
    # Then resume
    response = client.post("/api/controller/ec/hold", json={"hold": False})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["held"] is False
    assert data["mode"] == "auto"


def test_hold_invalid_controller(client):
    """Test hold endpoint with invalid controller name."""
    response = client.post("/api/controller/invalid_controller/hold", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "unknown_controller"


def test_hold_all_controllers_explicit_hold(client):
    """Test holding all controllers at once."""
    # Set some controllers to different states first
    client.post("/api/controller/ph/mode", json={"mode": "auto"})
    client.post("/api/controller/ec/mode", json={"mode": "auto"})
    client.post("/api/controller/chiller/mode", json={"mode": "auto"})
    
    # Hold all
    response = client.post("/api/controller/hold/all", json={"hold": True})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["hold"] is True
    
    # Verify all are held
    modes = data["modes"]
    assert modes["ph"] == "hold"
    assert modes["ec"] == "hold"
    assert modes["chiller"] == "hold"
    assert modes["lights"] == "hold"
    assert modes["circulation"] == "hold"


def test_hold_all_controllers_explicit_resume(client):
    """Test resuming all controllers at once."""
    # First hold all
    client.post("/api/controller/hold/all", json={"hold": True})
    
    # Then resume all
    response = client.post("/api/controller/hold/all", json={"hold": False})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["hold"] is False
    
    # Verify all are auto
    modes = data["modes"]
    assert modes["ph"] == "auto"
    assert modes["ec"] == "auto"
    assert modes["chiller"] == "auto"
    assert modes["lights"] == "auto"
    assert modes["circulation"] == "auto"


def test_hold_all_requires_explicit_parameter(client):
    """Test that hold/all endpoint requires explicit hold parameter."""
    response = client.post("/api/controller/hold/all", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "must_specify_hold"


def test_hold_independent_controllers(client):
    """Test that hold works independently for each controller."""
    # Hold pH
    client.post("/api/controller/ph/hold", json={"hold": True})
    
    # Hold EC
    client.post("/api/controller/ec/hold", json={"hold": True})
    
    # Leave chiller in auto
    client.post("/api/controller/chiller/hold", json={"hold": False})
    
    # Verify independent states
    assert client.get("/api/controller/ph/mode").json()["mode"] == "hold"
    assert client.get("/api/controller/ec/mode").json()["mode"] == "hold"
    assert client.get("/api/controller/chiller/mode").json()["mode"] == "auto"


def test_hold_persists_across_requests(client):
    """Test that hold state persists across multiple requests."""
    # Set hold
    client.post("/api/controller/lights/hold", json={"hold": True})
    
    # Multiple GET requests should return held state
    for _ in range(3):
        response = client.get("/api/controller/lights/mode")
        assert response.json()["mode"] == "hold"
    
    # Resume
    client.post("/api/controller/lights/hold", json={"hold": False})
    
    # Multiple GET requests should return auto state
    for _ in range(3):
        response = client.get("/api/controller/lights/mode")
        assert response.json()["mode"] == "auto"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
