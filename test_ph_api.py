#!/usr/bin/env python3
"""Check what /api/ph/status actually returns."""
import requests
import json

try:
    resp = requests.get('http://localhost:8080/api/ph/status')
    data = resp.json()
    print("=== /api/ph/status Response ===")
    print(json.dumps(data, indent=2))
    print("\n=== pH Targets ===")
    targets = data.get('targets', {})
    print(f"Low:  {targets.get('low')}")
    print(f"High: {targets.get('high')}")
except Exception as e:
    print(f"Error: {e}")
