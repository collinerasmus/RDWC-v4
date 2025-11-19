from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_chiller_events_endpoint_exists_and_shape():
    resp = client.get("/api/chiller/events")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "count" in data
    assert isinstance(data["events"], list)
    # Shape check if any events
    if data["events"]:
        ev = data["events"][0]
        assert set(["ts_utc", "prev_state", "new_state", "reason"]).issubset(ev.keys())


def test_chiller_events_limit_param():
    # Just verify limit parameter is accepted; content may be empty in CI
    resp = client.get("/api/chiller/events?limit=5")
    assert resp.status_code == 200


def test_chiller_events_ordering_newest_first():
    # Attempt to generate a couple of events by toggling relay through control module
    # This test remains resilient if hardware mocks prevent actual toggles.
    try:
        from app.chiller_control import set_chiller_relay
        set_chiller_relay(False, "test-reset-off")
        set_chiller_relay(True, "test-on")
        set_chiller_relay(False, "test-off")
    except Exception:
        pass

    resp = client.get("/api/chiller/events?limit=10")
    assert resp.status_code == 200
    events = resp.json().get("events", [])
    # Ensure monotonic non-increasing by ts_utc if there are at least two events
    if len(events) >= 2:
        ts_vals = [e.get("ts_utc", 0) for e in events]
        assert all(ts_vals[i] >= ts_vals[i+1] for i in range(len(ts_vals)-1))
