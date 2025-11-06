#!/usr/bin/env python3
"""Restore ec.min_interval_sec to 300 (Rapid Test OFF)."""
import urllib.request
import json

BASE = "http://localhost:8080"

# Restore interval to 300
payload = json.dumps({"ec.min_interval_sec": 300}).encode()
req = urllib.request.Request(
    BASE + "/api/settings",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="PUT"
)
resp = urllib.request.urlopen(req).read().decode()
print("Restored interval:", resp)

# Verify current setting
req2 = urllib.request.Request(BASE + "/settings")
settings = json.loads(urllib.request.urlopen(req2).read())
interval = settings.get("ec.min_interval_sec", "NOT_SET")
print(f"\nCurrent ec.min_interval_sec: {interval}")
print(f"Rapid Test Mode: {'ON (10s)' if interval == '10' else 'OFF (300s)' if interval == '300' else 'UNKNOWN'}")
