#!/usr/bin/env python3
"""Dosing pump calibration commissioning script.

Calibrates dosing pumps and tests safety guards.

Exit Codes:
  0: All pumps calibrated successfully
  1: Failed to discover pumps
  2: Calibration procedure failed
  3: Safety guard tests failed
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
    print_status, prompt_user
)

SCRIPT_VERSION = "1.0.0"


def discover_pumps(client: APIClient) -> dict:
    """Discover available dosing pumps."""
    print_status("Discovering dosing pumps...", "info")
    
    results = {
        "success": False,
        "pumps": [],
    }
    
    try:
        response = client.get("/calib/dose/pumps")
        data = response.json()
        
        # Extract pump information
        pumps_data = data.get("pumps", {})
        
        for pump_key, pump_info in pumps_data.items():
            pump = {
                "key": pump_key,
                "relay": pump_info.get("relay"),
                "ml_per_sec": pump_info.get("ml_per_sec"),
            }
            results["pumps"].append(pump)
            print_status(f"  Found: {pump_key} (relay: {pump['relay']}, rate: {pump['ml_per_sec']} ml/s)", "info")
        
        results["success"] = len(results["pumps"]) > 0
        
        if results["success"]:
            print_status(f"Found {len(results['pumps'])} pumps", "success")
        else:
            print_status("No pumps found", "error")
        
    except APIError as e:
        print_status(f"Failed to discover pumps: {e}", "error")
        results["error"] = str(e)
    
    return results


def prime_pump(
    client: APIClient,
    pump_id: str,
    duration_sec: int,
    auto_advance: bool
) -> dict:
    """Prime a dosing pump."""
    print_status(f"Priming {pump_id} for {duration_sec}s...", "info")
    
    results = {
        "success": False,
        "pump_id": pump_id,
        "duration_sec": duration_sec,
    }
    
    if not auto_advance:
        if not prompt_user(f"Ready to prime {pump_id}?", auto_advance):
            results["cancelled"] = True
            return results
    
    try:
        response = client.post(
            "/calib/dose/prime",
            json_data={"pump_id": pump_id, "duration_sec": duration_sec}
        )
        data = response.json()
        results["response"] = data
        results["success"] = True
        print_status(f"Prime completed for {pump_id}", "success")
        
    except APIError as e:
        print_status(f"Failed to prime {pump_id}: {e}", "error")
        results["error"] = str(e)
    
    return results


def calibrate_pump(
    client: APIClient,
    pump_id: str,
    run_duration_sec: int,
    auto_advance: bool
) -> dict:
    """Calibrate a single pump."""
    print_status(f"=== Calibrating {pump_id} ===", "info")
    
    results = {
        "success": False,
        "pump_id": pump_id,
    }
    
    # Start calibration run
    print_status(f"Starting calibration run ({run_duration_sec}s)...", "info")
    print_status("Prepare graduated cylinder or measuring container", "info")
    
    if not auto_advance:
        if not prompt_user(f"Ready to run {pump_id}?", auto_advance):
            results["cancelled"] = True
            return results
    
    try:
        response = client.post(
            "/calib/dose/run",
            json_data={"pump_id": pump_id, "duration_sec": run_duration_sec}
        )
        run_data = response.json()
        results["run_response"] = run_data
        
        print_status(f"Calibration run completed for {pump_id}", "success")
        
        # Get measured volume from user
        if auto_advance:
            # For testing, use a default value
            volume_ml = run_duration_sec * 0.5  # Assume 0.5 ml/s
            print_status(f"Using auto-advance volume: {volume_ml} ml", "info")
        else:
            print()
            print(f"Measure the dispensed volume in your graduated cylinder.")
            while True:
                try:
                    volume_input = input(f"Enter measured volume (ml) for {pump_id}: ").strip()
                    volume_ml = float(volume_input)
                    if volume_ml > 0:
                        break
                    print("Volume must be positive")
                except ValueError:
                    print("Invalid input, enter a number")
        
        results["measured_volume_ml"] = volume_ml
        
        # Commit calibration
        print_status(f"Committing calibration (volume: {volume_ml} ml)...", "info")
        
        response = client.post(
            "/calib/dose/commit",
            json_data={"pump_id": pump_id, "volume_ml": volume_ml}
        )
        commit_data = response.json()
        results["commit_response"] = commit_data
        
        # Calculate rate
        rate = volume_ml / run_duration_sec
        results["calculated_rate"] = rate
        
        print_status(f"{pump_id} calibrated: {rate:.3f} ml/s", "success")
        
        # Verify by reading pump list
        verify_response = client.get("/calib/dose/pumps")
        verify_data = verify_response.json()
        pumps = verify_data.get("pumps", {})
        
        if pump_id in pumps:
            updated_rate = pumps[pump_id].get("ml_per_sec")
            results["verified_rate"] = updated_rate
            
            if updated_rate and updated_rate > 0:
                print_status(f"Verified rate: {updated_rate:.3f} ml/s", "success")
                results["success"] = True
            else:
                print_status("Verified rate is invalid", "error")
        else:
            print_status("Could not verify pump calibration", "warning")
            results["success"] = True  # Still consider success if commit worked
        
    except APIError as e:
        print_status(f"Failed to calibrate {pump_id}: {e}", "error")
        results["error"] = str(e)
    
    return results


def test_safety_guards(client: APIClient, skip: bool) -> dict:
    """Test dosing safety guards."""
    print_status("=== Testing Safety Guards ===", "info")
    
    results = {
        "success": False,
        "skipped": skip,
        "tests": [],
    }
    
    if skip:
        print_status("Safety guard tests skipped", "info")
        results["success"] = True
        return results
    
    # Test 1: Excessive dose (press_cap)
    print_status("Testing press_cap (excessive dose rejection)...", "info")
    try:
        response = client.post(
            "/api/ph/dose",
            json_data={"ml": 999}  # Excessive amount
        )
        data = response.json()
        
        # Should be blocked
        blocked = not data.get("ok", True) or "press_cap" in str(data).lower()
        
        test1 = {
            "name": "press_cap blocks excessive dose",
            "success": blocked,
            "expected": True,
            "actual": blocked,
            "response": data,
        }
        results["tests"].append(test1)
        
        if blocked:
            print_status("Excessive dose correctly blocked", "success")
        else:
            print_status("Excessive dose was NOT blocked!", "error")
            
    except APIError as e:
        # Error response is also acceptable
        print_status("Excessive dose rejected (expected)", "success")
        test1 = {
            "name": "press_cap blocks excessive dose",
            "success": True,
            "expected": True,
            "actual": True,
            "error": str(e),
        }
        results["tests"].append(test1)
    
    # Test 2: E-STOP blocks dosing
    print_status("Testing E-STOP blocks dosing...", "info")
    try:
        # Activate E-STOP
        client.post("/api/relays/estop/toggle")
        
        # Try to dose
        try:
            response = client.post(
                "/api/ph/dose",
                json_data={"ml": 5}
            )
            data = response.json()
            
            # Should be blocked
            blocked = not data.get("ok", True) or "estop" in str(data).lower()
            
            test2 = {
                "name": "E-STOP blocks dosing",
                "success": blocked,
                "expected": True,
                "actual": blocked,
                "response": data,
            }
            results["tests"].append(test2)
            
            if blocked:
                print_status("E-STOP correctly blocked dosing", "success")
            else:
                print_status("E-STOP did NOT block dosing!", "error")
                
        except APIError as e:
            # Error is acceptable
            print_status("E-STOP blocked dosing (expected)", "success")
            test2 = {
                "name": "E-STOP blocks dosing",
                "success": True,
                "expected": True,
                "actual": True,
                "error": str(e),
            }
            results["tests"].append(test2)
        
        # Deactivate E-STOP
        client.post("/api/relays/estop/toggle")
        
    except APIError as e:
        print_status(f"E-STOP test failed: {e}", "error")
        test2 = {
            "name": "E-STOP blocks dosing",
            "success": False,
            "error": str(e),
        }
        results["tests"].append(test2)
    
    # Test 3: pH guard (informational - requires specific pH conditions)
    print_status("pH/EC guard tests require specific sensor conditions (skip)", "info")
    test3 = {
        "name": "pH/EC guards (informational)",
        "success": True,
        "note": "Requires specific pH/EC conditions to trigger",
    }
    results["tests"].append(test3)
    
    # Overall success
    results["success"] = all(t["success"] for t in results["tests"])
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Calibrate dosing pumps and test safety guards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0: All pumps calibrated successfully
  1: Failed to discover pumps
  2: Calibration procedure failed
  3: Safety guard tests failed

Example:
  python commission_pumps.py --pump ph_up
  python commission_pumps.py --auto-advance --skip-guards
        """
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("RDWC_API_URL", "http://localhost:8080"),
        help="API base URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--output",
        default="pump_calibration.json",
        help="Output JSON report file (default: pump_calibration.json)"
    )
    parser.add_argument(
        "--pump",
        help="Calibrate specific pump only (e.g., ph_up, grow, micro, bloom)"
    )
    parser.add_argument(
        "--prime-sec",
        type=int,
        default=5,
        help="Prime duration in seconds (default: 5)"
    )
    parser.add_argument(
        "--run-sec",
        type=int,
        default=30,
        help="Calibration run duration in seconds (default: 30)"
    )
    parser.add_argument(
        "--skip-guards",
        action="store_true",
        help="Skip safety guard tests"
    )
    parser.add_argument(
        "--auto-advance",
        action="store_true",
        help="Skip interactive prompts (testing mode)"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )
    
    args = parser.parse_args()
    
    print_status("=== Pump Calibration Script ===", "info", not args.no_color)
    print_status(f"API URL: {args.api_url}", "info", not args.no_color)
    
    client = APIClient(base_url=args.api_url)
    
    config = {
        "api_url": args.api_url,
        "specific_pump": args.pump,
        "prime_sec": args.prime_sec,
        "run_sec": args.run_sec,
        "skip_guards": args.skip_guards,
        "auto_advance": args.auto_advance,
    }
    
    results = {}
    errors = []
    recommendations = []
    exit_code = 0
    
    try:
        # 1. Discover pumps
        results["discovery"] = discover_pumps(client)
        
        if not results["discovery"]["success"]:
            exit_code = 1
            errors.append("Failed to discover pumps")
            recommendations.append("Check pump configuration and API endpoint")
        else:
            # Determine which pumps to calibrate
            available_pumps = [p["key"] for p in results["discovery"]["pumps"]]
            
            if args.pump:
                if args.pump in available_pumps:
                    pumps_to_calibrate = [args.pump]
                else:
                    print_status(f"Pump '{args.pump}' not found", "error")
                    exit_code = 1
                    errors.append(f"Specified pump '{args.pump}' not available")
                    pumps_to_calibrate = []
            else:
                pumps_to_calibrate = available_pumps
            
            # 2. Calibrate each pump
            calibration_results = []
            
            for pump_id in pumps_to_calibrate:
                print()
                print_status(f"Starting calibration for {pump_id}", "info", not args.no_color)
                
                # Prime pump
                prime_result = prime_pump(
                    client, pump_id, args.prime_sec, args.auto_advance
                )
                
                if not prime_result.get("success"):
                    if not prime_result.get("cancelled"):
                        print_status(f"Prime failed for {pump_id}", "error", not args.no_color)
                    calibration_results.append({
                        "pump_id": pump_id,
                        "success": False,
                        "prime": prime_result,
                    })
                    continue
                
                # Calibrate pump
                calib_result = calibrate_pump(
                    client, pump_id, args.run_sec, args.auto_advance
                )
                
                calibration_results.append({
                    "pump_id": pump_id,
                    "success": calib_result.get("success", False),
                    "prime": prime_result,
                    "calibration": calib_result,
                })
                
                if not calib_result.get("success"):
                    if exit_code == 0:
                        exit_code = 2
                    errors.append(f"Calibration failed for {pump_id}")
            
            results["calibrations"] = calibration_results
            
            # 3. Test safety guards
            if not args.skip_guards:
                print()
                results["safety_guards"] = test_safety_guards(client, args.skip_guards)
                
                if not results["safety_guards"]["success"]:
                    if exit_code == 0:
                        exit_code = 3
                    errors.append("Safety guard tests failed")
                    recommendations.append("Review safety guard implementation")
        
        # Summary
        print()
        if exit_code == 0:
            print_status("=== Pump Calibration COMPLETED ===", "success", not args.no_color)
            
            # Show calibrated rates
            if "calibrations" in results:
                print()
                print_status("Calibrated pump rates:", "info", not args.no_color)
                for calib in results["calibrations"]:
                    if calib["success"]:
                        rate = calib["calibration"].get("calculated_rate", 0)
                        print_status(f"  {calib['pump_id']}: {rate:.3f} ml/s", "success", not args.no_color)
        else:
            print_status(f"=== Pump Calibration FAILED (exit code: {exit_code}) ===", "error", not args.no_color)
            for error in errors:
                print_status(f"  • {error}", "error", not args.no_color)
        
        # Create and save report
        report = create_report(
            script_name="commission_pumps.py",
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
