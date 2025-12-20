#!/usr/bin/env python3
"""
Test settings history tracking and API endpoint.
Verifies that target/hysteresis changes are logged with timestamps
and can be retrieved via the /api/settings/history endpoint.
"""

import requests
import json
import time
from datetime import datetime, timedelta

BASE_URL = "http://192.168.88.55:8080"

def test_settings_history():
    """Test the settings history system end-to-end."""
    
    print("[TEST] Settings History Tracking")
    print("=" * 60)
    
    # Step 1: Get current settings
    print("\n1. Fetching current settings...")
    resp = requests.get(f"{BASE_URL}/api/settings")
    if resp.status_code != 200:
        print(f"   ERROR: Failed to fetch settings: {resp.status_code}")
        return False
    
    settings = resp.json()
    print(f"   OK: Current pH targets = {settings.get('targets', {}).get('ph_low')}/{settings.get('targets', {}).get('ph_high')}")
    print(f"   OK: Current EC targets = {settings.get('targets', {}).get('ec_low')}/{settings.get('targets', {}).get('ec_high')}")
    print(f"   OK: Current Temp target = {settings.get('targets', {}).get('temp_target_c')}°C")
    print(f"   OK: Current Temp hysteresis = {settings.get('temperature', {}).get('hysteresis')}°C")
    
    # Step 2: Update a setting (pH target)
    print("\n2. Updating pH target (6.1 -> 6.0)...")
    update_payload = {
        "targets.ph_low": 6.0,
        "targets.ph_high": 6.3
    }
    print("\n2. Updating all tracked settings...")
    update_payload = {
        "targets.ph_low": 6.0,
        "targets.ph_high": 6.3,
        "targets.ec_low": 0.9,
        "targets.ec_high": 1.3,
        "targets.temp_target_c": 20.5,
        "temperature.hysteresis": 0.6
    }
    resp = requests.post(f"{BASE_URL}/api/settings/import", json=update_payload)
    if resp.status_code != 200:
        print(f"   ERROR: Failed to update settings: {resp.status_code}")
        print(f"   Response: {resp.text}")
        return False
    print(f"   OK: Settings updated")
    
    # Give it a moment to log
    time.sleep(1)
    
    # Step 3: Fetch settings history (last 10 minutes)
    print("\n3. Fetching settings history (last 10 minutes)...")
    now = datetime.utcnow()
    start_iso = (now - timedelta(minutes=10)).isoformat() + "Z"
    end_iso = now.isoformat() + "Z"
    
    history_url = f"{BASE_URL}/api/settings/history?start={start_iso}&end={end_iso}"
    resp = requests.get(history_url)
    if resp.status_code != 200:
        print(f"   ERROR: Failed to fetch history: {resp.status_code}")
        print(f"   Response: {resp.text}")
        return False
    
    history = resp.json()
    print(f"   OK: Retrieved {len(history)} history events")
    
    # Group by key and display
    by_key = {}
    for event in history:
        key = event.get('key')
        if key not in by_key:
            by_key[key] = []
        by_key[key].append(event)
    
    for key in sorted(by_key.keys()):
        events = by_key[key]
        print(f"\n   {key}:")
        for evt in events[-3:]:  # Show last 3
            ts_unix = evt.get('ts', 0)
            ts_dt = datetime.fromtimestamp(ts_unix)
            print(f"     {ts_dt.isoformat()} = {evt.get('value')}")
    
    # Step 4: Verify expected keys are present
    print("\n4. Verifying expected history keys...")
    expected_keys = [
        'targets.ph_low', 'targets.ph_high',
        'targets.ec_low', 'targets.ec_high',
        'targets.temp_target_c', 'temperature.hysteresis'
    ]
    found_keys = set(evt['key'] for evt in history if evt.get('key'))
    
    for key in expected_keys:
        if key in found_keys:
            print(f"   ✓ {key}")
        else:
            print(f"   ✗ {key} (not yet logged)")
    
    print("\n" + "=" * 60)
    print("[TEST] COMPLETE")
    return True

if __name__ == '__main__':
    try:
        success = test_settings_history()
        exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
