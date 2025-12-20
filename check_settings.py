#!/usr/bin/env python3
from app.db_pool import get_conn

c = get_conn()

print("\n=== Current Settings (targets/temp) ===")
rows = c.execute("""
    SELECT key, value FROM settings 
    WHERE key LIKE 'targets.%' OR key LIKE 'temperature.%'
    ORDER BY key
""").fetchall()
for r in rows:
    print(f"{r[0]}: {r[1]}")

print("\n=== Recent Settings History (last 50) ===")
hist = c.execute("""
    SELECT datetime(ts, 'unixepoch') as dt, key, value 
    FROM settings_history 
    WHERE key IN ('targets.ec_low', 'targets.ec_high', 'targets.ph_low', 'targets.ph_high', 'targets.temp_target_c', 'temperature.hysteresis')
    ORDER BY ts DESC LIMIT 50
""").fetchall()
for h in hist:
    print(f"{h[0]} | {h[1]}: {h[2]}")
