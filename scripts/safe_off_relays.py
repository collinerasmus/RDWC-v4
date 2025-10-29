#!/usr/bin/env python3
"""
RDWC Safe-OFF script - sets all relay GPIOs to safe OFF state
Uses raspi-gpio command for zero-deps operation
"""

import subprocess
import sys

# BCM GPIO pins for all RDWC relays
RELAY_PINS = [5, 6, 13, 19, 26, 16, 20, 21]

def safe_off_all_relays():
    """Set all relay GPIOs to safe OFF state (HIGH for active-low boards)"""
    failed_pins = []
    
    for pin in RELAY_PINS:
        try:
            # Set GPIO to output, drive high (OFF for active-low relay boards)
            result = subprocess.run(
                ['sudo', 'raspi-gpio', 'set', str(pin), 'op', 'dh'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                failed_pins.append(pin)
                print(f"Failed to set GPIO {pin}: {result.stderr.strip()}")
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            failed_pins.append(pin)
            print(f"Error setting GPIO {pin}: {e}")
    
    # Verify and report status
    success_count = len(RELAY_PINS) - len(failed_pins)
    print(f"Safe-OFF complete: {success_count}/{len(RELAY_PINS)} relays OFF, {len(failed_pins)} failed")
    
    if failed_pins:
        print(f"Failed pins: {failed_pins}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(safe_off_all_relays())