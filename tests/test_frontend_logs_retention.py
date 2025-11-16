"""Tests for frontend logs retention trimming logic"""
import os
import tempfile
import time
from fastapi.testclient import TestClient


def _make_client(monkeypatch, retention_days=7, max_rows=5000):
    # Use temp DB per test
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db = f.name
    monkeypatch.setenv("RDWC_DB", test_db)
    monkeypatch.setenv("FRONTEND_LOG_RETENTION_DAYS", str(retention_days))
    monkeypatch.setenv("FRONTEND_LOG_MAX_ROWS", str(max_rows))
    from app.main import app
    client = TestClient(app)
    return client, test_db


def test_trim_by_age(monkeypatch):
    # Set high retention initially (30 days) so auto-trim on ingest doesn't delete the old log yet
    client, db_path = _make_client(monkeypatch, retention_days=30, max_rows=5000)
    try:
        now = int(time.time())
        old_ts = now - (10 * 24 * 3600)  # 10 days old
        payload = {
            "logs": [
                {"ts": old_ts, "level": "error", "message": "old-log", "stack": None,
                 "url": None, "line_number": None, "column_number": None,
                 "user_agent": "UA", "page_url": "/", "metadata": None},
                {"ts": now, "level": "error", "message": "new-log", "stack": None,
                 "url": None, "line_number": None, "column_number": None,
                 "user_agent": "UA", "page_url": "/", "metadata": None},
            ]
        }
        r = client.post("/api/frontend/log", json=payload)
        assert r.status_code == 200
        # Old log may already be trimmed if blueprint imported earlier with default retention; proceed regardless
        # Force trim with retention_days override = 7 (should ensure old 10-day log absent)
        r = client.post("/api/frontend/logs/trim?retention_days=7&max_rows=5000")
        assert r.status_code == 200
        stats = r.json()["stats"]
        assert stats["final_count"] == 1
        # Verify remaining log is the new one
        r = client.get("/api/frontend/logs?limit=10&hours=240")  # large hour window
        logs = r.json()["logs"]
        assert len(logs) == 1
        assert logs[0]["message"] == "new-log"
    finally:
        os.unlink(db_path)


def test_trim_by_row_cap(monkeypatch):
    # Start with generous cap so ingest doesn't trim; then enforce smaller cap manually
    client, db_path = _make_client(monkeypatch, retention_days=0, max_rows=100)  # disable age trimming
    try:
        now = int(time.time())
        logs = []
        # Create 15 logs with increasing timestamps (oldest first)
        for i in range(15):
            logs.append({
                "ts": now + i,  # ensure strictly increasing
                "level": "error" if i % 2 == 0 else "warn",
                "message": f"log-{i}",
                "stack": None,
                "url": None,
                "line_number": None,
                "column_number": None,
                "user_agent": "UA",
                "page_url": "/",
                "metadata": None
            })
        r = client.post("/api/frontend/log", json={"logs": logs})
        assert r.status_code == 200
        ingest = r.json()
        assert ingest["received"] == 15
        # No trimming should have occurred due to high max_rows
        # Force trim with max_rows=10
        r = client.post("/api/frontend/logs/trim?retention_days=0&max_rows=10")
        assert r.status_code == 200
        stats = r.json()["stats"]
        assert stats["final_count"] == 10
        # Fetch logs and ensure we kept the newest 10 (log-5 .. log-14)
        r = client.get("/api/frontend/logs?limit=50&hours=240")
        fetched = r.json()["logs"]
        messages = {log_entry["message"] for log_entry in fetched}
        assert "log-0" not in messages
        assert "log-4" not in messages
        for i in range(5, 15):
            assert f"log-{i}" in messages
    finally:
        os.unlink(db_path)
