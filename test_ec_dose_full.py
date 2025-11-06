#!/usr/bin/env python3
"""Test EC dosing endpoints - wait between tests to avoid interval guard"""
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
        result = r.json()
        print(json.dumps(result, indent=2))
        
        # Extract relay info if available
        if r.status_code == 200 and result.get('ok'):
            print(f"\n✓ EXECUTED: {result.get('seconds')}s pulse")
            print(f"  EC before: {result.get('ec_before')} mS/cm")
            print(f"  EC after:  {result.get('ec_after')} mS/cm")
            print(f"  Volume:    ~{result.get('seconds', 0) * 20}ml (assuming 20ml/s)")
        
        return result
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def get_recent_actions():
    """Fetch recent dose log"""
    print(f"\n{'='*60}")
    print("Recent Dose Actions (last 10)")
    print('='*60)
    
    try:
        r = requests.get(f'{BASE_URL}/api/ec/dose_log', timeout=10)
        data = r.json()
        
        if isinstance(data, list):
            for i, entry in enumerate(data[:10], 1):
                print(f"\n{i}. {entry.get('ts', 'N/A')}")
                print(f"   Pump: {entry.get('pump', 'N/A')} (assumed from context)")
                print(f"   Duration: {entry.get('seconds', 'N/A')}s")
                print(f"   Volume: {entry.get('volume_ml', 'N/A')}ml")
                print(f"   EC: {entry.get('ec_before', 'N/A')} → {entry.get('ec_after', 'N/A')} mS/cm")
                print(f"   Reason: {entry.get('detail', 'N/A')}")
                if entry.get('guard_triggered'):
                    print(f"   ⚠️  Guard triggered!")
        else:
            print(json.dumps(data, indent=2))
        
        return data
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def main():
    print("EC Dosing Smoke Test - Water-Only Pumps")
    print("Using 5min (300s) intervals to avoid guard blocks")
    print("="*60)
    
    # Test each pump with delay
    pumps = ['grow', 'micro', 'bloom']
    results = {}
    
    for i, pump in enumerate(pumps):
        if i > 0:
            wait_time = 305  # 5min + 5s buffer
            print(f"\n⏳ Waiting {wait_time}s for interval guard...")
            for remaining in range(wait_time, 0, -30):
                print(f"   {remaining}s remaining...", end='\r')
                time.sleep(min(30, remaining))
            print()  # Newline after countdown
        
        results[pump] = test_pump(pump)
    
    # Fetch recent actions
    time.sleep(2)
    get_recent_actions()
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print('='*60)
    for pump, result in results.items():
        if result and result.get('ok'):
            status = "✓ EXECUTED"
        elif result and 'error' in result:
            status = f"✗ BLOCKED: {result.get('error')}"
        else:
            status = "✗ FAILED"
        print(f"{pump.upper():8} → {status}")
    
    # Check for relay mapping confirmation
    print(f"\n{'='*60}")
    print("Expected Relay Mapping (from hardware docs):")
    print('='*60)
    print("  Grow  → BCM GPIO 6")
    print("  Micro → BCM GPIO 13")
    print("  Bloom → BCM GPIO 19")
    print("\n⚠️  Verify no pumps latched ON after test!")

if __name__ == '__main__':
    main()
