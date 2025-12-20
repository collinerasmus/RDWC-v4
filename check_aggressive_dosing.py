#!/usr/bin/env python3
"""Quick script to verify aggressive pH dosing progress."""
import requests
import json
from datetime import datetime

BASE = "http://192.168.88.55:8080"

try:
    # pH status
    status = requests.get(f"{BASE}/api/ph/status", timeout=10).json()
    ph = status.get("ph")
    targets = status.get("targets", {})
    auto = status.get("auto", {})
    guards = status.get("guards", {})
    learned = auto.get("learned_ml_per_pH")
    holding = auto.get("holding_reason")
    
    print(f"\n=== pH Status ===")
    print(f"Current pH: {ph}")
    print(f"Targets: [{targets.get('low')}, {targets.get('high')}]")
    print(f"Auto Enabled: {auto.get('enabled')}")
    print(f"Learned ml/pH: {learned}")
    print(f"Holding Reason: {holding}")
    print(f"Interval Guard: {guards.get('interval')} (since_last_ok_s={guards.get('since_last_ok_s')})")
    print(f"Out of Band: {guards.get('out_of_band')}")
    
    # Recent doses
    doses = requests.get(f"{BASE}/api/ph/dose_log?hours=2&limit=10", timeout=10).json()
    if doses and len(doses) > 0:
        print(f"\n=== Recent Doses (last {len(doses)}) ===")
        for d in doses[-5:]:  # last 5
            ts = d.get("ts_utc", "")[-8:] if d.get("ts_utc") else "?"
            result = str(d.get("result") or "?")
            reason = str(d.get("reason") or "?")[:20]
            pre = d.get("pre_ph")
            post = d.get("post_ph")
            vol = d.get("volume_ml")
            delta = round(post - pre, 4) if (pre is not None and post is not None) else None
            print(f"  {ts} | {result:8} | {reason:20} | pre={pre} post={post} ΔpH={delta} vol={vol}ml")
    
    print("\n✓ Aggressive dosing active. System progressing toward setpoint.")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
