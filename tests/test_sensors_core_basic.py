"""
Basic tests for sensors_core module focusing on pure functions.
Covers temperature compensation throttling logic and DB read utilities.
"""
import time
import sqlite3
import tempfile
from pathlib import Path


def test_should_send_temp_comp_first_time():
    """First temp comp call should always send (no cached value)."""
    import app.sensors_core as sc
    # Reset global state
    sc._last_t_sent_c = None
    sc._last_t_set_ts = 0.0
    
    should_send, delta = sc._should_send_temp_comp(23.0)
    assert should_send is True
    assert delta == 0.0


def test_should_send_temp_comp_large_delta():
    """Temperature change >= 0.2°C should trigger send."""
    import app.sensors_core as sc
    sc._last_t_sent_c = 23.0
    sc._last_t_set_ts = time.time()
    
    # Test delta = 0.3°C (above threshold)
    should_send, delta = sc._should_send_temp_comp(23.3)
    assert should_send is True
    assert abs(delta - 0.3) < 0.001  # Allow float precision variance


def test_should_send_temp_comp_small_delta_recent():
    """Small temperature change with recent update should NOT send."""
    import app.sensors_core as sc
    sc._last_t_sent_c = 23.0
    sc._last_t_set_ts = time.time()  # Just now
    
    # Test delta = 0.1°C (below threshold)
    should_send, delta = sc._should_send_temp_comp(23.1)
    assert should_send is False
    assert abs(delta - 0.1) < 0.001


def test_should_send_temp_comp_time_elapsed():
    """Time elapsed >= 60s should trigger send even with small delta."""
    import app.sensors_core as sc
    sc._last_t_sent_c = 23.0
    sc._last_t_set_ts = time.time() - 61.0  # 61 seconds ago
    
    # Small delta but time threshold exceeded
    should_send, delta = sc._should_send_temp_comp(23.05)
    assert should_send is True
    assert abs(delta - 0.05) < 0.001


def test_update_temp_comp_cache():
    """Verify temp comp cache is updated correctly."""
    import app.sensors_core as sc
    before = time.time()
    sc._update_temp_comp_cache(24.5)
    after = time.time()
    
    assert sc._last_t_sent_c == 24.5
    assert before <= sc._last_t_set_ts <= after


def test_get_last_temp_comp_state():
    """Verify diagnostics function returns correct state."""
    import app.sensors_core as sc
    sc._last_t_sent_c = 22.5
    sc._last_t_set_ts = time.time() - 10.0
    
    state = sc.get_last_temp_comp_state()
    assert state["last_t_sent_c"] == 22.5
    assert 9.5 <= state["time_since_last"] <= 10.5  # Allow some timing variance


def test_read_sensors_from_db_no_file():
    """DB read should return error if database doesn't exist."""
    import app.sensors_core as sc
    result = sc.read_sensors_from_db(db_path="/nonexistent/path.db")
    
    assert result["online"] is False
    assert result["temperature_c"] is None
    assert "db" in result["errors"]
    assert "not found" in result["errors"]["db"]


def test_read_sensors_from_db_empty():
    """DB read should return error if no readings exist."""
    import app.sensors_core as sc
    
    # Create empty DB
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    tmp_path = Path(tmp.name)
    
    try:
        conn = sqlite3.connect(str(tmp_path))
        conn.execute("""
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
        
        result = sc.read_sensors_from_db(db_path=str(tmp_path))
        assert result["online"] is False
        assert "no readings found" in result["errors"]["db"]
    finally:
        tmp_path.unlink()


def test_read_sensors_from_db_recent():
    """DB read with recent data should return online=True."""
    import app.sensors_core as sc
    
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    tmp_path = Path(tmp.name)
    
    try:
        conn = sqlite3.connect(str(tmp_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY,
                ts INTEGER NOT NULL,
                temp_c REAL,
                ph REAL,
                ec_ms_cm REAL
            )
        """)
        # Insert recent reading (5 seconds ago)
        now_ts = int(time.time()) - 5
        conn.execute(
            "INSERT INTO readings (ts, temp_c, ph, ec_ms_cm) VALUES (?, ?, ?, ?)",
            (now_ts, 23.5, 6.2, 1.45)
        )
        conn.commit()
        conn.close()
        
        result = sc.read_sensors_from_db(db_path=str(tmp_path), max_age_sec=60)
        assert result["online"] is True
        assert result["temperature_c"] == 23.5
        assert result["ph"] == 6.2
        assert result["ec_mscm"] == 1.45
        assert result["age_sec"] >= 5
        assert result["errors"] == {}
    finally:
        tmp_path.unlink()


def test_read_sensors_from_db_stale():
    """DB read with stale data should return online=False."""
    import app.sensors_core as sc
    
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    tmp_path = Path(tmp.name)
    
    try:
        conn = sqlite3.connect(str(tmp_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY,
                ts INTEGER NOT NULL,
                temp_c REAL,
                ph REAL,
                ec_ms_cm REAL
            )
        """)
        # Insert stale reading (120 seconds ago)
        stale_ts = int(time.time()) - 120
        conn.execute(
            "INSERT INTO readings (ts, temp_c, ph, ec_ms_cm) VALUES (?, ?, ?, ?)",
            (stale_ts, 22.0, 5.8, 1.2)
        )
        conn.commit()
        conn.close()
        
        result = sc.read_sensors_from_db(db_path=str(tmp_path), max_age_sec=60)
        assert result["online"] is False
        assert result["age_sec"] >= 120
        assert "stale" in result["errors"]
    finally:
        tmp_path.unlink()
