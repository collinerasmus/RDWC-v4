#!/usr/bin/env python3
"""Unified system commissioning orchestrator.

This script guides you through the complete commissioning process for the RDWC-v4 system.
It runs each commissioning phase in sequence and generates a comprehensive report.

Phases:
  1. Baseline System Validation (sensors, relays, E-STOP)
  2. Sensor Calibration (pH 3-point, EC 1-point)
  3. Dosing Pump Calibration (all pumps: pH Up/Down, Nutrient A/B)
  4. Integration Testing (modes, cooldowns, guards)
  5. Final Report Generation

Usage:
  python tools/commission_system.py [--phase PHASE] [--skip-phase PHASE] [--auto]
  
Examples:
  # Run complete commissioning sequence (interactive)
  python tools/commission_system.py
  
  # Run only specific phase
  python tools/commission_system.py --phase sensors
  
  # Skip certain phases
  python tools/commission_system.py --skip-phase pumps
  
  # Auto-advance (non-interactive, for testing)
  python tools/commission_system.py --auto

Exit Codes:
  0: Commissioning completed successfully
  1: Phase failed - see report for details
  2: Prerequisites not met
  3: User cancelled
"""
import sys
import os
import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from commission_utils import (
    APIClient, APIError, create_report, save_report,
    print_status
)

SCRIPT_VERSION = "1.0.0"

# Phase configuration
PHASES = {
    "sensors": {
        "name": "Sensor Health & Validation",
        "script": "commission_sensors.py",
        "description": "Validates I²C sensors, poller service, freshness, and health states",
        "required": True,
    },
    "relays": {
        "name": "Relay Safety Systems",
        "script": "commission_relays.py",
        "description": "Tests E-STOP, mode transitions, cooldown enforcement",
        "required": True,
    },
    "ph": {
        "name": "pH Calibration",
        "script": "commission_ph.py",
        "description": "3-point pH calibration (mid/low/high buffers)",
        "required": False,
    },
    "ec": {
        "name": "EC Calibration",
        "script": "commission_ec.py",
        "description": "EC K-value and 1-point calibration (1413 µS/cm)",
        "required": False,
    },
    "pumps": {
        "name": "Dosing Pump Calibration",
        "script": "commission_pumps.py",
        "description": "Calibrate all dosing pumps and verify safety guards",
        "required": False,
    },
}

PHASE_ORDER = ["sensors", "relays", "ph", "ec", "pumps"]


