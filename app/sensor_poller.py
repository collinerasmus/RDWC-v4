"""
Headless sensor poller - runs 24/7 independently of web UI/browsers.

This module provides:
- Continuous pH/EC/Temp polling at fixed intervals
- PID-based single-instance lock (prevents duplicate pollers)
- Heartbeat timestamp tracking
- SQLite data persistence
- REST API status endpoint

Design:
- Uses /run/rdwc_sensors.lock (or fallback to /tmp) for PID lock
- Writes sensor_poller_heartbeat_ts to system_state table
- Writes sensor_poller_pid on start
- Can be run standalone or embedded in main app
"""
import os
import sys
import time
import signal
import logging
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Lock file configuration
LOCK_FILE = Path("/run/rdwc_sensors.lock")
if not LOCK_FILE.parent.exists() or not os.access(LOCK_FILE.parent, os.W_OK):
    LOCK_FILE = Path("/tmp/rdwc_sensors.lock")

# Polling configuration from environment
POLL_INTERVAL_SEC = int(os.environ.get("RDWC_SENSOR_POLL_INTERVAL", "5"))
DB_PATH = os.environ.get("RDWC_DB_PATH", "data/rdwc.db")

# Global state
_poller_running = False
_last_sample_ts: Optional[float] = None
_last_heartbeat_ts: Optional[float] = None
_poll_count = 0


class PollerLockError(Exception):
    """Raised when another poller instance holds the lock"""
    pass


def _is_pid_running(pid: int) -> bool:
    """Check if a PID is currently running"""
    try:
        # Signal 0 doesn't kill, just checks if process exists
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def acquire_lock(force: bool = False) -> None:
    """
    Acquire PID lock file to ensure single poller instance.
    
    Args:
        force: If True, forcibly take over lock even if another PID exists
        
    Raises:
        PollerLockError: If lock is held by another running process
    """
    if LOCK_FILE.exists():
        try:
            existing_pid = int(LOCK_FILE.read_text().strip())
            if _is_pid_running(existing_pid) and not force:
                raise PollerLockError(
                    f"Sensor poller already running (PID {existing_pid}). "
                    f"Use --force to override or kill PID manually."
                )
            logger.warning(f"Stale lock file found (PID {existing_pid}), removing")
        except (ValueError, OSError) as e:
            logger.warning(f"Invalid lock file, removing: {e}")
        
        LOCK_FILE.unlink()
    
    # Write our PID
    my_pid = os.getpid()
    LOCK_FILE.write_text(str(my_pid))
    logger.info(f"Acquired sensor poller lock (PID {my_pid}, lock: {LOCK_FILE})")


def release_lock() -> None:
    """Release PID lock file"""
    if LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink()
            logger.info(f"Released sensor poller lock: {LOCK_FILE}")
        except OSError as e:
            logger.error(f"Failed to release lock: {e}")


