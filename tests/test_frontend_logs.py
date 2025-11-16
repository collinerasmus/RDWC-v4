"""
Test frontend error logging endpoints
"""
import os
import tempfile
import time
from fastapi.testclient import TestClient


def test_frontend_log_creation_and_retrieval(monkeypatch):
    """Test that frontend logs can be created and retrieved."""
    # Use temp DB
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db = f.name
    
    monkeypatch.setenv("RDWC_DB", test_db)
    
    try:
        from app.main import app
        client = TestClient(app)
        
        # Post some frontend logs
        now_ts = int(time.time())
        payload = {
            "logs": [
                {
                    "ts": now_ts,
                    "level": "error",
                    "message": "Test error from browser",
                    "stack": "Error: Test error\n  at test.js:10:5",
                    "url": "http://localhost:8080/static/js/test.js",
                    "line_number": 10,
                    "column_number": 5,
                    "user_agent": "Mozilla/5.0 Test",
                    "page_url": "http://localhost:8080/",
                    "metadata": None
                },
                {
                    "ts": now_ts - 10,
                    "level": "warn",
                    "message": "Test warning",
                    "stack": None,
                    "url": None,
                    "line_number": None,
                    "column_number": None,
                    "user_agent": "Mozilla/5.0 Test",
                    "page_url": "http://localhost:8080/",
                    "metadata": '{"foo": "bar"}'
                }
            ]
        }
        
        # POST logs
        response = client.post("/api/frontend/log", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["received"] == 2
        
        # GET logs
        response = client.get("/api/frontend/logs?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["logs"]) == 2
        
        # Verify error log
        error_log = next(log for log in data["logs"] if log["level"] == "error")
        assert error_log["message"] == "Test error from browser"
        assert error_log["stack"] == "Error: Test error\n  at test.js:10:5"
        assert error_log["line_number"] == 10
        
        # Filter by level
        response = client.get("/api/frontend/logs?level=error&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["logs"][0]["level"] == "error"
        
        # DELETE old logs (should delete nothing with default 7 days)
        response = client.delete("/api/frontend/logs?older_than_hours=168")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] == 0
        
        # DELETE all logs (0 hours = everything)
        response = client.delete("/api/frontend/logs?older_than_hours=0")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] == 2
        
        # Verify empty
        response = client.get("/api/frontend/logs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        
    finally:
        os.unlink(test_db)


def test_frontend_log_invalid_payload():
    """Test error handling for invalid payloads."""
    from app.main import app
    client = TestClient(app)
    
    # Missing logs array
    response = client.post("/api/frontend/log", json={})
    assert response.status_code == 400
    
    # Invalid logs type
    response = client.post("/api/frontend/log", json={"logs": "not an array"})
    assert response.status_code == 400
