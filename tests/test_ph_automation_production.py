"""
Production test suite for pH Up automation
Tests final production behaviors: status fields, EC baseline hold, learning, idempotent toggle, lock, reset endpoint.
"""
import pytest
import sqlite3
import time
from datetime import datetime, timezone, timedelta

# Import app components - defer TestClient creation to avoid version issues
from app.main import app
from app import ph_control

@pytest.fixture(scope="module")
def client():
    """Create TestClient with compatibility for different starlette/httpx versions."""
    try:
        from fastapi.testclient import TestClient
        return TestClient(app)
    except (ImportError, TypeError):
        # Fallback for older versions
        from starlette.testclient import TestClient as StarletteTestClient
        return StarletteTestClient(app)

@pytest.fixture
def db_path(tmp_path):
    """Create temporary database for isolated testing."""
    db_file = tmp_path / "test_rdwc.db"
    ph_control.DB_PATH = db_file
    
    # Also set app.settings DB_PATH so get_setting_key reads from test DB
    from app import settings
    settings.DB_PATH = db_file
    
    # Initialize tables
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                temp_c REAL,
                ph REAL,
                ec_ms_cm REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ph_dose_log(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts_utc TEXT NOT NULL,
              action TEXT NOT NULL,
              volume_ml REAL,
              duration_ms INTEGER,
              pre_ph REAL,
              post_ph REAL,
              result TEXT NOT NULL,
              reason TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
    
    yield db_file
    
    # Cleanup: stop any running automation thread
    try:
        ph_control._auto_enable(False)
        if ph_control._auto_stop_evt:
            ph_control._auto_stop_evt.set()
        time.sleep(0.5)
    except Exception:
        pass


def insert_reading(db_path, ph: float, ec: float, ts: int = None):  # type: ignore
    """Helper to insert a sensor reading."""
    if ts is None:
        ts = int(time.time())
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO readings (ts, temp_c, ph, ec_ms_cm) VALUES (?, ?, ?, ?)",
            (ts, 20.0, ph, ec)
        )
        conn.commit()


def insert_dose_log(db_path, pre_ph: float, post_ph: float, volume_ml: float, ts_utc: str = None):  # type: ignore
    """Helper to insert a dose log entry."""
    if ts_utc is None:
        ts_utc = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO ph_dose_log(ts_utc, action, volume_ml, duration_ms, pre_ph, post_ph, result, reason)
            VALUES(?, 'dose', ?, 2000, ?, ?, 'ok', 'test')
            """,
            (ts_utc, volume_ml, pre_ph, post_ph)
        )
        conn.commit()


def set_setting(db_path, key: str, value: str):
    """Helper to set a setting."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, value))
        conn.commit()


def test_ph_auto_status_fields(db_path, client):
    """Test that /api/ph/status includes auto.enabled, auto.holding_reason, auto.learned_ml_per_pH."""
    # Insert current reading (pH good, EC good)
    insert_reading(db_path, ph=5.9, ec=1.8)
    
    # Ensure auto is disabled
    set_setting(db_path, "ph.auto_enabled", "false")
    
    response = client.get("/api/ph/status")
    assert response.status_code == 200
    data = response.json()
    
    # Check structure
    assert "auto" in data
    assert "enabled" in data["auto"]
    assert "holding_reason" in data["auto"]
    assert "learned_ml_per_pH" in data["auto"]
    
    # Auto disabled
    assert data["auto"]["enabled"] is False
    
    # Learned should be present (default 50.0 when no history)
    assert isinstance(data["auto"]["learned_ml_per_pH"], (int, float))
    
    # Holding reason should be None when pH is in band
    # (or could be None when disabled)


