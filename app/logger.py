import sqlite3
import os
from .infra.db_writer import log_reading as _db_log_reading

# Legacy compatibility - redirect to singleton db writer
def log_reading(temp_c, ph, ec_ms_cm):
    """Log sensor reading via singleton database writer"""
    _db_log_reading(temp_c, ph, ec_ms_cm)

# Keep read operations direct for now (reads are less problematic)
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rdwc.db")
DB_PATH = os.path.abspath(DB_PATH)

def last_n(n=200):
    """Get last n readings (read-only operation)"""
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as c:
            cur = c.execute("SELECT ts,temp_c,ph,ec_ms_cm FROM readings ORDER BY ts DESC LIMIT ?", (n,))
            rows = [{"ts": r[0], "temp_c": r[1], "ph": r[2], "ec_ms_cm": r[3]} for r in cur.fetchall()]
        return rows[::-1]  # chronological
    except sqlite3.Error:
        return []  # Return empty list on error

def fetch_history_since(since_ts: int):
    """Fetch readings since given timestamp"""
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as c:
            cur = c.execute(
                "SELECT ts,temp_c,ph,ec_ms_cm FROM readings WHERE ts >= ? ORDER BY ts ASC", 
                (since_ts,)
            )
            return [{"ts": r[0], "temp_c": r[1], "ph": r[2], "ec_ms_cm": r[3]} for r in cur.fetchall()]
    except sqlite3.Error:
        return []