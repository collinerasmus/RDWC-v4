"""SQLite connection pool helper for RDWC-v4.
Provides a small fixed pool of connections with WAL enabled.
Use get_conn(readonly=True) for reads (returns shared read connection)
and get_conn() for writes (round-robin)."""
import sqlite3
import threading
from pathlib import Path
import os

_pool_lock = threading.Lock()
_write_pool = []
_write_index = 0
_read_conn = None
POOL_SIZE = int(os.getenv("RDWC_DB_POOL_SIZE", "5"))
DB_PATH = Path(__file__).parent.parent / "data" / "rdwc.db"

def _init_conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-16000")  # ~16MB cache
    except Exception:
        pass
    return conn

def _ensure_pool():
    global _write_pool, _read_conn
    if _write_pool and _read_conn:
        return
    DB_PATH.parent.mkdir(exist_ok=True)
    with _pool_lock:
        if not _read_conn:
            _read_conn = _init_conn(DB_PATH)
        if not _write_pool:
            for _ in range(max(1, POOL_SIZE)):
                _write_pool.append(_init_conn(DB_PATH))

def get_conn(readonly: bool = False) -> sqlite3.Connection:
    _ensure_pool()
    global _write_index
    if readonly:
        return _read_conn
    with _pool_lock:
        conn = _write_pool[_write_index]
        _write_index = (_write_index + 1) % len(_write_pool)
        return conn

def close_all():
    with _pool_lock:
        global _read_conn
        for c in _write_pool:
            try:
                c.close()
            except Exception:
                pass
        _write_pool.clear()
        if _read_conn:
            try:
                _read_conn.close()
            except Exception:
                pass
            _read_conn = None