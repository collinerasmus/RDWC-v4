"""Test relay endpoint performance and timeout issues."""
import time
from fastapi.testclient import TestClient
from app.main import app


def test_relay_set_post_performance():
    """Test that /relay/set POST responds quickly (under 2 seconds)."""
    client = TestClient(app)
    
    # Test a simple relay set operation
    start = time.time()
    response = client.post("/relay/set", json={"name": "dosing_grow", "on": False})
    elapsed = time.time() - start
    
    # Should respond in under 2 seconds
    assert elapsed < 2.0, f"POST /relay/set took {elapsed:.3f}s (expected < 2.0s)"
    
    # Should succeed
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    result = response.json()
    assert "ok" in result
    assert result["ok"] is True


def test_relay_set_multiple_fast():
    """Test multiple rapid relay set operations."""
    client = TestClient(app)
    
    timings = []
    for _ in range(5):
        start = time.time()
        response = client.post("/relay/set", json={"name": "dosing_grow", "on": False})
        elapsed = time.time() - start
        timings.append(elapsed)
        
        assert response.status_code == 200
        result = response.json()
        assert result["ok"] is True
    
    # All should be fast
    max_time = max(timings)
    avg_time = sum(timings) / len(timings)
    
    assert max_time < 1.0, f"Slowest request took {max_time:.3f}s (expected < 1.0s)"
    assert avg_time < 0.5, f"Average request took {avg_time:.3f}s (expected < 0.5s)"


def test_relay_set_with_mode_check():
    """Test relay set with mode checking (circulation controller)."""
    client = TestClient(app)
    
    # Set circulation to manual mode
    client.post("/api/modes/set", json={"controller": "circulation", "mode": "manual"})
    
    # Test main_pump set (should work with override)
    start = time.time()
    response = client.post("/relay/set", json={"name": "main_pump", "on": False})
    elapsed = time.time() - start
    
    assert elapsed < 2.0, f"POST /relay/set with mode check took {elapsed:.3f}s"
    assert response.status_code == 200


def test_middleware_body_consumption():
    """Test that middleware doesn't cause double body consumption issues."""
    client = TestClient(app)
    
    # Large-ish body to test body handling
    body = {"name": "dosing_grow", "on": True, "extra_data": "x" * 1000}
    
    start = time.time()
    response = client.post("/relay/set", json=body)
    elapsed = time.time() - start
    
    assert response.status_code == 200
    assert elapsed < 2.0, f"Request with larger body took {elapsed:.3f}s"
    
    result = response.json()
    assert result["ok"] is True


def test_invalid_relay_name_fast():
    """Test that invalid relay name fails fast."""
    client = TestClient(app)
    
    start = time.time()
    response = client.post("/relay/set", json={"name": "invalid_relay_xyz", "on": True})
    elapsed = time.time() - start
    
    # Should fail fast (validation error)
    assert elapsed < 0.5, f"Invalid relay check took {elapsed:.3f}s"
    assert response.status_code == 400
    result = response.json()
    assert "error" in result
