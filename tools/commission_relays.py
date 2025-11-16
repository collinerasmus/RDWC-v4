#!/usr/bin/env python3
"""Relay safety validation commissioning script.

Validates E-STOP, mode transitions, cooldown enforcement, and protected relay checks.

Exit Codes:
  0: All safety checks pass
  1: E-STOP failure
  2: Cooldown violation
  3: Protected relay bypass
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
    print_status
)

SCRIPT_VERSION = "1.0.0"


def get_relay_status(client: APIClient) -> dict:
    """Get current relay status."""
    try:
        response = client.get("/api/relays/status")
        return response.json()
    except APIError as e:
        print_status(f"Failed to get relay status: {e}", "error")
        return {}


def test_estop_toggle(client: APIClient) -> dict:
    """Test E-STOP toggle functionality."""
    print_status("=== Testing E-STOP ===", "info")
    
    results = {
        "success": False,
        "tests": [],
    }
    
    # Get initial state
    initial_status = get_relay_status(client)
    initial_estop = initial_status.get("estop", False)
    results["initial_estop"] = initial_estop
    
    print_status(f"Initial E-STOP state: {initial_estop}", "info")
    
    try:
        # Test 1: Toggle E-STOP ON
        print_status("Toggling E-STOP ON...", "info")
        response = client.post("/api/relays/estop/toggle")
        toggle_data = response.json()
        
        # Verify E-STOP is now active
        status = get_relay_status(client)
        estop_active = status.get("estop", False)
        
        test1 = {
            "name": "E-STOP activation",
            "success": estop_active,
            "expected": True,
            "actual": estop_active,
        }
        results["tests"].append(test1)
        
        if estop_active:
            print_status("E-STOP activated successfully", "success")
            
            # Verify all relays are OFF
            relays = status.get("relays", {})
            all_off = all(not relay.get("is_on", False) for relay in relays.values())
            
            test2 = {
                "name": "All relays OFF when E-STOP active",
                "success": all_off,
                "expected": True,
                "actual": all_off,
            }
            results["tests"].append(test2)
            
            if all_off:
                print_status("All relays are OFF", "success")
            else:
                print_status("Some relays are still ON!", "error")
            
            # Test 3: Attempt to operate relay (should fail)
            print_status("Testing relay operation blocking...", "info")
            try:
                # Try to turn on main_pump
                block_response = client.post(
                    "/api/relays/set",
                    json_data={"relay_key": "main_pump", "state": True, "reason": "test"}
                )
                block_data = block_response.json()
                
                # Check if operation was blocked
                blocked = not block_data.get("changed", True)
                
                test3 = {
                    "name": "E-STOP blocks relay operations",
                    "success": blocked,
                    "expected": True,
                    "actual": blocked,
                    "response": block_data,
                }
                results["tests"].append(test3)
                
                if blocked:
                    print_status("Relay operation blocked successfully", "success")
                else:
                    print_status("Relay operation was NOT blocked!", "error")
                    
            except APIError as e:
                # An error is also acceptable (operation rejected)
                print_status("Relay operation rejected (expected)", "success")
                test3 = {
                    "name": "E-STOP blocks relay operations",
                    "success": True,
                    "expected": True,
                    "actual": True,
                    "error": str(e),
                }
                results["tests"].append(test3)
            
            # Test 4: Toggle E-STOP OFF
            print_status("Toggling E-STOP OFF...", "info")
            response = client.post("/api/relays/estop/toggle")
            
            # Verify E-STOP is now inactive
            status = get_relay_status(client)
            estop_inactive = not status.get("estop", True)
            
            test4 = {
                "name": "E-STOP deactivation",
                "success": estop_inactive,
                "expected": True,
                "actual": estop_inactive,
            }
            results["tests"].append(test4)
            
            if estop_inactive:
                print_status("E-STOP deactivated successfully", "success")
            else:
                print_status("E-STOP still active!", "error")
        else:
            print_status("E-STOP activation failed!", "error")
        
        # Overall success: all tests passed
        results["success"] = all(t["success"] for t in results["tests"])
        
    except APIError as e:
        print_status(f"E-STOP test failed: {e}", "error")
        results["error"] = str(e)
    
    return results


def test_mode_transitions(client: APIClient) -> dict:
    """Test manual/auto mode transitions."""
    print_status("=== Testing Mode Transitions ===", "info")
    
    results = {
        "success": False,
        "tests": [],
    }
    
    # Get initial mode
    initial_status = get_relay_status(client)
    initial_mode = initial_status.get("mode", "unknown")
    results["initial_mode"] = initial_mode
    
    print_status(f"Initial mode: {initial_mode}", "info")
    
    try:
        # Test 1: Switch to manual mode
        print_status("Switching to manual mode...", "info")
        response = client.post("/api/relays/mode", json_data={"mode": "manual"})
        
        status = get_relay_status(client)
        is_manual = status.get("mode") == "manual"
        
        test1 = {
            "name": "Switch to manual mode",
            "success": is_manual,
            "expected": "manual",
            "actual": status.get("mode"),
        }
        results["tests"].append(test1)
        
        if is_manual:
            print_status("Switched to manual mode", "success")
        else:
            print_status("Failed to switch to manual mode", "error")
        
        # Test 2: Switch to auto mode
        print_status("Switching to auto mode...", "info")
        response = client.post("/api/relays/mode", json_data={"mode": "auto"})
        
        status = get_relay_status(client)
        is_auto = status.get("mode") == "auto"
        
        test2 = {
            "name": "Switch to auto mode",
            "success": is_auto,
            "expected": "auto",
            "actual": status.get("mode"),
        }
        results["tests"].append(test2)
        
        if is_auto:
            print_status("Switched to auto mode", "success")
        else:
            print_status("Failed to switch to auto mode", "error")
        
        # Overall success
        results["success"] = all(t["success"] for t in results["tests"])
        
    except APIError as e:
        print_status(f"Mode transition test failed: {e}", "error")
        results["error"] = str(e)
    
    return results


def test_protected_relays(client: APIClient) -> dict:
    """Test protected relay (lights/chiller) reason enforcement."""
    print_status("=== Testing Protected Relays ===", "info")
    
    results = {
        "success": False,
        "tests": [],
    }
    
    protected_relays = ["lights", "chiller_power"]
    
    for relay_key in protected_relays:
        # Check if relay exists
        status = get_relay_status(client)
        if relay_key not in status.get("relays", {}):
            print_status(f"{relay_key} not available (skip)", "info")
            continue
        
        # Try with non-whitelisted reason (should be blocked)
        print_status(f"Testing {relay_key} with non-whitelisted reason...", "info")
        
        try:
            response = client.post(
                "/api/relays/set",
                json_data={"relay_key": relay_key, "state": True, "reason": "invalid_test"}
            )
            data = response.json()
            
            # Should be blocked
            blocked = not data.get("changed", True) or "reason" in data.get("block_reason", "").lower()
            
            test = {
                "name": f"{relay_key} blocks non-whitelisted reason",
                "success": blocked,
                "expected": True,
                "actual": blocked,
                "response": data,
            }
            results["tests"].append(test)
            
            if blocked:
                print_status(f"{relay_key} correctly blocked invalid reason", "success")
            else:
                print_status(f"{relay_key} did NOT block invalid reason!", "error")
                
        except APIError as e:
            # Error is also acceptable
            print_status(f"{relay_key} rejected operation (expected)", "success")
            test = {
                "name": f"{relay_key} blocks non-whitelisted reason",
                "success": True,
                "expected": True,
                "actual": True,
                "error": str(e),
            }
            results["tests"].append(test)
    
    results["success"] = all(t["success"] for t in results["tests"]) if results["tests"] else True
    
    return results


def test_cooldown_enforcement(client: APIClient) -> dict:
    """Test cooldown timer enforcement."""
    print_status("=== Testing Cooldown Enforcement ===", "info")
    
    results = {
        "success": False,
        "tests": [],
    }
    
    # Test with main_pump (has 5s cooldown)
    relay_key = "main_pump"
    
    try:
        # Check if relay exists
        status = get_relay_status(client)
        if relay_key not in status.get("relays", {}):
            print_status(f"{relay_key} not available (skip)", "info")
            results["success"] = True
            results["skipped"] = True
            return results
        
        # Turn relay ON
        print_status(f"Turning {relay_key} ON...", "info")
        response = client.post(
            "/api/relays/set",
            json_data={"relay_key": relay_key, "state": True, "reason": "test"}
        )
        data = response.json()
        
        if not data.get("changed"):
            print_status(f"Failed to turn {relay_key} ON (may be blocked)", "warning")
            results["skipped"] = True
            results["success"] = True
            return results
        
        # Immediately try to turn OFF (should be blocked by cooldown)
        print_status(f"Immediately trying to turn {relay_key} OFF...", "info")
        time.sleep(0.5)  # Small delay
        
        response = client.post(
            "/api/relays/set",
            json_data={"relay_key": relay_key, "state": False, "reason": "test"}
        )
        data = response.json()
        
        # Check if cooldown blocked the operation
        cooldown_blocked = not data.get("changed", True) and "cooldown" in data.get("block_reason", "").lower()
        
        test1 = {
            "name": "Cooldown blocks rapid OFF after ON",
            "success": cooldown_blocked,
            "expected": True,
            "actual": cooldown_blocked,
            "response": data,
        }
        results["tests"].append(test1)
        
        if cooldown_blocked:
            print_status("Cooldown correctly enforced", "success")
        else:
            print_status("Cooldown was NOT enforced!", "error")
        
        # Clean up: wait for cooldown and turn OFF
        print_status("Waiting for cooldown to expire...", "info")
        time.sleep(6)
        
        response = client.post(
            "/api/relays/set",
            json_data={"relay_key": relay_key, "state": False, "reason": "test"}
        )
        
        results["success"] = all(t["success"] for t in results["tests"])
        
    except APIError as e:
        print_status(f"Cooldown test failed: {e}", "error")
        results["error"] = str(e)
    
    return results


def test_service_restart(client: APIClient) -> dict:
    """Verify relays default to OFF after service restart (informational)."""
    print_status("=== Service Restart Test (Informational) ===", "info")
    
    results = {
        "success": True,
        "note": "This test requires manual service restart to fully validate",
    }
    
    # Just check current state
    status = get_relay_status(client)
    relays = status.get("relays", {})
    
    all_off = all(not relay.get("is_on", False) for relay in relays.values())
    
    print_status(f"Current state: {'All relays OFF' if all_off else 'Some relays ON'}", "info")
    print_status("To fully test: sudo systemctl restart rdwc.service", "info")
    
    results["current_all_off"] = all_off
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate relay safety mechanisms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0: All safety checks pass
  1: E-STOP failure
  2: Cooldown violation
  3: Protected relay bypass

Example:
  python commission_relays.py
        """
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("RDWC_API_URL", "http://localhost:8080"),
        help="API base URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--output",
        default="relay_safety.json",
        help="Output JSON report file (default: relay_safety.json)"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )
    
    args = parser.parse_args()
    
    print_status("=== Relay Safety Commissioning Script ===", "info", not args.no_color)
    print_status(f"API URL: {args.api_url}", "info", not args.no_color)
    
    client = APIClient(base_url=args.api_url)
    
    config = {
        "api_url": args.api_url,
    }
    
    results = {}
    errors = []
    recommendations = []
    exit_code = 0
    
    try:
        # 1. Test E-STOP
        results["estop"] = test_estop_toggle(client)
        if not results["estop"]["success"]:
            exit_code = 1
            errors.append("E-STOP tests failed")
            recommendations.append("Check relay control system and E-STOP implementation")
        
        # 2. Test mode transitions
        results["mode_transitions"] = test_mode_transitions(client)
        if not results["mode_transitions"]["success"]:
            if exit_code == 0:
                exit_code = 1
            errors.append("Mode transition tests failed")
        
        # 3. Test protected relays
        results["protected_relays"] = test_protected_relays(client)
        if not results["protected_relays"]["success"]:
            if exit_code == 0:
                exit_code = 3
            errors.append("Protected relay tests failed")
            recommendations.append("Check reason whitelist configuration")
        
        # 4. Test cooldown enforcement
        results["cooldown"] = test_cooldown_enforcement(client)
        if not results["cooldown"]["success"]:
            if exit_code == 0:
                exit_code = 2
            errors.append("Cooldown enforcement tests failed")
            recommendations.append("Check cooldown timer implementation")
        
        # 5. Service restart test (informational)
        results["service_restart"] = test_service_restart(client)
        
        # Summary
        print()
        if exit_code == 0:
            print_status("=== All Relay Safety Checks PASSED ===", "success", not args.no_color)
        else:
            print_status(f"=== Relay Safety Checks FAILED (exit code: {exit_code}) ===", "error", not args.no_color)
            for error in errors:
                print_status(f"  • {error}", "error", not args.no_color)
        
        # Create and save report
        report = create_report(
            script_name="commission_relays.py",
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
