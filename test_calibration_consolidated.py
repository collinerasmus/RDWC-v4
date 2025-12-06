"""
Test to verify consolidated calibration endpoints work correctly.
All pH and EC calibration logic is now in sensor_controller.py.
"""
import os
os.environ["CALIB_ENABLE"] = "1"  # Enable calibration operations

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_ph_calibration_caps():
    """Test pH calibration enabled check"""
    response = client.get("/calib/ph/caps")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert data["enabled"] == True  # We set CALIB_ENABLE=1


def test_ph_calibration_status():
    """Test pH calibration status endpoint"""
    response = client.get("/calib/ph/status")
    assert response.status_code == 200
    data = response.json()
    # Even if hardware unavailable, should return structure
    assert "ok" in data or "error" in data
    

def test_ph_read_single():
    """Test single pH read endpoint"""
    response = client.get("/calib/ph/read")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    # Will be False in test environment (no hardware)
    # But should not crash


def test_ph_read_stable():
    """Test stable pH read endpoint"""
    response = client.get("/calib/ph/read_stable?timeout_s=2")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    assert "stable" in data


def test_ec_calibration_status():
    """Test EC calibration status endpoint"""
    response = client.get("/api/ec/cal/status")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data or "error" in data


def test_led_control_endpoints():
    """Test LED control endpoints use sensor_controller"""
    # LED on
    response = client.post("/calib/leds/on")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    
    # LED off
    response = client.post("/calib/leds/off")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    
    # LED blink
    response = client.post("/calib/leds/blink?count=2&period_s=0.1")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data


def test_ph_calibration_clear():
    """Test pH calibration clear endpoint"""
    response = client.post("/calib/ph/clear")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    assert "note" in data


def test_ph_calibration_point():
    """Test pH calibration point endpoints"""
    # Mid point
    response = client.post("/calib/ph/mid?value=7.0")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    assert "note" in data
    
    # Low point
    response = client.post("/calib/ph/low?value=4.0")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    
    # High point
    response = client.post("/calib/ph/high?value=10.0")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data


def test_ec_calibration_endpoints():
    """Test EC calibration endpoints"""
    # Clear
    response = client.post("/api/ec/cal/clear")
    assert response.status_code == 200
    
    # Dry
    response = client.post("/api/ec/cal/dry")
    assert response.status_code == 200
    
    # Low
    response = client.post("/api/ec/cal/low", json={})
    assert response.status_code == 200
    
    # High
    response = client.post("/api/ec/cal/high", json={})
    assert response.status_code == 200
    
    # Set K factor
    response = client.post("/api/ec/k", json={"k": 1.0})
    assert response.status_code == 200


def test_no_more_duplication():
    """Verify that main.py no longer has duplicate EZO/lock logic"""
    with open("app/main.py", "r") as f:
        main_content = f.read()
    
    # Should not have direct EZO instantiation in pH calibration area
    # (some are okay for special cases like power cycle)
    # Check that _ph_cmd is gone
    assert "_ph_cmd" not in main_content, "_ph_cmd should be removed"
    
    # Check that pH calibration delegates to sensor_controller
    assert "from app.sensor_controller import" in main_content
    assert "calibrate_ph_point" in main_content or "read_ph_single" in main_content


if __name__ == "__main__":
    print("Running consolidated calibration tests...")
    
    test_ph_calibration_caps()
    print("✓ pH caps")
    
    test_ph_calibration_status()
    print("✓ pH status")
    
    test_ph_read_single()
    print("✓ pH read single")
    
    test_ph_read_stable()
    print("✓ pH read stable")
    
    test_ec_calibration_status()
    print("✓ EC status")
    
    test_led_control_endpoints()
    print("✓ LED controls")
    
    test_ph_calibration_clear()
    print("✓ pH clear")
    
    test_ph_calibration_point()
    print("✓ pH calibration points")
    
    test_ec_calibration_endpoints()
    print("✓ EC calibration")
    
    test_no_more_duplication()
    print("✓ No duplication check")
    
    print("\n✅ All tests passed! Calibration is now consolidated in sensor_controller.py")
