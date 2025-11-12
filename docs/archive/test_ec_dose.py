#!/usr/bin/env python3
"""Test EC dosing endpoints with safe 0.4s pulses"""
import requests
import json
import time

BASE_URL = 'http://127.0.0.1:8080'

def test_pump(pump_name):
    """Test a single pump with 0.4s pulse"""
    print(f"\n{'='*60}")
    print(f"Testing {pump_name.upper()} pump (0.4s pulse)")
    print('='*60)
    
    payload = {
        'pump': pump_name,
        'seconds': 0.4,
        'reason': 'smoke-test',
        'actor': 'vs-ops'
    }
    
    try:
        r = requests.post(f'{BASE_URL}/api/ec/dose', json=payload, timeout=15)
        print(f"Status Code: {r.status_code}")
        print("Response:")
        print(json.dumps(r.json(), indent=2))
        return r.json()
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def get_recent_actions():
    """Fetch recent dose log"""
    print(f"\n{'='*60}")
    print("Recent Dose Actions")
    print('='*60)
    
    try:
        r = requests.get(f'{BASE_URL}/api/ec/dose_log', timeout=10)
        data = r.json()
        print(json.dumps(data, indent=2))
        return data
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def main():
    print("EC Dosing Smoke Test - Water-Only Pumps")
    print("="*60)
    
    # Test each pump
    pumps = ['grow', 'micro', 'bloom']
    results = {}
    
    for pump in pumps:
        results[pump] = test_pump(pump)
        time.sleep(2)  # Wait between tests
    
    # Fetch recent actions
    get_recent_actions()
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print('='*60)
    for pump, result in results.items():
        if result and 'ok' in result:
            status = "✓ EXECUTED" if result.get('ok') else f"✗ BLOCKED: {result.get('error', 'Unknown')}"
        else:
            status = "✗ FAILED"
        print(f"{pump.upper():8} → {status}")

if __name__ == '__main__':
    main()
