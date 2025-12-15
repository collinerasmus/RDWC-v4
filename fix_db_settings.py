#!/usr/bin/env python3
"""Fix temperature settings in the database."""
import sqlite3
import sys

db_path = '/home/pi/RDWC-v4/data/rdwc.db'
try:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("=== BEFORE ===")
    cur.execute("SELECT key, value FROM settings WHERE key LIKE '%temp%' OR key LIKE '%hyster%' ORDER BY key")
    for row in cur.fetchall():
        print(f'  {row[0]}: {row[1]}')

    # Update to correct values
    cur.execute("UPDATE settings SET value='20' WHERE key='targets.temp_target_c'")
    cur.execute("UPDATE settings SET value='0.5' WHERE key='chiller.hysteresis'")
    cur.execute("UPDATE settings SET value='0.5' WHERE key='temperature.hysteresis'")
    cur.execute("DELETE FROM settings WHERE key IN ('temperature.target_temp', 'chiller.target_temp')")
    conn.commit()

    print("\n=== AFTER ===")
    cur.execute("SELECT key, value FROM settings WHERE key LIKE '%temp%' OR key LIKE '%hyster%' ORDER BY key")
    for row in cur.fetchall():
        print(f'  {row[0]}: {row[1]}')
    conn.close()
    print("\nDatabase fixed successfully!")
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
