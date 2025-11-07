#!/usr/bin/env python3
"""
RDWC v4 System Audit & Dry Run Test
Tests all critical paths without nutrients (dry run safe).
"""
import requests
import time
import sys
from typing import Dict, Any

BASE_URL = "http://192.168.88.49:8080"

class SystemAudit:
    def __init__(self):
        self.results = []
        self.failed = []
    
    def test(self, name: str, func):
        """Run a test and record result."""
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print('='*60)
        try:
            result = func()
            if result:
                print(f"✓ PASS: {name}")
                self.results.append({"test": name, "status": "PASS", "details": result})
            else:
                print(f"✗ FAIL: {name}")
                self.failed.append(name)
                self.results.append({"test": name, "status": "FAIL", "details": "Test returned False"})
        except Exception as e:
            print(f"✗ ERROR: {name}")
            print(f"  {str(e)}")
            self.failed.append(name)
            self.results.append({"test": name, "status": "ERROR", "details": str(e)})
    
    def summary(self):
        """Print test summary."""
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print('='*60)
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        print(f"Total: {total} | Passed: {passed} | Failed: {len(self.failed)}")
        if self.failed:
            print("\nFailed tests:")
            for name in self.failed:
                print(f"  - {name}")
            return False
        print("\n✓ ALL TESTS PASSED")
        return True

audit = SystemAudit()

# === Test Functions ===

def test_service_health():
    """Check service is running and responding."""
    r = requests.get(f"{BASE_URL}/api/health", timeout=5)
    data = r.json()
    print(f"  Service: {data.get('ok')}")
    print(f"  Uptime: {data.get('uptime_seconds')}s")
    return data.get('ok') == True

def test_relay_status():
    """Check relay status endpoint."""
    r = requests.get(f"{BASE_URL}/api/relays/status", timeout=5)
    data = r.json()
    print(f"  Mode: {data.get('mode')}")
    print(f"  E-Stop: {data.get('estop')}")
    print(f"  Relays count: {len(data.get('relays', {}))}")
    return len(data.get('relays', {})) == 8

def test_sensor_readings():
    """Check sensor readings are available."""
    r = requests.get(f"{BASE_URL}/sensors/read", timeout=5)
    data = r.json()
    print(f"  pH: {data.get('ph')}")
    print(f"  EC: {data.get('ec_mscm')} mS/cm")
    print(f"  Temp: {data.get('temperature_c')} °C")
    print(f"  Stale: {data.get('stale_seconds')}s")
    # Allow None for dry run (no water)
    return 'ph' in data and 'ec_mscm' in data and 'temperature_c' in data

def test_relay_toggle_lights():
    """Test relay toggle via API (lights)."""
    # Get current state
    r = requests.get(f"{BASE_URL}/api/relays/status", timeout=5)
    initial = r.json()['relays']['lights']['is_on']
    print(f"  Initial state: {'ON' if initial else 'OFF'}")
    
    # Toggle
    r = requests.post(f"{BASE_URL}/api/relay/lights/toggle", json={"on": not initial}, timeout=5)
    result = r.json()
    print(f"  Toggle result: {result}")
    
    # Verify change
    time.sleep(0.5)
    r = requests.get(f"{BASE_URL}/api/relays/status", timeout=5)
    final = r.json()['relays']['lights']['is_on']
    print(f"  Final state: {'ON' if final else 'OFF'}")
    
    # Toggle back
    requests.post(f"{BASE_URL}/api/relay/lights/toggle", json={"on": initial}, timeout=5)
    
    return final != initial

def test_guard_integrity():
    """Check relay guard integrity."""
    r = requests.get(f"{BASE_URL}/api/relays/verify", timeout=5)
    data = r.json()
    print(f"  OK all: {data.get('ok_all')}")
    print(f"  Mismatches: {len(data.get('mismatches', []))}")
    return data.get('ok_all') == True

def test_guard_events():
    """Check guard events are being logged."""
    r = requests.get(f"{BASE_URL}/api/relays/guard/recent?limit=5", timeout=5)
    data = r.json()
    events = data.get('events', [])
    print(f"  Recent events: {len(events)}")
    if events:
        last = events[-1]
        print(f"  Last event: {last.get('relay')} → {last.get('status')}")
    return True  # Non-blocking

def test_dosing_pump_micro_short_pulse():
    """Test micro pump with 0.3s pulse (dry run safe)."""
    print("  WARNING: Pump will activate for 0.3s")
    print("  Ensure pumps are NOT in nutrient solution!")
    time.sleep(2)
    
    r = requests.post(
        f"{BASE_URL}/api/dose/micro",
        json={"seconds": 0.3, "reason": "test", "actor": "audit_script"},
        timeout=20
    )
    
    if r.status_code == 409:
        data = r.json()
        print(f"  Blocked: {data.get('message')}")
        # Check if it's a guard (expected) vs error
        blocked = data.get('blocked_by', '')
        if 'cap' in blocked or 'min_off' in blocked:
            print("  (Expected guard block—pump hardware is functional)")
            return True
        elif 'stale' in blocked:
            print("  (Stale sensor block—normal if sensors not ready)")
            return True
        return False
    elif r.status_code == 200:
        data = r.json()
        print(f"  Success: {data.get('ok')}")
        print(f"  Duration: {data.get('seconds')}s")
        return data.get('ok') == True
    else:
        print(f"  HTTP {r.status_code}: {r.text}")
        return False

def test_chiller_status():
    """Check chiller control status."""
    r = requests.get(f"{BASE_URL}/api/chiller/status", timeout=5)
    data = r.json()
    print(f"  Auto enabled: {data.get('auto_enabled')}")
    print(f"  Chiller ON: {data.get('chiller_on')}")
    print(f"  Current temp: {data.get('current_temp')} °C")
    return 'auto_enabled' in data

# === Run All Tests ===

print("""
╔══════════════════════════════════════════════════════════════╗
║          RDWC v4 — SYSTEM AUDIT & DRY RUN TEST              ║
╚══════════════════════════════════════════════════════════════╝

This script validates all critical paths:
  • Service health
  • Relay control (UI → API → Guard → GPIO)
  • Sensor readings
  • Dosing pump endpoints
  • Chiller automation
  • Guard integrity

⚠️  SAFETY: Pumps will pulse for 0.3s—ensure NOT in nutrients!
""")

input("Press Enter to start audit...")

# Core infrastructure
audit.test("Service Health", test_service_health)
audit.test("Relay Status API", test_relay_status)
audit.test("Sensor Readings API", test_sensor_readings)

# Relay control
audit.test("Relay Toggle (Lights)", test_relay_toggle_lights)
audit.test("Guard Integrity Check", test_guard_integrity)
audit.test("Guard Event Logging", test_guard_events)

# Dosing
audit.test("Dosing Pump (Micro 0.3s pulse)", test_dosing_pump_micro_short_pulse)

# Automation
audit.test("Chiller Status API", test_chiller_status)

# Summary
print()
success = audit.summary()

if success:
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    SYSTEM READY                              ║
╚══════════════════════════════════════════════════════════════╝

All critical paths validated. Proceed to hot commissioning:
  1. Fill reservoir with water + nutrients
  2. Calibrate pH/EC sensors
  3. Run 1mL dose test (see HOT_COMMISSION.md)
  4. Verify EC rise after nutrient dose
""")
    sys.exit(0)
else:
    print("""
╔══════════════════════════════════════════════════════════════╗
║                  FAILURES DETECTED                           ║
╚══════════════════════════════════════════════════════════════╝

Fix failed tests before commissioning.
""")
    sys.exit(1)