def _get_db_conn() -> sqlite3.Connection:
    """Get database connection (creates DB/tables if needed)"""
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.Connection(db_path)
    conn.row_factory = sqlite3.Row
    
    # Ensure tables exist
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS readings (
            ts INTEGER PRIMARY KEY,
            temp_c REAL,
            ph REAL,
            ec_ms_cm REAL
        );
        
        CREATE TABLE IF NOT EXISTS system_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at INTEGER
        );
        
        CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(ts DESC);
    """)
    conn.commit()
    return conn


def _update_system_state(key: str, value: str) -> None:
    """Update a key-value pair in system_state table"""
    try:
        conn = _get_db_conn()
        now = int(time.time())
        conn.execute(
            "INSERT OR REPLACE INTO system_state (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to update system_state[{key}]: {e}")


# Persistent EZO instances (init once per process lifetime)
_ezo_devices = None

def _init_sensors():
    """Initialize EZO devices once per process"""
    global _ezo_devices
    if _ezo_devices is not None:
        return
    
    from app.ezo_i2c_stabilized import EZO, RTD_ADDR, PH_ADDR, EC_ADDR
    rtd = EZO(1, RTD_ADDR, "RTD")
    ph = EZO(1, PH_ADDR, "pH")
    ec = EZO(1, EC_ADDR, "EC")
    
    # NOTE: NOT calling init_once() - leave devices in continuous mode
    # This allows read_value() to immediately fetch latest reading without
    # waiting for on-demand measurement completion
    
    _ezo_devices = {"rtd": rtd, "ph": ph, "ec": ec}
    logger.info("EZO sensors initialized (continuous mode)")


def _read_sensors() -> Dict[str, Any]:
    """
    Read sensors using persistent EZO instances.
    
    Returns:
        Dict with keys: temp_c, ph, ec_ms_cm, errors
    """
    try:
        _init_sensors()
        rtd = _ezo_devices["rtd"]
        ph = _ezo_devices["ph"]
        ec = _ezo_devices["ec"]
        
        # Read RTD first
        temp_c = float(rtd.read_value())
        
        # Apply temperature compensation
        for dev in (ph, ec):
            try:
                dev.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.06)
            except Exception:
                pass
        
        # Read pH and EC
        ph_val = float(ph.read_value())
        ec_val = float(ec.read_value())
        
        return {
            "temp_c": temp_c,
            "ph": ph_val,
            "ec_ms_cm": ec_val,
            "errors": {}
        }
    except Exception as e:
        logger.error(f"Sensor read failed: {e}")
        return {
            "temp_c": None,
            "ph": None,
            "ec_ms_cm": None,
            "errors": {"read": str(e)}
        }


def _log_reading(temp_c: Optional[float], ph: Optional[float], ec_ms_cm: Optional[float]) -> None:
    """Write sensor reading to database"""
    try:
        conn = _get_db_conn()
        ts = int(time.time())
        conn.execute(
            "INSERT INTO readings (ts, temp_c, ph, ec_ms_cm) VALUES (?, ?, ?, ?)",
            (ts, temp_c, ph, ec_ms_cm)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log reading: {e}")


def poll_once() -> Dict[str, Any]:
    """
    Execute one sensor poll cycle.
    
    Returns:
        Dict containing sensor readings and metadata
    """
    global _last_sample_ts, _last_heartbeat_ts, _poll_count
    
    readings = _read_sensors()
    now = time.time()
    
    # Log to database (NULLs allowed for offline sensors)
    _log_reading(readings["temp_c"], readings["ph"], readings["ec_ms_cm"])
    
    # Update timestamps
    _last_sample_ts = now
    _last_heartbeat_ts = now
    _poll_count += 1
    
    # Update system_state table
    _update_system_state("sensor_poller_heartbeat_ts", str(int(now)))
    _update_system_state("sensor_poller_pid", str(os.getpid()))
    _update_system_state("sensor_poller_count", str(_poll_count))
    
    logger.debug(f"Poll #{_poll_count}: temp={readings['temp_c']}, ph={readings['ph']}, ec={readings['ec_ms_cm']}")
    
    return readings


def run_poller(force: bool = False) -> None:
    """
    Run the sensor poller main loop.
    
    Args:
        force: If True, forcibly take over lock from another instance
    """
    global _poller_running
    
    # Setup signal handlers for graceful shutdown
    def _shutdown(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        global _poller_running
        _poller_running = False
    
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    
    # Acquire lock
    try:
        acquire_lock(force=force)
    except PollerLockError as e:
        logger.error(str(e))
        sys.exit(1)
    
    _poller_running = True
    logger.info(f"Starting sensor poller (interval={POLL_INTERVAL_SEC}s, db={DB_PATH})")
    
    try:
        while _poller_running:
            poll_once()
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, shutting down...")
    except Exception as e:
        logger.exception(f"Fatal error in poller loop: {e}")
    finally:
        release_lock()
        logger.info("Sensor poller stopped")


def get_status() -> Dict[str, Any]:
    """
    Get current poller status.
    
    Returns:
        Dict containing:
        - running: bool (is poller active)
        - last_sample_ts: float or None
        - last_heartbeat_ts: float or None
        - interval_sec: int
        - i2c_device: str
        - poll_count: int
        - lock_file: str
        - lock_exists: bool
        - lock_pid: int or None
    """
    lock_pid = None
    if LOCK_FILE.exists():
        try:
            lock_pid = int(LOCK_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    
    return {
        "running": _poller_running,
        "last_sample_ts": _last_sample_ts,
        "last_heartbeat_ts": _last_heartbeat_ts,
        "interval_sec": POLL_INTERVAL_SEC,
        "i2c_device": "/dev/i2c-1",  # Standard Pi I2C bus
        "poll_count": _poll_count,
        "lock_file": str(LOCK_FILE),
        "lock_exists": LOCK_FILE.exists(),
        "lock_pid": lock_pid
    }


if __name__ == "__main__":
    # Standalone mode - run as dedicated poller service
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    force = "--force" in sys.argv
    run_poller(force=force)
