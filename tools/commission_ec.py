#!/usr/bin/env python3
"""EC calibration commissioning script.

Automates EC K-value configuration and calibration.

Exit Codes:
  0: Calibration successful
  1: K-value configuration failed
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
    print_status, prompt_user
)

SCRIPT_VERSION = "1.0.0"

# Standard calibration solution values (µS/cm)
SOLUTION_LOW = 1413
SOLUTION_HIGH = 12880


def set_k_value(client: APIClient, k_value: float) -> dict:
    """Set EC probe K-value."""
    print_status(f"Setting K-value to {k_value}...", "info")
    
    results = {
        "success": False,
        "k_value": k_value,
    }
    
    try:
        response = client.post("/api/ec/k", json_data={"k_value": k_value})
        data = response.json()
        results["response"] = data
        results["success"] = True
        print_status(f"K-value set to {k_value}", "success")
        
    except APIError as e:
        print_status(f"Failed to set K-value: {e}", "error")
        results["error"] = str(e)
    
    return results


def clear_calibration(client: APIClient) -> dict:
    """Clear existing EC calibration."""
    print_status("Clearing existing EC calibration...", "info")
    
    results = {
        "success": False,
    }
    
    try:
        response = client.post("/api/ec/cal/clear")
        data = response.json()
        results["response"] = data
        results["success"] = True
        print_status("Calibration cleared", "success")
        
    except APIError as e:
        print_status(f"Failed to clear calibration: {e}", "error")
        results["error"] = str(e)
    
    return results


def calibrate_point(
    client: APIClient,
    point: str,
    solution_value: int,
    auto_advance: bool
) -> dict:
    """Calibrate EC at a specific point."""
    point_name = {"low": "Low-point", "high": "High-point"}[point]
    
    print_status(f"=== {point_name} Calibration ({solution_value} µS/cm) ===", "info")
    
    results = {
        "success": False,
        "point": point,
        "solution_value": solution_value,
    }
    
    # Prompt user to place probe
    if not prompt_user(
        f"Place probe in {solution_value} µS/cm solution and press Enter",
        auto_advance
    ):
        print_status("Calibration cancelled by user", "warning")
        results["cancelled"] = True
        return results
    
    # Wait for probe to stabilize
    if not auto_advance:
        print_status("Waiting for probe to stabilize (30s)...", "info")
        time.sleep(30)
    else:
        time.sleep(2)
    
    # Execute calibration
    print_status(f"Executing {point} calibration...", "info")
    
    try:
        response = client.post(
            f"/api/ec/cal/{point}",
            json_data={"value": solution_value}
        )
        data = response.json()
        results["calibration_response"] = data
        results["success"] = True
        print_status(f"{point_name} calibration successful", "success")
        
    except APIError as e:
        print_status(f"Calibration failed: {e}", "error")
        results["error"] = str(e)
    
    return results


def verify_calibration(client: APIClient, two_point: bool) -> dict:
    """Verify EC calibration status."""
    print_status("Verifying calibration status...", "info")
    
    results = {
        "success": False,
        "cal_points": [],
    }
    
    try:
        response = client.get("/api/ec/cal/status")
        data = response.json()
        
        cal_data = data.get("cal", {})
        results["status_data"] = data
        results["cal_data"] = cal_data
        
        # Check for expected calibration points
        if "low" in cal_data:
            results["cal_points"].append("low")
            print_status("Low-point calibration confirmed", "success")
        
        if "high" in cal_data:
            results["cal_points"].append("high")
            print_status("High-point calibration confirmed", "success")
        
        # Verify based on expected points
        if two_point:
            results["success"] = "low" in results["cal_points"] and "high" in results["cal_points"]
            if not results["success"]:
                print_status("Two-point calibration incomplete", "error")
        else:
            results["success"] = "low" in results["cal_points"]
            if not results["success"]:
                print_status("Low-point calibration not found", "error")
        
    except APIError as e:
        print_status(f"Failed to verify calibration: {e}", "error")
        results["error"] = str(e)
    
    return results


def check_accuracy(
    client: APIClient,
    tolerance: int = 50,
    skip: bool = False
) -> dict:
    """Check EC accuracy in reservoir against reference meter."""
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
    time.sleep(5)
    
    # Get reference value from user
    try:
        ref_value = int(input("Enter reference meter EC reading (µS/cm): ").strip())
        results["reference_value"] = ref_value
    except ValueError:
        print_status("Invalid reference value", "error")
        results["error"] = "Invalid reference value"
        return results
    
    # Read calibrated probe
    try:
        response = client.get("/api/sensors")
        data = response.json()
        probe_value = data.get("ec_mscm")
        
        if probe_value is None:
            print_status("No EC value returned", "error")
            results["error"] = "No EC value"
            return results
        
        # Convert mS/cm to µS/cm
        probe_value_us = probe_value * 1000
        results["probe_value"] = probe_value_us
        
        # Check accuracy
        diff = abs(probe_value_us - ref_value)
        results["difference"] = diff
        
        if diff <= tolerance:
            print_status(
                f"Accuracy check PASSED: probe={probe_value_us:.0f}, ref={ref_value}, diff={diff:.0f}",
                "success"
            )
            results["success"] = True
        else:
            print_status(
                f"Accuracy check FAILED: probe={probe_value_us:.0f}, ref={ref_value}, diff={diff:.0f} (> {tolerance})",
                "error"
            )
        
    except APIError as e:
        print_status(f"Failed to read probe value: {e}", "error")
        results["error"] = str(e)
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Automate EC K-value configuration and calibration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0: Calibration successful
  1: K-value configuration failed
  2: Calibration procedure failed
  3: Accuracy validation failed

Example:
  python commission_ec.py --k-value 1.0
  python commission_ec.py --k-value 1.0 --two-point
        """
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("RDWC_API_URL", "http://localhost:8080"),
        help="API base URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--output",
        default="ec_calibration.json",
        help="Output JSON report file (default: ec_calibration.json)"
    )
    parser.add_argument(
        "--k-value",
        type=float,
        default=1.0,
        help="Probe K-value constant (default: 1.0)"
    )
    parser.add_argument(
        "--two-point",
        action="store_true",
        help="Enable two-point calibration (low + high)"
    )
    parser.add_argument(
        "--skip-accuracy",
        action="store_true",
        help="Skip reservoir accuracy check"
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
    
    print_status("=== EC Calibration Script ===", "info", not args.no_color)
    print_status(f"API URL: {args.api_url}", "info", not args.no_color)
    
    client = APIClient(base_url=args.api_url)
    
    config = {
        "api_url": args.api_url,
        "k_value": args.k_value,
        "two_point": args.two_point,
        "skip_accuracy": args.skip_accuracy,
        "auto_advance": args.auto_advance,
    }
    
    results = {}
    errors = []
    recommendations = []
    exit_code = 0
    
    try:
        # 1. Set K-value
        results["k_value"] = set_k_value(client, args.k_value)
        if not results["k_value"]["success"]:
            exit_code = 1
            errors.append("Failed to set K-value")
        else:
            # 2. Clear existing calibration
            results["clear"] = clear_calibration(client)
            
            # 3. Calibrate low-point
            results["low_point"] = calibrate_point(
                client, "low", SOLUTION_LOW, args.auto_advance
            )
            
            if not results["low_point"].get("success"):
                exit_code = 2
                errors.append("Low-point calibration failed")
            else:
                # 4. Optional: Calibrate high-point
                if args.two_point:
                    results["high_point"] = calibrate_point(
                        client, "high", SOLUTION_HIGH, args.auto_advance
                    )
                    
                    if not results["high_point"].get("success"):
                        exit_code = 2
                        errors.append("High-point calibration failed")
                
                # 5. Verify calibration
                if exit_code == 0:
                    results["verification"] = verify_calibration(client, args.two_point)
                    
                    if not results["verification"]["success"]:
                        exit_code = 2
                        errors.append("Calibration verification failed")
                    else:
                        # 6. Optional accuracy check
                        results["accuracy"] = check_accuracy(
                            client, tolerance=50, skip=args.skip_accuracy
                        )
                        
                        if not results["accuracy"]["success"]:
                            exit_code = 3
                            errors.append("Accuracy validation failed")
                            recommendations.append("Check probe condition and solution freshness")
        
        # Summary
        print()
        if exit_code == 0:
            print_status("=== EC Calibration COMPLETED ===", "success", not args.no_color)
        else:
            print_status(f"=== EC Calibration FAILED (exit code: {exit_code}) ===", "error", not args.no_color)
            for error in errors:
                print_status(f"  • {error}", "error", not args.no_color)
        
        # Create and save report
        report = create_report(
            script_name="commission_ec.py",
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
