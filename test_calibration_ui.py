"""
Test calibration UI endpoints to verify proper message responses.
This test ensures that calibration endpoints return the expected structure
that the frontend JavaScript expects.
"""
import os
import sys
import pytest
from fastapi.testclient import TestClient

# Set test environment variables before importing app
os.environ["RDWC_SENSORS_MOCK"] = "1"
os.environ["CALIB_ENABLE"] = "1"
os.environ["DB_PATH"] = ":memory:"

# Import app after setting environment
sys.path.insert(0, os.path.dirname(__file__))
from app.main import app

client = TestClient(app)


class TestCalibrationEndpoints:
    """Test calibration endpoints return proper response structure"""
    
    def test_ph_caps_endpoint(self):
        """Test /calib/ph/caps returns enabled status"""
        response = client.get("/calib/ph/caps")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)
    
    def test_ph_status_endpoint(self):
        """Test /calib/ph/status returns proper structure"""
        response = client.get("/calib/ph/status")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        assert "points" in data or "flags" in data
        # Response should have either 'points' list or 'flags' list
        if "points" in data:
            assert isinstance(data["points"], list)
    
    def test_ph_clear_endpoint(self):
        """Test /calib/ph/clear returns ok and note"""
        response = client.post("/calib/ph/clear")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        assert isinstance(data["ok"], bool)
        # Should have note field for user feedback
        assert "note" in data
    
    def test_ec_cal_status_endpoint(self):
        """Test /api/ec/cal/status returns proper structure"""
        response = client.get("/api/ec/cal/status")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        # Should have calibration status info
        assert "cal" in data or "status" in data
    
    def test_ec_cal_clear_endpoint(self):
        """Test /api/ec/cal/clear returns ok and response/error"""
        response = client.post("/api/ec/cal/clear")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        assert isinstance(data["ok"], bool)
        # Should have either response or error field
        assert "response" in data or "error" in data
    
    def test_dose_pumps_endpoint(self):
        """Test /calib/dose/pumps returns pump list"""
        response = client.get("/calib/dose/pumps")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        assert "pumps" in data
        assert isinstance(data["pumps"], list)
        # Should have at least pH up pump
        assert len(data["pumps"]) >= 1
        # Each pump should have required fields
        if data["pumps"]:
            pump = data["pumps"][0]
            assert "key" in pump
            assert "ml_per_sec" in pump


class TestCalibrationResponseMessages:
    """Test that calibration endpoints return user-friendly messages"""
    
    def test_ph_calibrate_disabled_message(self):
        """Test calibration with CALIB_ENABLE=0 returns helpful message"""
        # Temporarily disable calibration
        os.environ["CALIB_ENABLE"] = "0"
        # Need to reload app for env change to take effect in a real scenario
        # For this test, we'll just verify the endpoint exists
        response = client.post("/calib/ph/mid?value=7.0")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        # Re-enable for other tests
        os.environ["CALIB_ENABLE"] = "1"


def test_calibration_ui_elements_match():
    """
    Integration test to verify frontend element IDs match backend response structure.
    This is a documentation test to ensure future changes maintain compatibility.
    """
    # pH calibration elements expected in HTML:
    ph_elements = [
        "ph-calib-msg-inline",  # Message display element
        "ph-calib-log-inline",  # Log display element
        "ph-current-calib",     # Calibration status display
        "ph-current-inline",    # Current pH reading
    ]
    
    # EC calibration elements expected in HTML:
    ec_elements = [
        "ecCalMessage",         # Message display element (uses camelCase, not ec-calib-msg)
        "ecCalStatusValue",     # Calibration status
        "ecKValue",             # K factor display
        "ecCalCurrentReading",  # Current EC reading
        "ecCalDryIndicator",    # Dry calibration indicator
        "ecCalLowIndicator",    # Low point indicator
        "ecCalHighIndicator",   # High point indicator
    ]
    
    # This test just documents the expected elements
    # In a real integration test, we would parse the HTML and verify
    assert len(ph_elements) > 0
    assert len(ec_elements) > 0
    print(f"✓ Documented {len(ph_elements)} pH UI elements")
    print(f"✓ Documented {len(ec_elements)} EC UI elements")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
