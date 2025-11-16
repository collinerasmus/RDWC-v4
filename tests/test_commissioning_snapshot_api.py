"""Test the commissioning snapshot API endpoint."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_commissioning_snapshot_basic():
    r = client.get("/api/commissioning/snapshot")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    # Key presence
    for key in ["relay_estop", "relay_count", "sensors_online", "pump_count", "pumps", "ts"]:
        assert key in data
    assert isinstance(data["pumps"], list)
    # pumps list should contain dicts with keys
    if data["pumps"]:
        sample = data["pumps"][0]
        for k in ["key", "relay", "ml_per_sec"]:
            assert k in sample
