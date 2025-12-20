import sqlite3
from pathlib import Path

DB_PATH = Path("data/rdwc.db")
conn = sqlite3.connect(str(DB_PATH))
c = conn.cursor()

# Check last dose
c.execute("SELECT id, created_at, volume_ml FROM ph_dose_log ORDER BY id DESC LIMIT 5")
rows = c.fetchall()
print("=== Last 5 doses ===")
for r in rows:
    print(f"ID {r[0]}: {r[1]} | {r[2]} ml")

# Check for doses in last 5 minutes
c.execute("SELECT COUNT(*) FROM ph_dose_log WHERE created_at > datetime('now', '-5 minutes')")
print(f"\nDoses in last 5 min: {c.fetchone()[0]}")

# Check dose lock status in system_state
c.execute("SELECT dosing_thread_locked, dosing_in_progress FROM system_state ORDER BY id DESC LIMIT 1")
r = c.fetchone()
if r:
    print(f"Dosing lock status: locked={r[0]}, in_progress={r[1]}")

conn.close()
