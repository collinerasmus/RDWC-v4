#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db_path = Path("data/rdwc.db")
conn = sqlite3.connect(str(db_path))

# Mark all pending_retry as abandoned
conn.execute("UPDATE ph_dose_log SET result='retry_abandoned' WHERE result='pending_retry'")
affected = conn.total_changes
conn.commit()

print(f"Cleared {affected} pending_retry doses")

# Verify
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM ph_dose_log WHERE result='pending_retry'")
remaining = c.fetchone()[0]
print(f"Remaining pending_retry: {remaining}")

conn.close()
