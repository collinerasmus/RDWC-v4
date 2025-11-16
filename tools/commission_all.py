#!/usr/bin/env python3
"""Orchestrate all commissioning phases with comprehensive reporting.

Runs all 5 phases in sequence:
1. Sensor health validation
2. pH calibration
3. EC calibration
4. Relay safety tests
5. Dosing pump calibration

Exit Codes:
  0: All phases completed successfully
  1-5: Specific phase failed (matches phase number)
  99: Multiple phases failed
"""
import sys
import os
import argparse
import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from commission_utils import print_status, get_host_info

SCRIPT_VERSION = "1.0.0"

PHASES = {
    "sensors": {
        "name": "Sensor Health Validation",
        "script": "commission_sensors.py",
        "output": "sensor_report.json",
    },
    "ph": {
        "name": "pH Calibration",
        "script": "commission_ph.py",
        "output": "ph_calibration.json",
    },
    "ec": {
        "name": "EC Calibration",
        "script": "commission_ec.py",
        "output": "ec_calibration.json",
    },
    "relays": {
        "name": "Relay Safety Tests",
        "script": "commission_relays.py",
        "output": "relay_safety.json",
    },
    "pumps": {
        "name": "Pump Calibration",
        "script": "commission_pumps.py",
        "output": "pump_calibration.json",
    },
}


def run_phase(
    phase_key: str,
    phase_info: dict,
    args: argparse.Namespace,
    tools_dir: Path
) -> dict:
    """Run a single commissioning phase."""
    script_path = tools_dir / phase_info["script"]
    
    print()
    print_status(f"=== Phase: {phase_info['name']} ===", "info", not args.no_color)
    
    result = {
        "phase": phase_key,
        "name": phase_info["name"],
        "script": phase_info["script"],
        "success": False,
        "exit_code": None,
    }
    
    if args.dry_run:
        print_status("DRY RUN: Skipping execution", "info", not args.no_color)
        result["success"] = True
        result["exit_code"] = 0
        result["dry_run"] = True
        return result
    
    # Build command
    cmd = [sys.executable, str(script_path)]
    
    # Add common arguments
    if args.api_url:
        cmd.extend(["--api-url", args.api_url])
    
    if args.no_color:
        cmd.append("--no-color")
    
    # Add phase-specific arguments
    if phase_key == "ph":
        if args.auto_advance:
            cmd.append("--auto-advance")
        if args.skip_reservoir:
            cmd.append("--skip-reservoir")
    elif phase_key == "ec":
        if args.auto_advance:
            cmd.append("--auto-advance")
        if args.skip_accuracy:
            cmd.append("--skip-accuracy")
    elif phase_key == "pumps":
        if args.auto_advance:
            cmd.append("--auto-advance")
        cmd.append("--skip-guards")  # Skip guards in orchestrated mode
    
    # Run the script
    try:
        start_time = datetime.now()
        
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per phase
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        result["exit_code"] = proc.returncode
        result["success"] = proc.returncode == 0
        result["duration_seconds"] = duration
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
        
        # Try to load the JSON report
        output_path = Path(phase_info["output"])
        if output_path.exists():
            try:
                with open(output_path, 'r') as f:
                    result["report"] = json.load(f)
            except Exception as e:
                result["report_error"] = str(e)
        
        if result["success"]:
            print_status(f"Phase PASSED ({duration:.1f}s)", "success", not args.no_color)
        else:
            print_status(f"Phase FAILED (exit code: {proc.returncode})", "error", not args.no_color)
            
    except subprocess.TimeoutExpired:
        result["exit_code"] = 124
        result["success"] = False
        result["error"] = "Timeout"
        print_status("Phase TIMEOUT", "error", not args.no_color)
        
    except Exception as e:
        result["exit_code"] = 125
        result["success"] = False
        result["error"] = str(e)
        print_status(f"Phase ERROR: {e}", "error", not args.no_color)
    
    return result


def archive_reports(timestamp: str) -> dict:
    """Archive commissioning reports to timestamped directory."""
    archive_dir = Path("docs") / f"commissioning_{timestamp}"
    
    result = {
        "success": False,
        "directory": str(archive_dir),
        "archived_files": [],
    }
    
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Move phase reports
        for phase_info in PHASES.values():
            output_file = Path(phase_info["output"])
            if output_file.exists():
                dest = archive_dir / output_file.name
                output_file.rename(dest)
                result["archived_files"].append(str(dest))
        
        result["success"] = True
        print_status(f"Reports archived to: {archive_dir}", "success")
        
    except Exception as e:
        result["error"] = str(e)
        print_status(f"Failed to archive reports: {e}", "error")
    
    return result


