#!/usr/bin/env python3
"""Sensor validation and health check commissioning script.

Validates I²C sensors, poller service, freshness, and health states.

Exit Codes:
  0: All sensors operational
  1: I²C device missing
  2: Sensors offline/stale
  3: Service not running
"""
import sys
import os
import argparse
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from commission_utils import (
    APIClient, APIError, create_report, save_report,
    print_status, get_host_info
)

SCRIPT_VERSION = "1.0.0"
DEFAULT_I2C_DEVICE = "/dev/i2c-1"
EXPECTED_ADDRESSES = {
    "pH": 0x63,
    "EC": 0x64,
    "RTD": 0x66,
}


def check_i2c_device(device_path: str = DEFAULT_I2C_DEVICE) -> bool:
    """Check if I²C device exists."""
    exists = os.path.exists(device_path)
    if exists:
        print_status(f"I²C device found: {device_path}", "success")
    else:
        print_status(f"I²C device not found: {device_path}", "error")
    return exists


def check_sensor_addresses(client: APIClient) -> dict:
    """Verify EZO sensors at expected addresses."""
    print_status("Checking sensor addresses...", "info")
    
    results = {
        "success": False,
        "addresses_found": [],
        "addresses_missing": [],
    }
    
    try:
        response = client.post("/fix_ezo")
        data = response.json()
        
        # Extract detected addresses from /fix_ezo response
        # Response format: {"detected": [...], "ph": {...}, "ec": {...}, "temperature": {...}}
        detected = set()
        
        # Check if there's a 'detected' key with addresses
        if "detected" in data and isinstance(data["detected"], list):
            for addr in data["detected"]:
                if isinstance(addr, int):
                    detected.add(addr)
                elif isinstance(addr, str):
                    try:
                        detected.add(int(addr, 16) if addr.startswith("0x") else int(addr))
                    except ValueError:
                        pass
        
        # Also check each sensor type for address info
        for sensor_type, addr_info in data.items():
            if isinstance(addr_info, dict) and "address" in addr_info:
                addr = addr_info["address"]
                if isinstance(addr, int):
                    detected.add(addr)
                elif isinstance(addr, str):
                    try:
                        detected.add(int(addr, 16) if addr.startswith("0x") else int(addr))
                    except ValueError:
                        pass
        
        # Check expected addresses
        for name, expected_addr in EXPECTED_ADDRESSES.items():
            if expected_addr in detected:
                results["addresses_found"].append({"name": name, "address": hex(expected_addr)})
                print_status(f"  {name} sensor found at {hex(expected_addr)}", "success")
            else:
                results["addresses_missing"].append({"name": name, "address": hex(expected_addr)})
                print_status(f"  {name} sensor NOT found at {hex(expected_addr)}", "error")
        
        results["success"] = len(results["addresses_missing"]) == 0
        
    except APIError as e:
        print_status(f"Failed to check sensor addresses: {e}", "error")
        results["error"] = str(e)
    
    return results


def check_sensor_poller(client: APIClient) -> dict:
    """Check sensor poller service status."""
    print_status("Checking sensor poller service...", "info")
    
    results = {
        "success": False,
        "running": False,
        "details": {},
    }
    
    try:
        response = client.get("/api/sensors/status")
        data = response.json()
        
        results["running"] = data.get("running", False)
        results["details"] = data
        results["success"] = results["running"]
        
        if results["running"]:
            print_status("Sensor poller is running", "success")
        else:
            print_status("Sensor poller is NOT running", "error")
            
    except APIError as e:
        print_status(f"Failed to check sensor poller: {e}", "error")
        results["error"] = str(e)
    
    return results


def check_sensor_data(client: APIClient, max_age_seconds: int = 60) -> dict:
    """Validate sensor data freshness and health."""
    print_status("Checking sensor data freshness...", "info")
    
    results = {
        "success": False,
        "online": False,
        "age_seconds": None,
        "health_state": None,
        "data": {},
    }
    
    try:
        response = client.get("/api/sensors")
        data = response.json()
        
        results["online"] = data.get("online", False)
        results["data"] = data
        
        # Calculate age
        ts = data.get("ts")
        if ts:
            # Handle both Unix timestamp and ISO format
            if isinstance(ts, str):
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    age = int(time.time()) - int(dt.timestamp())
                except:
                    age = 999  # Unknown age
            else:
                age = int(time.time()) - int(ts)
            results["age_seconds"] = age
            
            if age <= max_age_seconds:
                print_status(f"Data is fresh: {age}s old (< {max_age_seconds}s)", "success")
            else:
                print_status(f"Data is stale: {age}s old (> {max_age_seconds}s)", "error")
        
        # Check health state
        health = data.get("health_state")
        results["health_state"] = health
        
        if health == "green":
            print_status(f"Health state: {health}", "success")
        else:
            print_status(f"Health state: {health}", "warning")
        
        # Overall success criteria
        results["success"] = (
            results["online"] and
            results["age_seconds"] is not None and
            results["age_seconds"] <= max_age_seconds and
            health == "green"
        )
        
    except APIError as e:
        print_status(f"Failed to check sensor data: {e}", "error")
        results["error"] = str(e)
    
    return results


