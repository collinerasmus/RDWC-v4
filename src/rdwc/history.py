import sqlite3, os, time
DB_PATH = os.path.expanduser("~/RDWC-v4/data/history.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
      CREATE TABLE IF NOT EXISTS history (
        ts REAL PRIMARY KEY,
        temperature REAL,
        ec REAL,
        ph REAL
      );
    """)
    conn.commit()
    conn.close()

def log_sample(data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO history (ts, temperature, ec, ph) VALUES (?,?,?,?)",
              (data.get("ts", time.time()), data.get("temperature_c"), data.get("ec"), data.get("pH")))
    conn.commit()
    conn.close()

def read_recent(limit=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ts, temperature, ec, ph FROM history ORDER BY ts DESC LIMIT ?", (limit,))
    rows = [{"ts": r[0], "temperature_c": r[1], "ec": r[2], "pH": r[3]} for r in c.fetchall()]
    conn.close()
    return rows