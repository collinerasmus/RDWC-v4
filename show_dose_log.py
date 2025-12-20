#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db_path = Path("data/rdwc.db")
if not db_path.exists():
    print("Database not found!")
    exit(1)

conn = sqlite3.connect(str(db_path))
c = conn.cursor()

# Count total doses
c.execute("SELECT COUNT(*) FROM ph_dose_log")
count = c.fetchone()[0]
print(f"Total doses in DB: {count}")

# Get last 10 doses
if count > 0:
    c.execute("SELECT id, ts_utc, volume_ml, result FROM ph_dose_log ORDER BY id DESC LIMIT 10")
    print("\nLast 10 doses:")
    for r in c.fetchall():
        print(f"  ID {r[0]}: {r[1]} | {r[2]}ml | result={r[3]}")

conn.close()
