"""
Tests for the consolidated controllers status API endpoint.
Validates the atomic snapshot endpoint for UI synchronization.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_controllers_status_endpoint_exists():
    """Test that the consolidated status endpoint is accessible."""
    response = client.get("/api/controllers/status")
    assert response.status_code == 200


def test_controllers_status_shape():
    """Test that the response has the expected structure."""
    response = client.get("/api/controllers/status")
    assert response.status_code == 200
    
    data = response.json()
    
    # Top-level keys
    assert "system_mode" in data
    assert "maintenance_override" in data
    assert "estop" in data
    assert "controllers" in data
    assert "timestamp" in data
    
    # System mode should be auto or manual
    assert data["system_mode"] in ["auto", "manual"]
    
    # Maintenance override should be boolean
    assert isinstance(data["maintenance_override"], bool)
    
    # E-stop should be boolean
    assert isinstance(data["estop"], bool)
    
    # Timestamp should be an integer
    assert isinstance(data["timestamp"], int)
    
    # Controllers should be a dict
    assert isinstance(data["controllers"], dict)


def test_controllers_status_has_all_controllers():
    """Test that all expected controllers are present."""
    response = client.get("/api/controllers/status")
    assert response.status_code == 200
    
    data = response.json()
    controllers = data["controllers"]
    
    # Check for all expected controllers
    expected_controllers = ["ph", "ec", "chiller", "lights", "circulation"]
    for ctrl in expected_controllers:
        assert ctrl in controllers, f"Missing controller: {ctrl}"


def test_ph_controller_structure():
    """Test that pH controller data has expected fields."""
    response = client.get("/api/controllers/status")
    assert response.status_code == 200
    
    data = response.json()
    ph = data["controllers"]["ph"]
    
    # Required fields (even if error occurred, should have mode)
    assert "mode" in ph
    
    # If no error, should have full structure
    if "error" not in ph:
        assert "auto_enabled" in ph
        assert "guards" in ph
        assert "targets" in ph
        # Optional fields
        # holding_reason can be None
        # learned_ml_per_pH can be None


def test_ec_controller_structure():
    """Test that EC controller data has expected fields."""
    response = client.get("/api/controllers/status")
    assert response.status_code == 200
    
    data = response.json()
    ec = data["controllers"]["ec"]
    
    # Required fields
    assert "mode" in ec
    
    # If no error, should have full structure
    if "error" not in ec:
        assert "auto_enabled" in ec
        assert "guards" in ec
        assert "targets" in ec


def test_chiller_controller_structure():
    """Test that chiller controller data has expected fields."""
    response = client.get("/api/controllers/status")
    assert response.status_code == 200
    
    data = response.json()
    chiller = data["controllers"]["chiller"]
    
    # Required fields
    assert "mode" in chiller
    
    # If no error, should have full structure
    if "error" not in chiller:
        assert "auto_enabled" in chiller
        # current_temp might be None if sensor not available


def test_lights_controller_structure():
    """Test that lights controller data has expected fields."""
    response = client.get("/api/controllers/status")
    assert response.status_code == 200
    
    data = response.json()
    lights = data["controllers"]["lights"]
    
    # Required fields
    assert "mode" in lights
    
    # If no error, should have full structure
    if "error" not in lights:
        assert "is_on" in lights
        assert "schedule_active" in lights
        assert isinstance(lights["is_on"], bool)
        assert isinstance(lights["schedule_active"], bool)


def test_circulation_controller_structure():
    """Test that circulation controller data has expected fields."""
    response = client.get("/api/controllers/status")
    assert response.status_code == 200
    
    data = response.json()
    circulation = data["controllers"]["circulation"]
    
    # Required fields
    assert "mode" in circulation
    
    # If no error, should have full structure
    if "error" not in circulation:
        assert "main_pump" in circulation
        assert "chiller_pump" in circulation
        assert isinstance(circulation["main_pump"], bool)
        assert isinstance(circulation["chiller_pump"], bool)


def test_controller_modes_are_valid():
    """Test that all controller modes are valid values."""
    response = client.get("/api/controllers/status")
    assert response.status_code == 200
    
    data = response.json()
    valid_modes = {"auto", "manual", "maintenance"}
    
    for ctrl_name, ctrl_data in data["controllers"].items():
        assert "mode" in ctrl_data
        assert ctrl_data["mode"] in valid_modes, f"{ctrl_name} has invalid mode: {ctrl_data['mode']}"


def test_status_response_is_fast():
    """Test that the endpoint responds quickly (should be cached/lightweight)."""
    import time
    
    start = time.time()
    response = client.get("/api/controllers/status")
    elapsed = time.time() - start
    
    assert response.status_code == 200
    # Should respond in under 2 seconds (reasonable for non-cached initial request)
    assert elapsed < 2.0, f"Status endpoint took {elapsed:.2f}s, should be < 2s"
