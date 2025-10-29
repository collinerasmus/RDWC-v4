#!/usr/bin/env python3
"""
RDWC Health Guard - monitors API health and takes corrective action
Polls /health endpoint and triggers safe-off + restart if unhealthy
"""

import subprocess
import sys
import time
import urllib.request
import urllib.error

HEALTH_URL = "http://127.0.0.1:8080/health"
MAX_ATTEMPTS = 6
POLL_INTERVAL = 5  # seconds

def check_health():
    """Check if RDWC API health endpoint responds with 200"""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False

def safe_off_and_restart():
    """Execute safe-off script and restart the service"""
    print("API unhealthy, executing safe-off and restart sequence...")
    
    # Run safe-off script
    try:
        result = subprocess.run([
            '/usr/bin/python3', 
            '/home/pi/RDWC-v4/scripts/safe_off_relays.py'
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("Safe-off completed successfully")
        else:
            print(f"Safe-off warnings: {result.stdout}")
    except subprocess.TimeoutExpired:
        print("Safe-off script timed out")
    except Exception as e:
        print(f"Error running safe-off script: {e}")
    
    # Restart the service
    try:
        result = subprocess.run([
            'sudo', 'systemctl', 'restart', 'rdwc.service'
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("Service restart initiated")
        else:
            print(f"Service restart failed: {result.stderr}")
    except Exception as e:
        print(f"Error restarting service: {e}")

def main():
    """Main health guard loop"""
    print(f"Health guard starting - checking {HEALTH_URL}")
    
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"Health check {attempt}/{MAX_ATTEMPTS}...")
        
        if check_health():
            print("API is healthy ✅")
            return 0
        
        if attempt < MAX_ATTEMPTS:
            print(f"API unhealthy, waiting {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)
    
    print(f"API failed {MAX_ATTEMPTS} health checks - taking corrective action")
    safe_off_and_restart()
    
    # Always return 0 to prevent restart loops
    return 0

if __name__ == "__main__":
    sys.exit(main())