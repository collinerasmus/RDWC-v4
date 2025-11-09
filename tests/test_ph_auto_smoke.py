"""
Smoke tests for pH Up Automation v1.0

Fast, minimal tests that don't require special hardware mocking.
Run with: pytest -m smoke tests/test_ph_auto_smoke.py
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.mark.smoke
def test_status_auto_keys_present():
    """Verify /api/ph/status contains required auto fields."""
    resp = client.get("/api/ph/status")
    assert resp.status_code == 200
    
    data = resp.json()
    assert "auto" in data, "Missing 'auto' key in status"
    
    auto = data["auto"]
    assert "enabled" in auto, "Missing 'enabled' in auto"
    assert "holding_reason" in auto, "Missing 'holding_reason' in auto"
    assert "learned_ml_per_pH" in auto, "Missing 'learned_ml_per_pH' in auto"
    
    # Type checks
    assert isinstance(auto["enabled"], bool), "auto.enabled must be bool"
    # holding_reason can be str or None
    assert auto["holding_reason"] is None or isinstance(auto["holding_reason"], str), \
        "auto.holding_reason must be str or None"
    # learned_ml_per_pH can be number or None
    assert auto["learned_ml_per_pH"] is None or isinstance(auto["learned_ml_per_pH"], (int, float)), \
        "auto.learned_ml_per_pH must be number or None"
    
    print(f"✅ Status auto keys present: enabled={auto['enabled']}, "
          f"holding_reason={auto['holding_reason']}, "
          f"learned={auto['learned_ml_per_pH']}")


@pytest.mark.smoke
def test_reset_endpoint_works():
    """Verify /api/ph/auto/learn/reset returns ok and resets learned value."""
    # Get initial learned value
    resp1 = client.get("/api/ph/status")
    assert resp1.status_code == 200
    learned_before = resp1.json()["auto"]["learned_ml_per_pH"]
    print(f"Learned before reset: {learned_before}")
    
    # Call reset endpoint
    resp2 = client.post("/api/ph/auto/learn/reset")
    assert resp2.status_code == 200
    
    reset_data = resp2.json()
    assert "ok" in reset_data, "Missing 'ok' in reset response"
    assert reset_data["ok"] is True, "Reset endpoint did not return ok:true"
    assert "message" in reset_data, "Missing 'message' in reset response"
    
    # Verify learned value is now default (50.0)
    resp3 = client.get("/api/ph/status")
    assert resp3.status_code == 200
    learned_after = resp3.json()["auto"]["learned_ml_per_pH"]
    print(f"Learned after reset: {learned_after}")
    
    # Should be 50.0 (default when no valid samples)
    assert learned_after == 50.0 or learned_after == 50, \
        f"Expected learned to reset to 50.0, got {learned_after}"
    
    print(f"✅ Reset endpoint works: {learned_before} → {learned_after}")


@pytest.mark.smoke
def test_debug_endpoint_structure():
    """Verify /api/ph/auto/debug returns expected structure."""
    resp = client.get("/api/ph/auto/debug")
    assert resp.status_code == 200
    
    data = resp.json()
    
    # Required keys
    required = ["enabled", "holding_reason", "poll_interval_s", "observe_s", 
                "learned_ml_per_pH", "last_decision"]
    for key in required:
        assert key in data, f"Missing '{key}' in debug response"
    
    # Type checks
    assert isinstance(data["enabled"], bool)
    assert isinstance(data["poll_interval_s"], int)
    assert isinstance(data["observe_s"], int)
    assert isinstance(data["last_decision"], dict)
    
    print(f"✅ Debug endpoint structure valid: enabled={data['enabled']}, "
          f"poll={data['poll_interval_s']}s, observe={data['observe_s']}s")


if __name__ == "__main__":
    # Run tests directly (requires service running)
    print("Running smoke tests...\n")
    try:
        test_status_auto_keys_present()
        test_reset_endpoint_works()
        test_debug_endpoint_structure()
        print("\n✅ All smoke tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        exit(1)
