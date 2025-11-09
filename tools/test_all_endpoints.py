#!/usr/bin/env python3
"""Comprehensive endpoint testing for RDWC-v4 UI and API"""
import requests
import json
import time
from datetime import datetime

BASE_URL = "http://192.168.88.49:8080"
results = {"passed": [], "failed": [], "warnings": []}

def test(name, func):
    """Run a test and track results"""
    try:
        print(f"Testing: {name}...", end=" ")
        result = func()
        if result:
            results["passed"].append(name)
            print("✓ PASS")
            return True
        else:
            results["failed"].append(name)
            print("✗ FAIL")
            return False
    except Exception as e:
        results["failed"].append(f"{name}: {str(e)}")
        print(f"✗ ERROR: {e}")
        return False

# Core System Tests
def test_health():
    r = requests.get(f"{BASE_URL}/health/db", timeout=5)
    return r.status_code == 200 and r.json().get("status") == "ok"

def test_api_version():
    r = requests.get(f"{BASE_URL}/api/version", timeout=5)
    return r.status_code == 200 and "version" in r.json()

def test_progress():
    r = requests.get(f"{BASE_URL}/api/progress", timeout=5)
    data = r.json()
    return r.status_code == 200 and "percent" in data and "components" in data

# Relay Tests
def test_relay_status():
    r = requests.get(f"{BASE_URL}/api/relays/status", timeout=5)
    data = r.json()
    return r.status_code == 200 and "relays" in data and "mode" in data

def test_estop_status():
    r = requests.get(f"{BASE_URL}/api/estop", timeout=5)
    data = r.json()
    return r.status_code == 200 and "active" in data

def test_relay_mode_switch():
    # Get current mode
    r = requests.get(f"{BASE_URL}/api/relays/status", timeout=5)
    current = r.json()["mode"]
    
    # Switch to opposite
    new_mode = "manual" if current == "auto" else "auto"
    r = requests.post(f"{BASE_URL}/api/relays/mode", 
                      json={"mode": new_mode}, timeout=5)
    if r.status_code != 200:
        return False
    
    # Verify
    time.sleep(0.5)
    r = requests.get(f"{BASE_URL}/api/relays/status", timeout=5)
    switched = r.json()["mode"] == new_mode
    
    # Switch back
    requests.post(f"{BASE_URL}/api/relays/mode", 
                  json={"mode": current}, timeout=5)
    return switched

# Sensor Tests
def test_sensors():
    r = requests.get(f"{BASE_URL}/api/sensors", timeout=5)
    data = r.json()
    return (r.status_code == 200 and 
            "temperature_c" in data and 
            "ph" in data and 
            "ec_mscm" in data)

def test_sensor_status():
    r = requests.get(f"{BASE_URL}/api/sensors/status", timeout=5)
    data = r.json()
    return r.status_code == 200 and "running" in data

def test_fix_ezo():
    r = requests.post(f"{BASE_URL}/fix_ezo", timeout=10)
    return r.status_code == 200

# pH Control Tests
def test_ph_status():
    r = requests.get(f"{BASE_URL}/api/ph/status", timeout=5)
    data = r.json()
    return (r.status_code == 200 and 
            "current_ph" in data and 
            "guards" in data)

def test_ph_auto_status():
    r = requests.get(f"{BASE_URL}/api/ph/auto_mode", timeout=5)
    data = r.json()
    return r.status_code == 200 and "enabled" in data

# EC Control Tests
def test_ec_status():
    r = requests.get(f"{BASE_URL}/api/ec/status", timeout=5)
    data = r.json()
    return r.status_code == 200 and "current_ec_mscm" in data

def test_ec_auto_status():
    r = requests.get(f"{BASE_URL}/api/ec/auto_mode", timeout=5)
    data = r.json()
    return r.status_code == 200 and "enabled" in data

# Calibration Tests
def test_ph_cal_status():
    r = requests.get(f"{BASE_URL}/calib/ph/status", timeout=5)
    return r.status_code == 200

def test_ec_cal_status():
    r = requests.get(f"{BASE_URL}/api/ec/cal/status", timeout=5)
    return r.status_code == 200

def test_dose_pumps():
    r = requests.get(f"{BASE_URL}/calib/dose/pumps", timeout=5)
    data = r.json()
    return r.status_code == 200 and "pumps" in data

# Settings Tests
def test_settings_get():
    r = requests.get(f"{BASE_URL}/settings", timeout=5)
    return r.status_code == 200 and isinstance(r.json(), dict)

def test_settings_export():
    r = requests.get(f"{BASE_URL}/api/settings/export", timeout=5)
    return r.status_code == 200 and isinstance(r.json(), dict)

# Chiller Tests
def test_chiller_status():
    r = requests.get(f"{BASE_URL}/api/chiller/status", timeout=5)
    data = r.json()
    return r.status_code == 200 and "auto_enabled" in data

# History Tests
def test_history():
    r = requests.get(f"{BASE_URL}/history?limit=10", timeout=5)
    return r.status_code == 200 and isinstance(r.json(), list)

def test_history_window():
    r = requests.get(f"{BASE_URL}/history_window?hours=1", timeout=5)
    return r.status_code == 200 and isinstance(r.json(), list)

# Schedule Tests
def test_nutrient_schedule():
    r = requests.get(f"{BASE_URL}/api/nutrient_schedule", timeout=5)
    return r.status_code == 200

# Run all tests
if __name__ == "__main__":
    print("="*60)
    print("RDWC-v4 Endpoint Test Suite")
    print(f"Target: {BASE_URL}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Core System
    print("\n[CORE SYSTEM]")
    test("Health Check", test_health)
    test("API Version", test_api_version)
    test("Progress Endpoint", test_progress)
    
    # Relays
    print("\n[RELAY CONTROLS]")
    test("Relay Status", test_relay_status)
    test("E-Stop Status", test_estop_status)
    test("Relay Mode Switch", test_relay_mode_switch)
    
    # Sensors
    print("\n[SENSORS]")
    test("Sensor Data", test_sensors)
    test("Sensor Status", test_sensor_status)
    test("Fix EZO", test_fix_ezo)
    
    # pH Control
    print("\n[pH CONTROL]")
    test("pH Status", test_ph_status)
    test("pH Auto Mode Status", test_ph_auto_status)
    
    # EC Control
    print("\n[EC CONTROL]")
    test("EC Status", test_ec_status)
    test("EC Auto Mode Status", test_ec_auto_status)
    
    # Calibration
    print("\n[CALIBRATION]")
    test("pH Cal Status", test_ph_cal_status)
    test("EC Cal Status", test_ec_cal_status)
    test("Dose Pumps Status", test_dose_pumps)
    
    # Settings
    print("\n[SETTINGS]")
    test("Settings Get", test_settings_get)
    test("Settings Export", test_settings_export)
    
    # Chiller
    print("\n[CHILLER]")
    test("Chiller Status", test_chiller_status)
    
    # History
    print("\n[HISTORY]")
    test("History Endpoint", test_history)
    test("History Window", test_history_window)
    
    # Schedule
    print("\n[SCHEDULE]")
    test("Nutrient Schedule", test_nutrient_schedule)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"✓ PASSED: {len(results['passed'])}")
    print(f"✗ FAILED: {len(results['failed'])}")
    
    if results['failed']:
        print("\nFailed Tests:")
        for fail in results['failed']:
            print(f"  - {fail}")
    
    pass_rate = len(results['passed']) / (len(results['passed']) + len(results['failed'])) * 100
    print(f"\nPass Rate: {pass_rate:.1f}%")
    print("="*60)
    
    exit(0 if len(results['failed']) == 0 else 1)
