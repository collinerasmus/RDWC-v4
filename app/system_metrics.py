"""
System metrics collection and management.
Captures Pi CPU, memory, disk, voltage, network, load every 60s.
Persists to SQLite with 7-day auto-purge.
"""
import time
import sqlite3
import os
import psutil
from typing import Optional
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from app.db_pool import get_conn

DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

# Sampling interval in seconds
SAMPLE_INTERVAL_S = 60

# Retention period in days
RETENTION_DAYS = 7

def init_system_metrics_table():
    """Create system_metrics table if not exists."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_metrics (
            ts INTEGER PRIMARY KEY,
            cpu_percent REAL,
            memory_percent REAL,
            disk_percent REAL,
            core_voltage_v REAL,
            load_1m REAL,
            load_5m REAL,
            load_15m REAL,
            net_rx_bytes INTEGER,
            net_tx_bytes INTEGER
        )
    """)
    # Create index for faster range queries
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_system_metrics_ts ON system_metrics(ts)
    """)
    conn.commit()

def purge_old_metrics():
    """Remove system metrics older than RETENTION_DAYS."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cutoff_ts = int((time.time() - RETENTION_DAYS * 86400))
        cur.execute("DELETE FROM system_metrics WHERE ts < ?", (cutoff_ts,))
        conn.commit()
    except Exception as e:
        # Graceful; don't crash if purge fails
        pass

def collect_metrics():
    """Collect current system metrics; return dict or None on error."""
    try:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Load average
        load = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)
        
        # Core voltage
        core_v = None
        try:
            vres = subprocess.run(["vcgencmd", "measure_volts"], capture_output=True, text=True, timeout=2)
            if vres.returncode == 0 and "volt=" in vres.stdout:
                out = vres.stdout.strip()
                try:
                    core_v = float(out.split("=")[1].replace("V", ""))
                except Exception:
                    core_v = None
        except Exception:
            core_v = None
        
        # Network stats (aggregate across all interfaces)
        net_rx = 0
        net_tx = 0
        try:
            stats = psutil.net_io_counters()
            net_rx = stats.bytes_recv
            net_tx = stats.bytes_sent
        except Exception:
            pass
        
        return {
            "ts": int(time.time()),
            "cpu_percent": round(cpu_pct, 1),
            "memory_percent": round(mem.percent, 1),
            "disk_percent": round(disk.percent, 1),
            "core_voltage_v": core_v,
            "load_1m": round(load[0], 2) if load[0] is not None else None,
            "load_5m": round(load[1], 2) if load[1] is not None else None,
            "load_15m": round(load[2], 2) if load[2] is not None else None,
            "net_rx_bytes": net_rx,
            "net_tx_bytes": net_tx
        }
    except Exception as e:
        return None

def store_metrics(metrics):
    """Store metrics dict to database."""
    if not metrics:
        return
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO system_metrics 
            (ts, cpu_percent, memory_percent, disk_percent, core_voltage_v, load_1m, load_5m, load_15m, net_rx_bytes, net_tx_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metrics["ts"],
            metrics["cpu_percent"],
            metrics["memory_percent"],
            metrics["disk_percent"],
            metrics["core_voltage_v"],
            metrics["load_1m"],
            metrics["load_5m"],
            metrics["load_15m"],
            metrics["net_rx_bytes"],
            metrics["net_tx_bytes"]
        ))
        conn.commit()
    except Exception as e:
        pass  # Graceful; don't crash on store failure

_last_sample_ts = None  # type: Optional[float]

def sample_and_store():
    """Collect metrics and store; enforce SAMPLE_INTERVAL_S cadence."""
    global _last_sample_ts
    now = time.time()
    if _last_sample_ts is not None and (now - _last_sample_ts) < SAMPLE_INTERVAL_S:
        return
    metrics = collect_metrics()
    if metrics:
        store_metrics(metrics)
        _last_sample_ts = now
    # Purge old data periodically (~ every 1000 seconds)
    if int(now) % 1000 == 0:
        purge_old_metrics()

def get_metrics_history(metric_names, hours=24):
    """
    Retrieve metrics history for given metric names over past N hours.
    
    Args:
        metric_names: list of column names (e.g., ['cpu_percent', 'memory_percent'])
        hours: lookback period in hours
    
    Returns:
        list of dicts with ts and requested metrics
    """
    try:
        conn = get_conn(readonly=True)
        cur = conn.cursor()
        
        cutoff_ts = int(time.time() - hours * 3600)
        
        # Validate column names (basic safety)
        allowed = {
            'cpu_percent', 'memory_percent', 'disk_percent', 'core_voltage_v',
            'load_1m', 'load_5m', 'load_15m', 'net_rx_bytes', 'net_tx_bytes'
        }
        safe_names = [n for n in metric_names if n in allowed]
        if not safe_names:
            return []
        
        # Build query
        cols = ", ".join(["ts"] + safe_names)
        query = f"SELECT {cols} FROM system_metrics WHERE ts >= ? ORDER BY ts ASC"
        
        cur.execute(query, (cutoff_ts,))
        rows = cur.fetchall()
        
        # Convert to list of dicts
        result = []
        for row in rows:
            record = {"ts": row[0]}
            for i, name in enumerate(safe_names, 1):
                record[name] = row[i]
            result.append(record)
        
        return result
    except Exception as e:
        return []

# Module-level init on import
try:
    init_system_metrics_table()
except Exception:
    pass  # Table may already exist
