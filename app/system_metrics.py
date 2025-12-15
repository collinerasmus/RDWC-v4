import os
import time
import sqlite3
import subprocess
from typing import Dict, Any, List
from datetime import datetime, timedelta

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # fallback handled at call site

DB_PATH = os.environ.get("RDWC_DB", os.path.join(os.path.dirname(__file__), "..", "data", "rdwc.db"))
DB_PATH = os.path.abspath(DB_PATH)

_last_sample_ts = 0.0  # Guard 60s cadence

def _read_core_voltage() -> float | None:
    """Read Raspberry Pi core voltage via vcgencmd if available.
    Returns volts as float or None if unavailable.
    """
    try:
        proc = subprocess.run(["vcgencmd", "measure_volts", "core"], capture_output=True, text=True, check=False)
        out = (proc.stdout or "").strip()
        # Example: "volt=0.8625V"
        if "volt=" in out and out.endswith("V"):
            val = out.split("volt=")[-1].rstrip("V").strip()
            return float(val)
    except Exception:
        return None
    return None


def collect_current_metrics() -> Dict[str, Any]:
    """Collect a single snapshot of system metrics.
    Safe: all calls wrapped and tolerant to missing psutil/vcgencmd.
    """
    ts = int(time.time())
    data: Dict[str, Any] = {
        "ts": ts,
        "cpu_percent": None,
        "memory_percent": None,
        "disk_percent": None,
        "core_voltage_v": None,
        "load_1m": None,
        "load_5m": None,
        "load_15m": None,
        "net_rx_bytes": None,
        "net_tx_bytes": None,
    }

    if psutil is not None:
        try:
            data["cpu_percent"] = float(psutil.cpu_percent(interval=None))
        except Exception:
            pass
        try:
            vm = psutil.virtual_memory()
            data["memory_percent"] = float(vm.percent)
        except Exception:
            pass
        try:
            du = psutil.disk_usage("/")
            data["disk_percent"] = float(du.percent)
        except Exception:
            pass
        try:
            nic = psutil.net_io_counters(pernic=False)
            data["net_rx_bytes"] = int(getattr(nic, "bytes_recv", 0))
            data["net_tx_bytes"] = int(getattr(nic, "bytes_sent", 0))
        except Exception:
            pass
    # Load averages (Linux)
    try:
        load1, load5, load15 = os.getloadavg()  # type: ignore[attr-defined]
        data["load_1m"], data["load_5m"], data["load_15m"] = float(load1), float(load5), float(load15)
    except Exception:
        pass
    # Core voltage
    v = _read_core_voltage()
    if v is not None:
        data["core_voltage_v"] = v

    return data


def init_system_metrics_table():
    """Create system_metrics table if it doesn't exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
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
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[system_metrics] init_system_metrics_table error: {e}")


def store_metrics(data: Dict[str, Any]):
    """Insert metrics snapshot into database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO system_metrics
            (ts, cpu_percent, memory_percent, disk_percent, core_voltage_v,
             load_1m, load_5m, load_15m, net_rx_bytes, net_tx_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("ts"),
            data.get("cpu_percent"),
            data.get("memory_percent"),
            data.get("disk_percent"),
            data.get("core_voltage_v"),
            data.get("load_1m"),
            data.get("load_5m"),
            data.get("load_15m"),
            data.get("net_rx_bytes"),
            data.get("net_tx_bytes"),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[system_metrics] store_metrics error: {e}")


def sample_and_store() -> bool:
    """Collect and store metrics if 60s have passed since last sample.
    Returns True if stored, False if skipped (cadence guard).
    """
    global _last_sample_ts
    now = time.time()
    if now - _last_sample_ts < 60:
        return False
    _last_sample_ts = now
    data = collect_current_metrics()
    store_metrics(data)
    return True


def purge_old_metrics(days: int = 7):
    """Delete metrics older than N days."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cutoff_ts = int(time.time()) - (days * 86400)
        conn.execute("DELETE FROM system_metrics WHERE ts < ?", (cutoff_ts,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[system_metrics] purge_old_metrics error: {e}")


def get_metrics_history(start_ts: int, end_ts: int, metrics: List[str] | None = None) -> List[Dict[str, Any]]:
    """Query metrics within time range.
    
    Args:
        start_ts: Unix timestamp (seconds)
        end_ts: Unix timestamp (seconds)
        metrics: List of metric names to include; if None, all are included.
    
    Returns:
        List of dicts with selected metrics + ts.
    """
    if metrics is None:
        metrics = [
            "ts", "cpu_percent", "memory_percent", "disk_percent", "core_voltage_v",
            "load_1m", "load_5m", "load_15m", "net_rx_bytes", "net_tx_bytes"
        ]
    
    # Always include ts
    if "ts" not in metrics:
        metrics = ["ts"] + metrics
    
    cols = ", ".join(metrics)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT {cols} FROM system_metrics WHERE ts BETWEEN ? AND ? ORDER BY ts ASC",
                           (start_ts, end_ts)).fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[system_metrics] get_metrics_history error: {e}")
        return []