def generate_summary(phases_results: list, output_file: str) -> None:
    """Generate human-readable summary."""
    lines = []
    lines.append("=" * 70)
    lines.append("COMMISSIONING SUMMARY")
    lines.append("=" * 70)
    lines.append("")
    
    # Overall status
    all_success = all(r["success"] for r in phases_results)
    total_phases = len(phases_results)
    passed_phases = sum(1 for r in phases_results if r["success"])
    
    lines.append(f"Overall Status: {'✓ PASSED' if all_success else '✗ FAILED'}")
    lines.append(f"Phases: {passed_phases}/{total_phases} passed")
    lines.append("")
    
    # Phase details
    lines.append("Phase Results:")
    lines.append("-" * 70)
    
    for result in phases_results:
        status = "✓ PASS" if result["success"] else "✗ FAIL"
        exit_code = result.get("exit_code", "N/A")
        duration = result.get("duration_seconds", 0)
        
        lines.append(f"{status}  {result['name']:<30} (exit: {exit_code}, {duration:.1f}s)")
        
        if not result["success"]:
            if "error" in result:
                lines.append(f"       Error: {result['error']}")
    
    lines.append("")
    lines.append("=" * 70)
    
    # Write to file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print_status(f"Summary saved to: {output_file}", "success")
    except Exception as e:
        print_status(f"Failed to save summary: {e}", "error")
    
    # Print to console
    print()
    for line in lines:
        print(line)


def main():
    parser = argparse.ArgumentParser(
        description="Orchestrate all commissioning phases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0: All phases completed successfully
  1-5: Specific phase failed (matches phase number)
  99: Multiple phases failed

Example:
  python commission_all.py
  python commission_all.py --phase sensors
  python commission_all.py --dry-run
  python commission_all.py --continue-on-error
        """
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("RDWC_API_URL", "http://localhost:8080"),
        help="API base URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--phase",
        choices=list(PHASES.keys()),
        help="Run specific phase only"
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Don't abort on phase failure"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without execution"
    )
    parser.add_argument(
        "--auto-advance",
        action="store_true",
        help="Use auto-advance for pH/EC calibration (testing)"
    )
    parser.add_argument(
        "--skip-reservoir",
        action="store_true",
        help="Skip pH reservoir accuracy check"
    )
    parser.add_argument(
        "--skip-accuracy",
        action="store_true",
        help="Skip EC accuracy check"
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Don't archive reports to docs/"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )
    
    args = parser.parse_args()
    
    print_status("=== RDWC Commissioning Orchestrator ===", "info", not args.no_color)
    print_status(f"Version: {SCRIPT_VERSION}", "info", not args.no_color)
    print_status(f"API URL: {args.api_url}", "info", not args.no_color)
    
    if args.dry_run:
        print_status("DRY RUN MODE: No actual execution", "warning", not args.no_color)
    
    # Determine which phases to run
    if args.phase:
        phases_to_run = {args.phase: PHASES[args.phase]}
        print_status(f"Running single phase: {args.phase}", "info", not args.no_color)
    else:
        phases_to_run = PHASES
        print_status(f"Running all {len(PHASES)} phases", "info", not args.no_color)
    
    # Get tools directory
    tools_dir = Path(__file__).parent
    
    # Run phases
    phases_results = []
    
    for phase_key, phase_info in phases_to_run.items():
        result = run_phase(phase_key, phase_info, args, tools_dir)
        phases_results.append(result)
        
        # Check if we should continue
        if not result["success"] and not args.continue_on_error:
            print_status("Aborting due to phase failure", "error", not args.no_color)
            break
    
    # Generate timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Archive reports
    archive_result = None
    if not args.no_archive and not args.dry_run:
        archive_result = archive_reports(timestamp.split('_')[0])  # Date only for directory
    
    # Create comprehensive report
    comprehensive_report = {
        "metadata": {
            "script": "commission_all.py",
            "version": SCRIPT_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "host": get_host_info(),
        },
        "config": {
            "api_url": args.api_url,
            "specific_phase": args.phase,
            "continue_on_error": args.continue_on_error,
            "dry_run": args.dry_run,
        },
        "phases": phases_results,
        "archive": archive_result,
    }
    
    report_file = f"commissioning_report_{timestamp}.json"
    try:
        with open(report_file, 'w') as f:
            json.dump(comprehensive_report, f, indent=2)
        print_status(f"Comprehensive report saved: {report_file}", "success", not args.no_color)
    except Exception as e:
        print_status(f"Failed to save report: {e}", "error", not args.no_color)
    
    # Generate human-readable summary
    summary_file = "commissioning_summary.txt"
    generate_summary(phases_results, summary_file)
    
    # Determine exit code
    failed_phases = [r for r in phases_results if not r["success"]]
    
    if not failed_phases:
        exit_code = 0
    elif len(failed_phases) == 1:
        # Map phase to exit code (1-5)
        phase_keys = list(PHASES.keys())
        failed_phase = failed_phases[0]["phase"]
        exit_code = phase_keys.index(failed_phase) + 1
    else:
        # Multiple failures
        exit_code = 99
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
