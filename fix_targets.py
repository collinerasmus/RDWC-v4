#!/usr/bin/env python3
"""Fix target settings to correct values"""
from app.settings import upsert_settings

updates = {
    "targets.ph_low": "6.1",
    "targets.ph_high": "6.2",
    "targets.ec_low": "1.45",
    "targets.ec_high": "1.55",
}

print("Updating settings:")
for k, v in updates.items():
    print(f"  {k}: {v}")

upsert_settings(updates)
print("\n✅ Done. Settings updated.")
