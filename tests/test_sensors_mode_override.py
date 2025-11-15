"""Tests for sensor mode & overrides endpoints.
Focus: maintenance overrides alter effective values; manual mode sets mode field; clearing overrides restores originals.
"""
import time
import sqlite3
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "rdwc.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            ts INTEGER PRIMARY KEY,
            temp_c REAL,
            ph REAL,
            ec_ms_cm REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    monkeypatch.setenv("RDWC_DB", str(db_file))
    monkeypatch.setenv("RDWC_DB_PATH", str(db_file))
    return str(db_file)

@pytest.fixture
def app_client(temp_db):
    # Insert one reading
    conn = sqlite3.connect(temp_db)
    ts = int(time.time())
    conn.execute("INSERT INTO readings (ts, temp_c, ph, ec_ms_cm) VALUES (?,?,?,?)", (ts, 23.5, 6.10, 1.55))
    conn.commit()
    conn.close()
    from app.main import app
    return TestClient(app)

def test_set_manual_mode(app_client):
    r = app_client.post("/api/sensors/mode", json={"mode":"manual"})
    assert r.status_code == 200
    j = r.json()
    assert j.get("mode") == "manual"
    # GET reflects change
    g = app_client.get("/api/sensors/mode")
    assert g.json().get("mode") == "manual"

def test_maintenance_override_effective_ph(app_client):
    # Set mode maintenance
    app_client.post("/api/sensors/mode", json={"mode":"maintenance"})
    # Apply override (ph only)
    r = app_client.post("/api/sensors/override", json={"ph":5.80})
    assert r.status_code == 200
    # Fetch sensors
    s = app_client.get("/api/sensors")
    assert s.status_code == 200
    data = s.json()
    assert data.get("mode") == "maintenance"
    assert data.get("ph") == pytest.approx(5.80, rel=1e-3)
    # Original should remain 6.10
    assert data.get("original_ph") == pytest.approx(6.10, rel=1e-3)

def test_clear_override_restores_original(app_client):
    app_client.post("/api/sensors/mode", json={"mode":"maintenance"})
    app_client.post("/api/sensors/override", json={"ph":5.70, "temperature_c":22.2})
    s1 = app_client.get("/api/sensors").json()
    assert s1.get("ph") == pytest.approx(5.70, rel=1e-3)
    assert s1.get("temperature_c") == pytest.approx(22.2, rel=1e-3)
    # Clear ph override
    clr = app_client.delete("/api/sensors/override/ph")
    assert clr.status_code == 200
    s2 = app_client.get("/api/sensors").json()
    assert s2.get("ph") == pytest.approx(6.10, rel=1e-3)  # back to original
    # Temperature still overridden
    assert s2.get("temperature_c") == pytest.approx(22.2, rel=1e-3)

def test_overrides_endpoint_age(app_client):
    app_client.post("/api/sensors/mode", json={"mode":"maintenance"})
    app_client.post("/api/sensors/override", json={"ec_mscm":1.99})
    o = app_client.get("/api/sensors/override")
    assert o.status_code == 200
    j = o.json()
    assert "age_seconds" in j
    assert j["overrides"].get("ec_mscm") == pytest.approx(1.99, rel=1e-3)
