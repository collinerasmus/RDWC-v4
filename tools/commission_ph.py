#!/usr/bin/env python3
"""pH calibration commissioning script.

Automates 3-point pH calibration workflow (mid/low/high).

Exit Codes:
  0: Calibration successful
  1: Calibration capabilities check failed
  2: Calibration procedure failed
  3: Accuracy validation failed
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
    print_status, wait_for_stability, prompt_user
)

SCRIPT_VERSION = "1.0.0"

# Standard buffer values
BUFFER_MID = 7.00
BUFFER_LOW = 4.01
BUFFER_HIGH = 10.00


def check_capabilities(client: APIClient) -> dict:
    """Check pH calibration capabilities."""
    print_status("Checking pH calibration capabilities...", "info")
    
    results = {
        "success": False,
        "capabilities": {},
    }
    
    try:
        response = client.get("/calib/ph/caps")
        data = response.json()
        results["capabilities"] = data
        results["success"] = True
        print_status("pH calibration capabilities available", "success")
        
    except APIError as e:
        print_status(f"Failed to check capabilities: {e}", "error")
        results["error"] = str(e)
    
    return results


def clear_calibration(client: APIClient) -> dict:
    """Clear existing pH calibration."""
    print_status("Clearing existing pH calibration...", "info")
    
    results = {
        "success": False,
    }
    
    try:
        response = client.post("/calib/ph/clear")
        data = response.json()
        results["response"] = data
        results["success"] = True
        print_status("Calibration cleared", "success")
        
    except APIError as e:
        print_status(f"Failed to clear calibration: {e}", "error")
        results["error"] = str(e)
    
    return results


def read_current_ph(client: APIClient) -> tuple[bool, float]:
    """Read current pH value."""
    try:
        response = client.get("/calib/ph/read")
        data = response.json()
        value = data.get("value")
        
        if value is not None:
            print_status(f"Current pH: {value:.2f}", "info")
            return True, value
        else:
            print_status("No pH value returned", "error")
            return False, 0.0
            
    except APIError as e:
        print_status(f"Failed to read pH: {e}", "error")
        return False, 0.0


def calibrate_point(
    client: APIClient,
    point: str,
    buffer_value: float,
    timeout: int,
    threshold: float,
    auto_advance: bool
) -> dict:
    """Calibrate a single pH point."""
    point_name = {"mid": "Mid-point", "low": "Low-point", "high": "High-point"}[point]
    
    print_status(f"=== {point_name} Calibration (pH {buffer_value:.2f}) ===", "info")
    
    results = {
        "success": False,
        "point": point,
        "buffer_value": buffer_value,
        "readings": [],
    }
    
    # Prompt user to place probe
    if not prompt_user(
        f"Place probe in pH {buffer_value:.2f} buffer and press Enter",
        auto_advance
    ):
        print_status("Calibration cancelled by user", "warning")
        results["cancelled"] = True
        return results
    
    # Wait a moment for probe to equilibrate
    if not auto_advance:
        time.sleep(5)
    
    # Read current value
    success, current = read_current_ph(client)
    if not success:
        results["error"] = "Failed to read pH"
        return results
    
    # Wait for stability
    stable, final_value, readings = wait_for_stability(
        client=client,
        read_endpoint="/calib/ph/read",
        value_key="value",
        threshold=threshold,
        timeout_s=timeout,
        check_interval=3
    )
    
    results["readings"] = readings
    results["stable"] = stable
    results["final_value"] = final_value
    
    if not stable:
        print_status(f"Reading did not stabilize within {timeout}s", "error")
        results["error"] = "Unstable reading"
        return results
    
    # Check if reading is reasonable for this buffer
    expected_range = 1.0  # Allow ±1.0 pH from buffer value
    if abs(final_value - buffer_value) > expected_range:
        print_status(
            f"Warning: Reading {final_value:.2f} is far from buffer {buffer_value:.2f}",
            "warning"
        )
    
    # Execute calibration
    print_status(f"Executing {point} calibration...", "info")
    
    try:
        response = client.post(f"/calib/ph/{point}")
        data = response.json()
        results["calibration_response"] = data
        results["success"] = True
        print_status(f"{point_name} calibration successful", "success")
        
    except APIError as e:
        print_status(f"Calibration failed: {e}", "error")
        results["error"] = str(e)
    
    return results


def verify_calibration(client: APIClient) -> dict:
    """Verify calibration flags."""
    print_status("Verifying calibration status...", "info")
    
    results = {
        "success": False,
        "flags": [],
    }
    
    try:
        response = client.get("/calib/ph/status")
        data = response.json()
        flags = data.get("flags", [])
        results["flags"] = flags
        results["status_data"] = data
        
        expected_flags = ["mid", "low", "high"]
        missing = [f for f in expected_flags if f not in flags]
        
        if not missing:
            print_status(f"All calibration flags present: {flags}", "success")
            results["success"] = True
        else:
            print_status(f"Missing calibration flags: {missing}", "error")
            results["missing_flags"] = missing
            
    except APIError as e:
        print_status(f"Failed to verify calibration: {e}", "error")
        results["error"] = str(e)
    
    return results


def check_accuracy(
    client: APIClient,
    tolerance: float = 0.05,
    skip: bool = False
) -> dict:
    """Check pH accuracy in reservoir against reference meter."""
    results = {
        "success": False,
        "skipped": skip,
    }
    
    if skip:
        print_status("Accuracy check skipped", "info")
        results["success"] = True
        return results
    
    print_status("=== Accuracy Validation ===", "info")
    print("Place probe back in reservoir and wait for reading to stabilize.")
    
    # Get reference value from user
    try:
        ref_value = float(input("Enter reference meter pH reading: ").strip())
        results["reference_value"] = ref_value
    except ValueError:
        print_status("Invalid reference value", "error")
        results["error"] = "Invalid reference value"
        return results
    
    # Read calibrated probe
    success, probe_value = read_current_ph(client)
    if not success:
        results["error"] = "Failed to read probe value"
        return results
    
    results["probe_value"] = probe_value
    
    # Check accuracy
    diff = abs(probe_value - ref_value)
    results["difference"] = diff
    
    if diff <= tolerance:
        print_status(
            f"Accuracy check PASSED: probe={probe_value:.2f}, ref={ref_value:.2f}, diff={diff:.3f}",
            "success"
        )
        results["success"] = True
    else:
        print_status(
            f"Accuracy check FAILED: probe={probe_value:.2f}, ref={ref_value:.2f}, diff={diff:.3f} (> {tolerance})",
            "error"
        )
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Automate 3-point pH calibration workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0: Calibration successful
  1: Calibration capabilities check failed
  2: Calibration procedure failed
  3: Accuracy validation failed

Example:
  python commission_ph.py --auto-advance --skip-reservoir
        """
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("RDWC_API_URL", "http://localhost:8080"),
        help="API base URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--output",
        default="ph_calibration.json",
        help="Output JSON report file (default: ph_calibration.json)"
    )
    parser.add_argument(
        "--auto-advance",
        action="store_true",
        help="Skip interactive prompts (testing mode)"
    )
    parser.add_argument(
        "--skip-reservoir",
        action="store_true",
        help="Skip final accuracy validation"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Stability wait timeout in seconds (default: 45)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.03,
        help="Stability threshold (default: 0.03)"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )
    
    args = parser.parse_args()
    
    print_status("=== pH Calibration Script ===", "info", not args.no_color)
    print_status(f"API URL: {args.api_url}", "info", not args.no_color)
    
    # Check for CALIB_ENABLE
    if not os.environ.get("CALIB_ENABLE"):
        print_status("Warning: CALIB_ENABLE environment variable not set", "warning", not args.no_color)
        print_status("Set with: export CALIB_ENABLE=1", "info", not args.no_color)
    
    client = APIClient(base_url=args.api_url)
    
    config = {
        "api_url": args.api_url,
        "auto_advance": args.auto_advance,
        "skip_reservoir": args.skip_reservoir,
        "timeout": args.timeout,
        "threshold": args.threshold,
    }
    
    results = {}
    errors = []
    recommendations = []
    exit_code = 0
    
    try:
        # 1. Check capabilities
        results["capabilities"] = check_capabilities(client)
        if not results["capabilities"]["success"]:
            exit_code = 1
            errors.append("Failed to check calibration capabilities")
            recommendations.append("Ensure CALIB_ENABLE=1 is set")
        else:
            # 2. Clear existing calibration
            results["clear"] = clear_calibration(client)
            
            # 3. Calibrate mid-point
            results["mid_point"] = calibrate_point(
                client, "mid", BUFFER_MID, args.timeout, args.threshold, args.auto_advance
            )
            
            if not results["mid_point"].get("success"):
                exit_code = 2
                errors.append("Mid-point calibration failed")
            else:
                # 4. Calibrate low-point
                results["low_point"] = calibrate_point(
                    client, "low", BUFFER_LOW, args.timeout, args.threshold, args.auto_advance
                )
                
                if not results["low_point"].get("success"):
                    exit_code = 2
                    errors.append("Low-point calibration failed")
                else:
                    # 5. Calibrate high-point
                    results["high_point"] = calibrate_point(
                        client, "high", BUFFER_HIGH, args.timeout, args.threshold, args.auto_advance
                    )
                    
                    if not results["high_point"].get("success"):
                        exit_code = 2
                        errors.append("High-point calibration failed")
                    else:
                        # 6. Verify calibration
                        results["verification"] = verify_calibration(client)
                        
                        if not results["verification"]["success"]:
                            exit_code = 2
                            errors.append("Calibration verification failed")
                        else:
                            # 7. Optional accuracy check
                            results["accuracy"] = check_accuracy(
                                client, tolerance=0.05, skip=args.skip_reservoir
                            )
                            
                            if not results["accuracy"]["success"]:
                                exit_code = 3
                                errors.append("Accuracy validation failed")
                                recommendations.append("Check probe condition and buffer freshness")
        
        # Summary
        print()
        if exit_code == 0:
            print_status("=== pH Calibration COMPLETED ===", "success", not args.no_color)
        else:
            print_status(f"=== pH Calibration FAILED (exit code: {exit_code}) ===", "error", not args.no_color)
            for error in errors:
                print_status(f"  • {error}", "error", not args.no_color)
        
        # Create and save report
        report = create_report(
            script_name="commission_ph.py",
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