def test_ph_auto_holds_on_ec_baseline_low(db_path, client, monkeypatch):
    """Test that automation holds when EC is below baseline threshold."""
    # Mock relays to avoid GPIO
    def mock_set_dosing_ph_up(state, reason=None, force=False):
        return {"changed": True, "state": state, "reason": reason}
    
    monkeypatch.setattr("app.relays_core.set_dosing_ph_up", mock_set_dosing_ph_up)
    
    # Set EC baseline minimum
    set_setting(db_path, "dosing.ec_baseline_min", "0.2")
    set_setting(db_path, "targets.ph_low", "5.8")
    set_setting(db_path, "general.reservoir_liters", "25")
    
    # Insert reading: pH below band, EC below baseline
    insert_reading(db_path, ph=5.5, ec=0.15)
    
    response = client.get("/api/ph/status")
    assert response.status_code == 200
    data = response.json()
    
    # Check guards
    assert data["guards"]["ec_baseline_low"] is True
    
    # Holding reason should be ec_baseline_low when pH is below and EC is low
    # (if auto were enabled and trying to dose)
    # For status API, holding_reason is derived from current state
    assert data["auto"]["holding_reason"] == "ec_baseline_low"


def test_ph_auto_learning_applied(db_path, client, monkeypatch):
    """Test that learning estimator uses historical doses and is exported in status."""
    # Mock relays
    def mock_set_dosing_ph_up(state, reason=None, force=False):
        return {"changed": True, "state": state, "reason": reason}
    
    monkeypatch.setattr("app.relays_core.set_dosing_ph_up", mock_set_dosing_ph_up)
    
    # Seed valid historical doses
    # Dose 1: 2.0 ml raised pH from 5.7 to 5.9 (ΔpH = 0.2)
    ts1 = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    insert_dose_log(db_path, pre_ph=5.7, post_ph=5.9, volume_ml=2.0, ts_utc=ts1)
    
    # Dose 2: 3.0 ml raised pH from 5.6 to 5.85 (ΔpH = 0.25)
    ts2 = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    insert_dose_log(db_path, pre_ph=5.6, post_ph=5.85, volume_ml=3.0, ts_utc=ts2)
    
    # Insert EC readings near dose times to pass EC baseline filter
    insert_reading(db_path, ph=5.9, ec=1.8, ts=int((datetime.fromisoformat(ts1.replace('Z', '+00:00'))).timestamp()))
    insert_reading(db_path, ph=5.85, ec=1.8, ts=int((datetime.fromisoformat(ts2.replace('Z', '+00:00'))).timestamp()))
    
    # Current reading: pH below band, EC good
    insert_reading(db_path, ph=5.7, ec=1.8)
    
    response = client.get("/api/ph/status")
    assert response.status_code == 200
    data = response.json()
    
    # Learned should be calculated from history
    # Total: 5 ml, Total ΔpH: 0.45 → ~11.1 ml per 1.0 pH
    # Clamped to [5, 100]
    learned = data["auto"]["learned_ml_per_pH"]
    assert isinstance(learned, (int, float))
    assert 5.0 <= learned <= 100.0
    
    # Should be close to calculated value (allow some margin)
    expected = 5.0 / 0.45  # ~11.1
    assert abs(learned - expected) < 2.0


def test_worker_idempotent_toggle(db_path, client, monkeypatch):
    """Test that double-enable creates only one thread, and disable/re-enable works."""
    # Mock relays
    def mock_set_dosing_ph_up(state, reason=None, force=False):
        return {"changed": True, "state": state, "reason": reason}
    
    monkeypatch.setattr("app.relays_core.set_dosing_ph_up", mock_set_dosing_ph_up)
    
    # Current reading
    insert_reading(db_path, ph=5.9, ec=1.8)
    
    # Enable automation
    response1 = client.post("/api/ph/auto", json={"enable": True})
    assert response1.status_code == 200
    assert response1.json()["enabled"] is True
    
    thread1 = ph_control._auto_thread
    assert thread1 is not None
    assert thread1.is_alive()
    
    # Double enable (should return same thread, idempotent)
    response2 = client.post("/api/ph/auto", json={"enable": True})
    assert response2.status_code == 200
    assert response2.json()["enabled"] is True
    thread2 = ph_control._auto_thread
    assert thread2 is thread1  # Same thread instance
    
    # Disable
    response3 = client.post("/api/ph/auto", json={"enable": False})
    assert response3.status_code == 200
    assert response3.json()["enabled"] is False
    
    # Wait briefly for thread to stop
    time.sleep(0.5)
    
    # Re-enable (should start new thread)
    response4 = client.post("/api/ph/auto", json={"enable": True})
    assert response4.status_code == 200
    assert response4.json()["enabled"] is True
    thread4 = ph_control._auto_thread
    assert thread4 is not None
    assert thread4.is_alive()
    
    # Cleanup
    ph_control._auto_enable(False)


