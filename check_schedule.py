#!/usr/bin/env python3
from app.db_pool import get_conn

c = get_conn()

print("\n=== Nutrient Schedule (EC targets) ===")
rows = c.execute("""
    SELECT week, stage, ec_target, grow_ml, micro_ml, bloom_ml 
    FROM nutrient_schedule 
    ORDER BY week
""").fetchall()

for r in rows:
    print(f"Week {r[0]} ({r[1]}): EC={r[2]} mS/cm | GMB={r[3]}/{r[4]}/{r[5]} ml/10L")

print("\n=== Current Settings ===")
from app.settings import get_all_settings
s = get_all_settings()
print(f"Grow start: {s.get('general.grow_start_date')}")
print(f"EC tolerance: {s.get('targets.ec_tolerance', '0.2')}")
print(f"Manual EC low/high: {s.get('targets.ec_low')}/{s.get('targets.ec_high')}")

# Calculate current week
from datetime import datetime, timezone
start_str = s.get('general.grow_start_date', '')
if start_str:
    start_date = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    days = max(0, (now - start_date).days)
    current_week = min(12, max(1, (days // 7) + 1))
    print(f"\nCurrent week: {current_week}")
