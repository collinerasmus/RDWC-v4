#!/usr/bin/env python3
import sqlite3
import json
from pathlib import Path

db_path = Path("data/rdwc.db")
conn = sqlite3.connect(str(db_path))
c = conn.cursor()

c.execute("SELECT * FROM ph_dose_log WHERE id >= 722 ORDER BY id")
rows = c.fetchall()
cols = [desc[0] for desc in c.description]

print("=== Doses 722-724 (pending_retry) ===")
for r in rows:
    d = dict(zip(cols, r))
    print(json.dumps(d, indent=2, default=str))

conn.close()