class CommissioningOrchestrator:
    """Orchestrates the complete commissioning process."""
    
    def __init__(self, api_url: str, output_dir: str, auto_mode: bool = False):
        self.api_url = api_url
        self.output_dir = Path(output_dir)
        self.auto_mode = auto_mode
        self.client = APIClient(base_url=api_url)
        self.results: Dict[str, Any] = {}
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def print_header(self):
        """Print commissioning header."""
        print()
        print("=" * 70)
        print("  RDWC-v4 SYSTEM COMMISSIONING ORCHESTRATOR")
        print("=" * 70)
        print(f"  Version: {SCRIPT_VERSION}")
        print(f"  API URL: {self.api_url}")
        print(f"  Output Directory: {self.output_dir}")
        print(f"  Mode: {'Auto (non-interactive)' if self.auto_mode else 'Interactive'}")
        print("=" * 70)
        print()
    
    def print_phase_list(self):
        """Print list of commissioning phases."""
        print("Commissioning Phases:")
        print()
        for idx, phase_id in enumerate(PHASE_ORDER, 1):
            phase = PHASES[phase_id]
            required = " [REQUIRED]" if phase["required"] else " [OPTIONAL]"
            print(f"  {idx}. {phase['name']}{required}")
            print(f"     {phase['description']}")
            print()
    
    def check_prerequisites(self) -> bool:
        """Check if system is ready for commissioning."""
        print_status("=== Checking Prerequisites ===", "info")
        
        checks = []
        
        # 1. API reachable
        try:
            response = self.client.get("/api/version")
            version = response.json().get("version", "unknown")
            print_status(f"API reachable (version: {version})", "success")
            checks.append(True)
        except APIError as e:
            print_status(f"API not reachable: {e}", "error")
            checks.append(False)
        
        # 2. E-STOP status
        try:
            response = self.client.get("/api/relays/status")
            estop = response.json().get("estop", True)
            if estop:
                print_status("E-STOP is ACTIVE - must be disabled for commissioning", "error")
                checks.append(False)
            else:
                print_status("E-STOP is inactive", "success")
                checks.append(True)
        except APIError as e:
            print_status(f"Cannot check E-STOP status: {e}", "error")
            checks.append(False)
        
        # 3. Sensor poller
        try:
            response = self.client.get("/api/sensors/status")
            running = response.json().get("running", False)
            if running:
                print_status("Sensor poller is running", "success")
                checks.append(True)
            else:
                print_status("Sensor poller is NOT running", "warning")
                print_status("  You can continue, but sensor tests may fail", "warning")
                checks.append(True)  # Non-blocking warning
        except APIError as e:
            print_status(f"Cannot check sensor poller: {e}", "error")
            checks.append(False)
        
        print()
        return all(checks)
    
    def prompt_continue(self, message: str = "Continue?") -> bool:
        """Prompt user to continue (returns True in auto mode)."""
        if self.auto_mode:
            return True
        
        response = input(f"\n{message} (y/n): ").strip().lower()
        return response in ["y", "yes"]
    
    def run_phase(self, phase_id: str) -> Dict[str, Any]:
        """Run a single commissioning phase."""
        phase = PHASES[phase_id]
        
        print()
        print("=" * 70)
        print(f"  PHASE: {phase['name']}")
        print("=" * 70)
        print(f"  {phase['description']}")
        print("=" * 70)
        print()
        
        if not self.auto_mode:
            if not self.prompt_continue(f"Ready to start {phase['name']}?"):
                return {
                    "phase": phase_id,
                    "skipped": True,
                    "reason": "User cancelled",
                }
        
        # Run the phase script
        script_path = Path(__file__).parent / phase["script"]
        output_file = self.output_dir / f"{phase_id}_{self.timestamp}.json"
        
        print_status(f"Running {phase['script']}...", "info")
        print()
        
        import subprocess
        cmd = [
            sys.executable,
            str(script_path),
            "--api-url", self.api_url,
            "--output", str(output_file),
        ]
        
        # Add auto-advance flags for specific phases
        if self.auto_mode:
            if phase_id == "ph":
                cmd.extend(["--auto-advance", "--skip-reservoir"])
            elif phase_id == "ec":
                cmd.extend(["--auto-advance", "--skip-accuracy"])
            elif phase_id == "pumps":
                cmd.extend(["--skip-guards", "--auto-advance"])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=False,
                text=True,
                timeout=300,  # 5 minute timeout per phase
            )
            
            # Load the report
            if output_file.exists():
                with open(output_file, 'r') as f:
                    report = json.load(f)
            else:
                report = {}
            
            return {
                "phase": phase_id,
                "exit_code": result.returncode,
                "success": result.returncode == 0,
                "report_file": str(output_file),
                "report": report,
            }
            
        except subprocess.TimeoutExpired:
            print_status(f"Phase {phase_id} timed out!", "error")
            return {
                "phase": phase_id,
                "exit_code": -1,
                "success": False,
                "error": "Timeout after 5 minutes",
            }
        except Exception as e:
            print_status(f"Phase {phase_id} failed: {e}", "error")
            return {
                "phase": phase_id,
                "exit_code": -1,
                "success": False,
                "error": str(e),
            }
    
    def generate_final_report(self) -> Dict[str, Any]:
        """Generate final commissioning report."""
        print()
        print("=" * 70)
        print("  GENERATING FINAL REPORT")
        print("=" * 70)
        print()
        
        # Get final system snapshot
        try:
            response = self.client.get("/api/commissioning/snapshot")
            snapshot = response.json()
        except:
            snapshot = {}
        
        # Summarize results
        summary = {
            "timestamp": datetime.now().isoformat(),
            "api_url": self.api_url,
            "phases_completed": len([r for r in self.results.values() if r.get("success")]),
            "phases_failed": len([r for r in self.results.values() if not r.get("success") and not r.get("skipped")]),
            "phases_skipped": len([r for r in self.results.values() if r.get("skipped")]),
            "overall_success": all(
                r.get("success") or r.get("skipped") or not PHASES[r["phase"]]["required"]
                for r in self.results.values()
            ),
        }
        
        report = {
            "script": "commission_system.py",
            "version": SCRIPT_VERSION,
            "summary": summary,
            "phase_results": self.results,
            "final_snapshot": snapshot,
        }
        
        # Save final report
        final_report_file = self.output_dir / f"commissioning_final_{self.timestamp}.json"
        save_report(report, str(final_report_file))
        
        # Print summary
        print()
        print("=" * 70)
        print("  COMMISSIONING SUMMARY")
        print("=" * 70)
        print(f"  Completed: {summary['phases_completed']}")
        print(f"  Failed:    {summary['phases_failed']}")
        print(f"  Skipped:   {summary['phases_skipped']}")
        print(f"  Overall:   {'✓ SUCCESS' if summary['overall_success'] else '✗ FAILED'}")
        print("=" * 70)
        print()
        print(f"Final report: {final_report_file}")
        print()
        
        return report
    
    def run(self, phases_to_run: Optional[List[str]] = None, phases_to_skip: Optional[List[str]] = None) -> int:
        """Run the commissioning process."""
        self.print_header()
        self.print_phase_list()
        
        # Check prerequisites
        if not self.check_prerequisites():
            print_status("Prerequisites not met!", "error")
            return 2
        
        if not self.auto_mode:
            if not self.prompt_continue("Start commissioning?"):
                print_status("Commissioning cancelled by user", "warning")
                return 3
        
        # Determine which phases to run
        if phases_to_run:
            phases = [p for p in phases_to_run if p in PHASES]
        else:
            phases = PHASE_ORDER
        
        if phases_to_skip:
            phases = [p for p in phases if p not in phases_to_skip]
        
        # Run each phase
        for phase_id in phases:
            result = self.run_phase(phase_id)
            self.results[phase_id] = result
            
            # Check if phase failed and is required
            if not result.get("success") and not result.get("skipped") and PHASES[phase_id]["required"]:
                print_status(f"Required phase {phase_id} failed!", "error")
                if not self.auto_mode:
                    if not self.prompt_continue("Continue anyway?"):
                        break
        
        # Generate final report
        final_report = self.generate_final_report()
        
        # Return exit code
        if final_report["summary"]["overall_success"]:
            return 0
        else:
            return 1
    
    def close(self):
        """Clean up resources."""
        self.client.close()


