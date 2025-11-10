"""
Sensors fallback service - provides last known reading when live sensors offline.
"""
from __future__ import annotations
import sqlite3
import os
import datetime as dt

# Align with main.py DB path logic (RDWC_DB env or ../data/rdwc.db)
DB_PATH = os.environ.get(
    "RDWC_DB",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "rdwc.db"))
)

def _row_to_out(row):
    import time
    if not row:
        return None
    ts = row["ts"]
    if isinstance(ts, (int, float)):  # epoch
        ts_iso = dt.datetime.utcfromtimestamp(ts).isoformat() + "Z"
        # Use time.time() for consistent UTC epoch comparison
        age = max(0, int(time.time() - ts))
    else:
        # assume ISO8601
        ts_iso = str(ts)
        try:
            age = int((dt.datetime.utcnow() - dt.datetime.fromisoformat(ts.replace("Z", ""))).total_seconds())
        except Exception:
            age = None
    return {
        "temperature_c": row.get("temp") or row.get("temperature_c") or row.get("temp_c"),
        "ec_mscm": row.get("ec_mscm") or row.get("ec") or row.get("ec_ms_cm"),
        "ph": row.get("ph"),
        "ts": ts_iso,
        "stale_seconds": age,
        "online": False,
        "temp_comp_applied": False,
        "temp_comp_reason": "fallback",
    }

def get_last_reading():
    """
    Try to fetch the most recent sensor reading from the database.
    Attempts multiple table schemas (readings, sensor_log, metrics).
    Returns dict with stale_seconds tag or None if no data found.
    """
    # Try to reuse whatever table trends uses.
    # We attempt a few common schemas and return the first hit.
    candidates = [
        ("readings",   "SELECT ts, temp_c, ec_ms_cm, ph FROM readings ORDER BY ts DESC LIMIT 1"),
        ("metrics",    "SELECT ts, temperature_c as temp_c, ec_mscm as ec_ms_cm, ph FROM metrics ORDER BY ts DESC LIMIT 1"),
        ("sensor_log", "SELECT ts, temp as temp_c, ec_mscm as ec_ms_cm, ph FROM sensor_log ORDER BY ts DESC LIMIT 1"),
    ]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        for _, q in candidates:
            try:
                row = cur.execute(q).fetchone()
                if row:
                    return _row_to_out(dict(row))
            except Exception:
                continue
        return None
    finally:
        conn.close()
