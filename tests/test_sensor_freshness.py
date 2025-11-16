"""
Test sensor freshness & health indicators in /api/sensors endpoint.
Scenarios: A) recent (age=0, green), B) 120s aged (stale, yellow), C) 400s aged (stale, red).
"""
import pytest
import sqlite3
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset app.main cache before each test."""
    import app.main as main_module
    main_module._last = {}
    main_module._last_t = 0.0
    yield


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create temporary test database with schema."""
    db_file = tmp_path / "test_rdwc.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            temp_c REAL,
            ph REAL,
            ec_ms_cm REAL
        )
    """)
    conn.commit()
    conn.close()
    
    # Patch RDWC_DB env var to use test DB
    monkeypatch.setenv("RDWC_DB", str(db_file))
    
    # Also patch the sensors_fallback.py DB_PATH
    import app.services.sensors_fallback
    app.services.sensors_fallback.DB_PATH = str(db_file)
    
    yield str(db_file)


def insert_reading(db_path: str, age_seconds: float):
    """Insert sensor reading with specified age."""
    import time
    ts = int(time.time() - age_seconds)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO readings (ts, temp_c, ph, ec_ms_cm) VALUES (?, ?, ?, ?)",
        (ts, 23.5, 6.1, 310.0)
    )
    conn.commit()
    conn.close()


def test_sensor_freshness_recent(test_db):
    """Scenario A: Recent reading (age=0s) should be green and not stale."""
    from app.main import app
    
    insert_reading(test_db, age_seconds=0)
    
    client = TestClient(app)
    response = client.get("/api/sensors")
    
    assert response.status_code == 200
    data = response.json()
    
    # Validate freshness fields
    assert "age_seconds" in data
    assert "stale" in data
    assert "health_state" in data
    
    assert data["age_seconds"] < 60, f"Expected age <60s, got {data['age_seconds']}"
    assert data["stale"] is False, "Recent reading should not be stale"
    assert data["health_state"] == "green", f"Expected green, got {data['health_state']}"
    assert data["online"] is True, "Recent reading should be online"


def test_sensor_freshness_120s_aged(test_db):
    """Scenario B: 120s aged reading should be yellow (stale but <300s)."""
    from app.main import app
    
    insert_reading(test_db, age_seconds=120)
    
    client = TestClient(app)
    response = client.get("/api/sensors")
    
    assert response.status_code == 200
    data = response.json()
    
    # Validate freshness fields
    assert data["age_seconds"] >= 60, f"Expected age >=60s, got {data['age_seconds']}"
    assert data["stale"] is True, "120s aged reading should be stale"
    # online flag uses 60s threshold, so 120s = offline
    assert data["online"] is False, "120s aged should be offline (>60s threshold)"
    # health_state should be yellow for 60-300s range (stale but not too old)
    assert data["health_state"] == "yellow", f"Expected yellow (60-300s), got {data['health_state']}"


def test_sensor_freshness_400s_aged(test_db):
    """Scenario C: 400s aged reading should be red (stale and >=300s)."""
    from app.main import app
    
    insert_reading(test_db, age_seconds=400)
    
    client = TestClient(app)
    response = client.get("/api/sensors")
    
    assert response.status_code == 200
    data = response.json()
    
    # Validate freshness fields
    assert data["age_seconds"] >= 300, f"Expected age >=300s, got {data['age_seconds']}"
    assert data["stale"] is True, "400s aged reading should be stale"
    assert data["health_state"] == "red", f"Expected red, got {data['health_state']}"
    assert data["online"] is False, "400s aged should be offline"
