#!/usr/bin/env python3
import sqlite3

DB_PATH = "data/rdwc.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("\n=== Direct DB query ===")
rows = cur.execute("""
    SELECT key, value FROM settings 
    WHERE key IN ('targets.ph_low', 'targets.ph_high', 'targets.ec_low', 'targets.ec_high')
    ORDER BY key
""").fetchall()

for k, v in rows:
    print(f"{k}: {v}")

conn.close()