def main():
    parser = argparse.ArgumentParser(
        description="Unified system commissioning orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commissioning Phases:
  sensors - Sensor health and validation (REQUIRED)
  relays  - Relay safety systems (REQUIRED)
  ph      - pH calibration (optional)
  ec      - EC calibration (optional)
  pumps   - Dosing pump calibration (optional)

Examples:
  # Run complete commissioning
  python commission_system.py
  
  # Run only sensors and relays
  python commission_system.py --phase sensors --phase relays
  
  # Skip pump calibration
  python commission_system.py --skip-phase pumps
  
  # Auto mode (non-interactive)
  python commission_system.py --auto
        """
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("RDWC_API_URL", "http://localhost:8080"),
        help="API base URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--output-dir",
        default="commissioning_reports",
        help="Output directory for reports (default: commissioning_reports)"
    )
    parser.add_argument(
        "--phase",
        action="append",
        choices=list(PHASES.keys()),
        help="Run only specific phase(s) (can be specified multiple times)"
    )
    parser.add_argument(
        "--skip-phase",
        action="append",
        choices=list(PHASES.keys()),
        help="Skip specific phase(s) (can be specified multiple times)"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto mode (non-interactive, skips prompts)"
    )
    
    args = parser.parse_args()
    
    orchestrator = CommissioningOrchestrator(
        api_url=args.api_url,
        output_dir=args.output_dir,
        auto_mode=args.auto,
    )
    
    try:
        exit_code = orchestrator.run(
            phases_to_run=args.phase,
            phases_to_skip=args.skip_phase,
        )
    finally:
        orchestrator.close()
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
