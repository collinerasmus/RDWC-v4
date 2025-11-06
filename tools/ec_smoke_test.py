#!/usr/bin/env python3
"""
EC Control v1 UI Smoke Test
Tests the dose endpoint with minimal 0.2s pulse and verifies UI responsiveness.
"""
import requests
import json
import time
import sys

BASE_URL = "http://192.168.88.49:8080"

def test_dose_endpoint():
    """Test if /api/dose/grow endpoint exists and responds."""
    print("Testing /api/dose/grow endpoint...")
    try:
        # Probe with 0-second dose
        response = requests.post(
            f"{BASE_URL}/api/dose/grow",
            json={"seconds": 0.0, "reason": "probe"},
            timeout=5
        )
        print(f"  Probe status: {response.status_code}")
        if response.status_code == 200:
            print(f"  Response: {response.json()}")
            return True
        else:
            print(f"  Error: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"  Exception: {e}")
        return False

def get_current_ec():
    """Get current EC reading."""
    try:
        response = requests.get(f"{BASE_URL}/api/sensors/last", timeout=5)
        if response.ok:
            data = response.json()
            return data.get("ec_mscm")
        return None
    except Exception:
        return None

def perform_minimal_dose():
    """Perform a minimal 0.2s grow dose."""
    print("\nPerforming minimal dose (0.2s Grow)...")
    
    # Get EC before
    ec_before = get_current_ec()
    print(f"  EC before: {ec_before} mS/cm")
    
    try:
        # Perform dose
        response = requests.post(
            f"{BASE_URL}/api/dose/grow",
            json={"seconds": 0.2, "reason": "ec-ui-smoke"},
            timeout=5
        )
        print(f"  Dose status: {response.status_code}")
        
        if response.ok:
            result = response.json()
            print(f"  Result: {json.dumps(result, indent=2)}")
            
            # Wait a moment then check EC
            time.sleep(2)
            ec_after = get_current_ec()
            print(f"  EC after: {ec_after} mS/cm")
            
            return True
        else:
            print(f"  Error: {response.text[:300]}")
            return False
            
    except Exception as e:
        print(f"  Exception: {e}")
        return False

def check_recent_doses():
    """Check recent dose log."""
    print("\nChecking recent dose log...")
    try:
        response = requests.get(f"{BASE_URL}/api/dose/recent?limit=5", timeout=5)
        if response.ok:
            data = response.json()
            events = data.get("events", [])
            print(f"  Found {len(events)} recent events")
            for i, event in enumerate(events[:3]):
                print(f"  [{i+1}] {event.get('ts_utc')} - {event.get('pump')} - {event.get('seconds')}s - {event.get('reason')}")
            return True
        else:
            print(f"  Error: {response.status_code}")
            return False
    except Exception as e:
        print(f"  Exception: {e}")
        return False

def main():
    print("=" * 60)
    print("EC Control v1 UI Smoke Test")
    print("=" * 60)
    
    # Test endpoint availability
    if not test_dose_endpoint():
        print("\n❌ Endpoint test failed - endpoint may not be available")
        print("   UI will fall back to relay pulse mode")
    else:
        print("\n✓ Endpoint available")
    
    # Perform minimal dose
    if perform_minimal_dose():
        print("\n✓ Dose completed successfully")
    else:
        print("\n❌ Dose failed")
        return 1
    
    # Check recent log
    if check_recent_doses():
        print("\n✓ Recent dose log accessible")
    else:
        print("\n⚠ Recent dose log not available")
    
    print("\n" + "=" * 60)
    print("SMOKE TEST COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Open UI: http://192.168.88.49:8080")
    print("2. Navigate to EC tab")
    print("3. Verify:")
    print("   - Setpoint field shows saved value")
    print("   - Δ chip shows deviation from setpoint")
    print("   - Safety caps row populated")
    print("   - Recent activity shows the smoke test dose")
    print("   - Quick-dose buttons work with spinner")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
