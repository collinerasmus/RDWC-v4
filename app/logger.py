import sqlite3, threading, os, time
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rdwc.db")
DB_PATH = os.path.abspath(DB_PATH)
_lock = threading.Lock()

def _init():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS readings(
            ts INTEGER NOT NULL,
            temp_c REAL, ph REAL, ec_ms_cm REAL
        )""")
        c.commit()
_init()

def log_reading(temp_c, ph, ec_ms_cm):
    with _lock, sqlite3.connect(DB_PATH) as c:
        c.execute("INSERT INTO readings(ts,temp_c,ph,ec_ms_cm) VALUES(?,?,?,?)",
                  (int(time.time()), temp_c, ph, ec_ms_cm))
        c.commit()

def last_n(n=200):
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("SELECT ts,temp_c,ph,ec_ms_cm FROM readings ORDER BY ts DESC LIMIT ?", (n,))
        rows = [{"ts": r[0], "temp_c": r[1], "ph": r[2], "ec_ms_cm": r[3]} for r in cur.fetchall()]
    return rows[::-1]  # chronological