#!/usr/bin/env python3
import sqlite3

db = sqlite3.connect("data/rdwc.db")
db.execute("UPDATE settings SET value='false' WHERE key='safety.maintenance_override'")
db.commit()
print("maintenance_override disabled")