def test_nonblocking_lock(db_path, client, monkeypatch):
    """Test that while dose lock is held, auto cycle reports holding (cooldown) and does not double-dose."""
    # Mock relays with artificial delay
    dose_count = {"count": 0}
    
    def mock_set_dosing_ph_up(state, reason=None, force=False):
        if state:
            dose_count["count"] += 1
            time.sleep(0.2)  # Simulate actuation time
        return {"changed": True, "state": state, "reason": reason}
    
    monkeypatch.setattr("app.relays_core.set_dosing_ph_up", mock_set_dosing_ph_up)
    
    # Setup: pH below band, EC good
    set_setting(db_path, "targets.ph_low", "5.8")
    set_setting(db_path, "general.reservoir_liters", "25")
    set_setting(db_path, "dosing.poll_interval_s", "1")  # Fast poll for test
    insert_reading(db_path, ph=5.5, ec=1.8)
    
    # Manually acquire dose lock
    acquired = ph_control._dose_lock.acquire(blocking=False)
    assert acquired
    
    try:
        # Attempt nonblocking dose (should fail with busy)
        response = client.post("/api/ph/dose", json={"ml": 1.0, "reason": "test"})
        # Should return 409 (busy/blocked)
        assert response.status_code == 409
        data = response.json()
        assert data["ok"] is False
        assert data["blocked"] is True
        
        # Dose count should remain 0 (no actuation)
        assert dose_count["count"] == 0
    finally:
        ph_control._dose_lock.release()
    
    # Now dose should succeed
    response2 = client.post("/api/ph/dose", json={"ml": 1.0, "reason": "test"})
    assert response2.status_code == 200
    assert response2.json()["ok"] is True
    assert dose_count["count"] == 1


def test_reset_learner_endpoint(db_path, client):
    """Test that POST /api/ph/auto/learn/reset clears learned value."""
    # Seed dose history
    ts1 = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    insert_dose_log(db_path, pre_ph=5.7, post_ph=5.9, volume_ml=2.0, ts_utc=ts1)
    
    # Insert EC reading
    insert_reading(db_path, ph=5.9, ec=1.8, ts=int((datetime.fromisoformat(ts1.replace('Z', '+00:00'))).timestamp()))
    
    # Current reading
    insert_reading(db_path, ph=5.9, ec=1.8)
    
    # Check learned value exists
    response1 = client.get("/api/ph/status")
    assert response1.status_code == 200
    learned_before = response1.json()["auto"]["learned_ml_per_pH"]
    assert isinstance(learned_before, (int, float))
    
    # Reset learner
    response2 = client.post("/api/ph/auto/learn/reset")
    assert response2.status_code == 200
    data = response2.json()
    assert data["ok"] is True
    assert "message" in data
    
    # Check learned value is now default (no valid post_ph)
    response3 = client.get("/api/ph/status")
    assert response3.status_code == 200
    learned_after = response3.json()["auto"]["learned_ml_per_pH"]
    
    # Should fall back to default (50.0) when no valid samples
    assert learned_after == 50.0


def test_debug_endpoint(db_path, client):
    """Test that GET /api/ph/auto/debug returns expected structure."""
    # Insert reading
    insert_reading(db_path, ph=5.9, ec=1.8)
    
    # Set auto disabled
    set_setting(db_path, "ph.auto_enabled", "false")
    
    response = client.get("/api/ph/auto/debug")
    assert response.status_code == 200
    data = response.json()
    
    # Check structure
    assert "enabled" in data
    assert "holding_reason" in data
    assert "poll_interval_s" in data
    assert "observe_s" in data
    assert "learned_ml_per_pH" in data
    assert "last_decision" in data
    
    # Verify types
    assert isinstance(data["enabled"], bool)
    assert isinstance(data["poll_interval_s"], int)
    assert isinstance(data["observe_s"], int)
    assert isinstance(data["last_decision"], dict)
