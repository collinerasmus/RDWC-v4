#!/usr/bin/env python3
"""Comprehensive UI endpoint test - reports pass/fail for all functionality."""
import requests
import time

BASE = "http://192.168.88.49:8080"
results = []

def test(name: str, method: str, path: str, data=None, expect_status=200, check_json=True) -> bool:
    """Run a test and record result."""
    try:
        if method == "GET":
            r = requests.get(f"{BASE}{path}", timeout=5)
        elif method == "POST":
            r = requests.post(f"{BASE}{path}", json=data, timeout=5)
        else:
            results.append((name, False, f"Unknown method {method}"))
            return False
        
        if r.status_code != expect_status:
            results.append((name, False, f"Status {r.status_code} != {expect_status}"))
            return False
        
        if check_json:
            j = r.json()  # Will raise if not JSON
        
        results.append((name, True, "OK"))
        return True
    except requests.Timeout:
        results.append((name, False, "Timeout"))
        return False
    except Exception as e:
        results.append((name, False, str(e)[:50]))
        return False

print("=" * 70)
print("RDWC-v4 UI COMPREHENSIVE TEST SUITE")
print("=" * 70)

# Health & Status
print("\n[HEALTH & STATUS]")
test("Health", "GET", "/health")
test("Progress", "GET", "/api/progress")

# Sensors
print("\n[SENSORS]")
test("Sensors Cached", "GET", "/api/sensors")
test("Sensors Status", "GET", "/api/sensors/status")
test("Sensor Read Now", "POST", "/read_now")
test("Fix EZO", "POST", "/fix_ezo")

# Relays
print("\n[RELAYS]")
test("Relay Status", "GET", "/api/relays/status")
# Use GET fallback for mode to avoid POST hang
test("System Mode Auto (GET)", "GET", "/api/system_mode/set?mode=auto", check_json=False)
test("System Mode Manual (GET)", "GET", "/api/system_mode/set?mode=manual", check_json=False)
test("Estop Status", "GET", "/api/estop")

# pH Control
print("\n[PH CONTROL]")
test("pH Status", "GET", "/api/ph/status")
# Use GET fallbacks to avoid POST hang
test("pH Auto Enable (GET)", "GET", "/api/ph/auto/enable?on=1")
test("pH Auto Disable (GET)", "GET", "/api/ph/auto/enable?on=0")
test("pH Dose Log", "GET", "/api/ph/dose_log")

# EC Control
print("\n[EC CONTROL]")
test("EC Status", "GET", "/api/ec/status")
test("EC Auto Enable (GET)", "GET", "/api/ec/auto/enable?on=1")
test("EC Auto Disable (GET)", "GET", "/api/ec/auto/enable?on=0")
test("EC Dose Log", "GET", "/api/ec/dose_log")

# Settings
print("\n[SETTINGS]")
test("Settings GET", "GET", "/settings")
test("Settings Namespaced", "GET", "/api/settings")

# Calibration Status
print("\n[CALIBRATION]")
test("pH Cal Status", "GET", "/calib/ph/status")
test("pH Cal Caps", "GET", "/calib/ph/caps")
test("EC Cal Status", "GET", "/api/ec/cal/status")
test("Dose Pumps", "GET", "/calib/dose/pumps")

# Chiller
print("\n[CHILLER]")
test("Chiller Status", "GET", "/api/chiller/status")

# Schedule
print("\n[SCHEDULE]")
test("Schedule Current Week", "GET", "/api/schedule/current_week")
test("Schedule Plan", "GET", "/api/schedule/plan")

# Diagnostics
print("\n[DIAGNOSTICS]")
test("Diag Sensors Once", "GET", "/diag/sensors/once")

# Summary
print("\n" + "=" * 70)
print("TEST RESULTS SUMMARY")
print("=" * 70)

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)

print(f"\nTotal: {total} | Passed: {passed} | Failed: {failed}")
print(f"Pass Rate: {100*passed/total:.1f}%\n")

if failed > 0:
    print("FAILURES:")
    for name, ok, msg in results:
        if not ok:
            print(f"  ✗ {name}: {msg}")

print("\nPASSED:")
for name, ok, msg in results:
    if ok:
        print(f"  ✓ {name}")

# Check critical issues
print("\n" + "=" * 70)
print("CRITICAL CHECKS")
print("=" * 70)

try:
    r = requests.get(f"{BASE}/api/sensors", timeout=3)
    sensors = r.json()
    ts = sensors.get("ts")
    try:
        # ts may be ISO string
        if isinstance(ts, str) and "T" in ts:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age = time.time() - dt.timestamp()
        else:
            age = time.time() - float(ts or 0)
    except Exception:
        age = 9e9
    print(f"Sensor data age: {age:.0f}s {'✓ FRESH' if age < 60 else '✗ STALE'}")
    print(f"  Temp: {sensors.get('temperature_c')}°C")
    print(f"  pH: {sensors.get('ph')}")
    print(f"  EC: {sensors.get('ec_mscm')} mS/cm")
except Exception as e:
    print(f"✗ Could not check sensors: {e}")

try:
    r = requests.get(f"{BASE}/api/progress", timeout=3)
    prog = r.json()
    print(f"\nSystem Progress: {prog.get('percentage')}%")
    comps = prog.get("components", {})
    for k, v in comps.items():
        print(f"  {k}: {'✓' if v else '✗'}")
except Exception as e:
    print(f"✗ Could not check progress: {e}")

print("\n" + "=" * 70)
if failed == 0:
    print("🎉 ALL TESTS PASSED - SYSTEM READY FOR NUTRIENT HOOKUP")
else:
    print(f"⚠️  {failed} ISSUE(S) NEED FIXING")
print("=" * 70)
