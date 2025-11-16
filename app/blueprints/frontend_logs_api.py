"""
Frontend Logging API
Captures browser console errors and logs for debugging
"""
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/frontend", tags=["frontend"])

DB_PATH = os.environ.get("RDWC_DB", "data/rdwc.db")

def _get_db():
    """Get database connection with frontend_logs table initialized."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Auto-create table if missing
    conn.execute("""
        CREATE TABLE IF NOT EXISTS frontend_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            level TEXT NOT NULL CHECK(level IN ('error', 'warn', 'info', 'debug')),
            message TEXT NOT NULL,
            stack TEXT,
            url TEXT,
            line_number INTEGER,
            column_number INTEGER,
            user_agent TEXT,
            page_url TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frontend_logs_ts ON frontend_logs(ts DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frontend_logs_level ON frontend_logs(level)")
    conn.commit()
    
    return conn


@router.post("/log")
async def log_frontend_errors(payload: dict = Body(...)):
    """
    POST /api/frontend/log
    Receive browser error logs and store them in database.
    
    Payload: { logs: [ { ts, level, message, stack?, url?, ... } ] }
    """
    logs = payload.get("logs", [])
    if not logs or not isinstance(logs, list):
        return JSONResponse({"error": "logs array required"}, status_code=400)
    
    try:
        conn = _get_db()
        cursor = conn.cursor()
        
        for log in logs:
            cursor.execute("""
                INSERT INTO frontend_logs 
                (ts, level, message, stack, url, line_number, column_number, 
                 user_agent, page_url, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log.get("ts"),
                log.get("level", "info"),
                log.get("message", ""),
                log.get("stack"),
                log.get("url"),
                log.get("line_number"),
                log.get("column_number"),
                log.get("user_agent"),
                log.get("page_url"),
                log.get("metadata")
            ))
        
        conn.commit()
        conn.close()
        
        return {"ok": True, "received": len(logs)}
    
    except Exception as e:
        logger.error(f"Failed to store frontend logs: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/logs")
async def get_frontend_logs(
    level: Optional[str] = None,
    limit: int = 100,
    hours: int = 24
):
    """
    GET /api/frontend/logs?level=error&limit=50&hours=24
    Retrieve frontend error logs for debugging.
    
    Query params:
    - level: Filter by error level (error, warn, info, debug)
    - limit: Max number of logs to return (default 100, max 500)
    - hours: Look back this many hours (default 24)
    
    Returns: { logs: [ { id, ts, level, message, stack, ... } ], total: N }
    """
    try:
        limit = min(max(1, limit), 500)  # Clamp 1-500
        hours = max(1, hours)
        
        cutoff_ts = int((datetime.utcnow() - timedelta(hours=hours)).timestamp())
        
        conn = _get_db()
        cursor = conn.cursor()
        
        query = "SELECT * FROM frontend_logs WHERE ts >= ?"
        params = [cutoff_ts]
        
        if level:
            query += " AND level = ?"
            params.append(level)
        
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        
        rows = cursor.execute(query, params).fetchall()
        
        # Get total count
        count_query = "SELECT COUNT(*) FROM frontend_logs WHERE ts >= ?"
        count_params = [cutoff_ts]
        if level:
            count_query += " AND level = ?"
            count_params.append(level)
        
        total = cursor.execute(count_query, count_params).fetchone()[0]
        
        conn.close()
        
        logs = [dict(row) for row in rows]
        
        return {"logs": logs, "total": total, "limit": limit, "hours": hours}
    
    except Exception as e:
        logger.error(f"Failed to retrieve frontend logs: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/logs")
async def clear_frontend_logs(older_than_hours: int = 168):  # Default 7 days
    """
    DELETE /api/frontend/logs?older_than_hours=168
    Clear old frontend logs to prevent database bloat.
    
    Query params:
    - older_than_hours: Delete logs older than this (default 168 = 7 days)
                        Use 0 to delete all logs
    
    Returns: { deleted: N }
    """
    try:
        if older_than_hours == 0:
            # Delete all logs
            conn = _get_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM frontend_logs")
            deleted = cursor.rowcount
        else:
            cutoff_ts = int((datetime.utcnow() - timedelta(hours=older_than_hours)).timestamp())
            
            conn = _get_db()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM frontend_logs WHERE ts < ?", (cutoff_ts,))
            deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return {"ok": True, "deleted": deleted, "older_than_hours": older_than_hours}
    
    except Exception as e:
        logger.error(f"Failed to clear frontend logs: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)
