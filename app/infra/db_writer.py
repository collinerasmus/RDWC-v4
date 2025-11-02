"""
SQLite Database Writer with queue for RDWC-v4
Provides single-connection database writing to prevent FD leaks
"""

import atexit
import os
import sqlite3
import threading
import time
from queue import Queue, Empty
from typing import Optional

# Database configuration
DB_PATH = "data/rdwc.db"
BATCH_SIZE = 10
FLUSH_INTERVAL = 5.0  # seconds

class DatabaseWriter:
    """Thread-safe SQLite writer with queued operations"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.queue: Queue = Queue()
        self.connection: Optional[sqlite3.Connection] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.shutdown_event = threading.Event()
        self._ensure_db_dir()
        self._start_worker()
    
    def _ensure_db_dir(self):
        """Ensure database directory exists"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def _start_worker(self):
        """Start the background worker thread"""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create the database connection"""
        if self.connection is None:
            self.connection = sqlite3.connect(
                self.db_path,
                timeout=30,
                isolation_level=None,  # Autocommit mode
                check_same_thread=False
            )
            try:
                # Harden SQLite for durability and concurrency
                self.connection.execute("PRAGMA journal_mode=WAL;")
                self.connection.execute("PRAGMA synchronous=NORMAL;")
                self.connection.execute("PRAGMA busy_timeout=30000;")
                self.connection.execute("PRAGMA foreign_keys=ON;")
            except Exception:
                pass
            self._ensure_tables()
        return self.connection
    
    def _ensure_tables(self):
        """Ensure required tables exist"""
        conn = self.connection
        if conn:
            # Readings table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    temp_c REAL,
                    ph REAL,
                    ec_ms_cm REAL
                )
            """)
            
            # Events table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    event TEXT NOT NULL
                )
            """)
    
    def _worker_loop(self):
        """Main worker loop for processing queued operations"""
        batch = []
        last_flush = time.time()
        
        while not self.shutdown_event.is_set():
            try:
                # Get items from queue with timeout
                try:
                    item = self.queue.get(timeout=1.0)
                    batch.append(item)
                except Empty:
                    pass
                
                # Process batch if full or timeout reached
                current_time = time.time()
                should_flush = (
                    len(batch) >= BATCH_SIZE or
                    (batch and current_time - last_flush >= FLUSH_INTERVAL)
                )
                
                if should_flush and batch:
                    self._process_batch(batch)
                    batch.clear()
                    last_flush = current_time
                    
            except Exception as e:
                print(f"Database worker error: {e}")
                batch.clear()  # Clear batch on error to prevent loop
        
        # Process remaining items on shutdown
        if batch:
            self._process_batch(batch)
    
    def _process_batch(self, batch):
        """Process a batch of database operations with retries; never drop silently."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Use an explicit transaction for atomicity
            cursor.execute("BEGIN IMMEDIATE")
            for item in batch:
                if item['type'] == 'reading':
                    cursor.execute(
                        "INSERT INTO readings (ts, temp_c, ph, ec_ms_cm) VALUES (?, ?, ?, ?)",
                        (item['ts'], item['temp_c'], item['ph'], item['ec_ms_cm'])
                    )
                elif item['type'] == 'event':
                    cursor.execute(
                        "INSERT INTO events (ts, event) VALUES (?, ?)",
                        (item['ts'], item['event'])
                    )
            cursor.execute("COMMIT")
        except Exception as e:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            print(f"Database batch processing error (will retry individually): {e}")
            # Retry item-by-item so partial success is possible
            for item in batch:
                for attempt in range(3):
                    try:
                        if item['type'] == 'reading':
                            cursor.execute(
                                "INSERT INTO readings (ts, temp_c, ph, ec_ms_cm) VALUES (?, ?, ?, ?)",
                                (item['ts'], item['temp_c'], item['ph'], item['ec_ms_cm'])
                            )
                        elif item['type'] == 'event':
                            cursor.execute(
                                "INSERT INTO events (ts, event) VALUES (?, ?)",
                                (item['ts'], item['event'])
                            )
                        break
                    except Exception as ee:
                        if attempt == 2:
                            print(f"Database write permanently failed for item {item}: {ee}")
                        else:
                            time.sleep(0.2 * (attempt + 1))
        finally:
            try:
                cursor.close()
            except Exception:
                pass
    
    def log_reading(self, temp_c: float, ph: float, ec_ms_cm: float):
        """Queue a sensor reading for database storage"""
        self.queue.put({
            'type': 'reading',
            'ts': int(time.time()),
            'temp_c': temp_c,
            'ph': ph,
            'ec_ms_cm': ec_ms_cm
        })
    
    def log_event(self, event: str):
        """Queue an event for database storage"""
        self.queue.put({
            'type': 'event',
            'ts': int(time.time()),
            'event': event
        })
    
    def shutdown(self):
        """Shutdown the database writer and flush remaining operations"""
        self.shutdown_event.set()
        
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=10)
        
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None

# Global singleton instance
_db_writer: Optional[DatabaseWriter] = None

def get_db_writer() -> DatabaseWriter:
    """Get the singleton database writer instance"""
    global _db_writer
    if _db_writer is None:
        _db_writer = DatabaseWriter()
    return _db_writer

def log_reading(temp_c: float, ph: float, ec_ms_cm: float):
    """Convenience function to log a sensor reading"""
    get_db_writer().log_reading(temp_c, ph, ec_ms_cm)

def log_event(event: str):
    """Convenience function to log an event"""
    get_db_writer().log_event(event)

def shutdown_db():
    """Shutdown the database writer"""
    global _db_writer
    if _db_writer:
        _db_writer.shutdown()
        _db_writer = None

# Register cleanup on exit
atexit.register(shutdown_db)