def check_temp_compensation(client: APIClient) -> dict:
    """Verify temperature compensation throttling."""
    print_status("Checking temperature compensation...", "info")
    
    results = {
        "success": False,
        "temp_comp_applied": None,
        "details": {},
    }
    
    try:
        response = client.get("/api/sensors")
        data = response.json()
        
        temp_comp_applied = data.get("temp_comp_applied")
        temp_comp_reason = data.get("temp_comp_reason", "")
        
        results["temp_comp_applied"] = temp_comp_applied
        results["details"] = {
            "applied": temp_comp_applied,
            "reason": temp_comp_reason,
            "temperature_c": data.get("temperature_c"),
        }
        
        if temp_comp_applied is not None:
            results["success"] = True
            print_status(f"Temperature compensation: applied={temp_comp_applied}", "success")
            if temp_comp_reason:
                print_status(f"  Reason: {temp_comp_reason}", "info")
        else:
            print_status("Temperature compensation data not available", "warning")
            
    except APIError as e:
        print_status(f"Failed to check temperature compensation: {e}", "error")
        results["error"] = str(e)
    
    return results


def test_sensor_power_cycle(client: APIClient) -> dict:
    """Test sensor power cycling if configured."""
    print_status("Testing sensor power cycle (if configured)...", "info")
    
    results = {
        "success": False,
        "supported": False,
        "details": {},
    }
    
    try:
        # Check if sensor power relay exists
        relay_response = client.get("/api/relays/status")
        relay_data = relay_response.json()
        
        if "sensor_power" in relay_data.get("relays", {}):
            results["supported"] = True
            print_status("Sensor power control available", "info")
            
            # Attempt power cycle
            try:
                cycle_response = client.post(
                    "/api/sensors/power_cycle",
                    params={"off_ms": 2000, "post_wait_ms": 4000, "validate": 1}
                )
                cycle_data = cycle_response.json()
                results["details"] = cycle_data
                results["success"] = cycle_data.get("success", False)
                
                if results["success"]:
                    print_status("Sensor power cycle successful", "success")
                else:
                    print_status("Sensor power cycle failed", "error")
                    
            except APIError as e:
                print_status(f"Power cycle failed: {e}", "error")
                results["error"] = str(e)
        else:
            print_status("Sensor power control not configured (skip)", "info")
            results["success"] = True  # Not an error, just not configured
            
    except APIError as e:
        print_status(f"Failed to check sensor power: {e}", "error")
        results["error"] = str(e)
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate I²C sensors and sensor poller service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0: All sensors operational
  1: I²C device missing
  2: Sensors offline/stale
  3: Service not running
        """
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("RDWC_API_URL", "http://localhost:8080"),
        help="API base URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--output",
        default="sensor_report.json",
        help="Output JSON report file (default: sensor_report.json)"
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=60,
        help="Maximum sensor data age in seconds (default: 60)"
    )
    parser.add_argument(
        "--test-power-cycle",
        action="store_true",
        help="Test sensor power cycling (requires RDWC_SENSOR_POWER_PIN)"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )
    
    args = parser.parse_args()
    
    print_status("=== Sensor Commissioning Script ===", "info", not args.no_color)
    print_status(f"API URL: {args.api_url}", "info", not args.no_color)
    
    client = APIClient(base_url=args.api_url)
    
    config = {
        "api_url": args.api_url,
        "max_age_seconds": args.max_age,
        "test_power_cycle": args.test_power_cycle,
    }
    
    results = {}
    errors = []
    recommendations = []
    exit_code = 0
    
    try:
        # 1. Check I²C device
        results["i2c_device"] = {
            "exists": check_i2c_device(),
            "path": DEFAULT_I2C_DEVICE,
        }
        if not results["i2c_device"]["exists"]:
            exit_code = 1
            errors.append("I²C device not found")
            recommendations.append("Ensure I²C is enabled and /dev/i2c-1 exists")
        
        # 2. Check sensor addresses
        results["sensor_addresses"] = check_sensor_addresses(client)
        if not results["sensor_addresses"]["success"]:
            errors.append("Not all sensors detected at expected addresses")
            recommendations.append("Check sensor wiring and I²C connections")
        
        # 3. Check sensor poller
        results["sensor_poller"] = check_sensor_poller(client)
        if not results["sensor_poller"]["success"]:
            if exit_code == 0:
                exit_code = 3
            errors.append("Sensor poller service not running")
            recommendations.append("Start service: sudo systemctl start rdwc-sensors")
        
        # 4. Check sensor data
        results["sensor_data"] = check_sensor_data(client, args.max_age)
        if not results["sensor_data"]["success"]:
            if exit_code == 0:
                exit_code = 2
            errors.append("Sensor data is offline or stale")
            recommendations.append("Check sensor poller logs: journalctl -u rdwc-sensors -n 50")
        
        # 5. Check temperature compensation
        results["temp_compensation"] = check_temp_compensation(client)
        
        # 6. Optional: Test power cycle
        if args.test_power_cycle:
            results["power_cycle"] = test_sensor_power_cycle(client)
        
        # Summary
        print()
        if exit_code == 0:
            print_status("=== All sensor checks PASSED ===", "success", not args.no_color)
        else:
            print_status(f"=== Sensor checks FAILED (exit code: {exit_code}) ===", "error", not args.no_color)
            for error in errors:
                print_status(f"  • {error}", "error", not args.no_color)
        
        # Create and save report
        report = create_report(
            script_name="commission_sensors.py",
            version=SCRIPT_VERSION,
            config=config,
            results=results,
            errors=errors,
            recommendations=recommendations
        )
        
        save_report(report, args.output)
        
    finally:
        client.close()
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
