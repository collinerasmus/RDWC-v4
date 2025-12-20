#!/usr/bin/env python3
"""Update EC tolerance to achieve 1.45-1.55 band with scheduler target of 1.5"""
from app.settings import upsert_settings

updates = {
    "targets.ec_tolerance": "0.05",  # 1.5 ± 0.05 = 1.45-1.55
}

print("Updating EC tolerance:")
for k, v in updates.items():
    print(f"  {k}: {v}")
print("\nWith week 7 scheduler target of 1.5, this gives band: 1.45-1.55 ✅")

upsert_settings(updates)
print("\n✅ Done.")
