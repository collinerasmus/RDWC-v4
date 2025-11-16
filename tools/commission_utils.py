"""Shared utilities for commissioning scripts.

Provides common functionality:
- API client with retry logic
- JSON output helpers
- Progress indicators
- Error handling
"""
import os
import sys
import time
import json
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urljoin

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("Error: 'requests' library not found. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class APIClient:
    """HTTP client with retry logic for RDWC API."""
    
    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        self.base_url = base_url or os.environ.get("RDWC_API_URL", "http://localhost:8080")
        self.timeout = timeout
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def get(self, path: str, **kwargs) -> requests.Response:
        """GET request with error handling."""
        url = urljoin(self.base_url, path)
        kwargs.setdefault('timeout', self.timeout)
        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            raise APIError(f"GET {path} failed: {e}")
    
    def post(self, path: str, json_data: Optional[Dict] = None, **kwargs) -> requests.Response:
        """POST request with error handling."""
        url = urljoin(self.base_url, path)
        kwargs.setdefault('timeout', self.timeout)
        try:
            response = self.session.post(url, json=json_data, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            raise APIError(f"POST {path} failed: {e}")
    
    def close(self):
        """Close session."""
        self.session.close()


class APIError(Exception):
    """API request error."""
    pass


def get_host_info() -> Dict[str, Any]:
    """Get system information for metadata."""
    return {
        "hostname": socket.gethostname(),
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
    }


def create_report(
    script_name: str,
    version: str,
    config: Dict[str, Any],
    results: Dict[str, Any],
    errors: Optional[list] = None,
    recommendations: Optional[list] = None
) -> Dict[str, Any]:
    """Create standardized JSON report structure."""
    return {
        "metadata": {
            "script": script_name,
            "version": version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "host": get_host_info(),
        },
        "config": config,
        "results": results,
        "errors": errors or [],
        "recommendations": recommendations or [],
    }


def save_report(report: Dict[str, Any], filename: str) -> None:
    """Save report to JSON file."""
    try:
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to: {filename}")
    except Exception as e:
        print(f"Warning: Failed to save report: {e}", file=sys.stderr)


def print_status(message: str, status: str = "info", use_color: bool = True):
    """Print status message with optional color."""
    if RICH_AVAILABLE and use_color:
        console = Console()
        if status == "success":
            console.print(f"[green]✓[/green] {message}")
        elif status == "error":
            console.print(f"[red]✗[/red] {message}")
        elif status == "warning":
            console.print(f"[yellow]⚠[/yellow] {message}")
        else:
            console.print(f"[blue]ℹ[/blue] {message}")
    else:
        prefix = {"success": "[OK]", "error": "[ERROR]", "warning": "[WARN]", "info": "[INFO]"}
        print(f"{prefix.get(status, '[INFO]')} {message}")


def wait_for_stability(
    client: APIClient,
    read_endpoint: str,
    value_key: str,
    threshold: float,
    timeout_s: int = 45,
    check_interval: int = 3,
    use_color: bool = True
) -> tuple[bool, Optional[float], list]:
    """Wait for sensor reading to stabilize.
    
    Returns: (success, final_value, readings_history)
    """
    print_status(f"Waiting for stability (threshold: ±{threshold}, timeout: {timeout_s}s)...", "info", use_color)
    
    readings = []
    start_time = time.time()
    
    while time.time() - start_time < timeout_s:
        try:
            response = client.get(read_endpoint)
            data = response.json()
            value = data.get(value_key)
            
            if value is None:
                print_status(f"No value returned from {read_endpoint}", "warning", use_color)
                time.sleep(check_interval)
                continue
            
            readings.append({"timestamp": time.time(), "value": value})
            
            # Check stability once we have enough readings
            if len(readings) >= 3:
                recent = [r["value"] for r in readings[-3:]]
                value_range = max(recent) - min(recent)
                
                if value_range <= threshold:
                    print_status(f"Stable reading: {value:.2f} (range: ±{value_range:.3f})", "success", use_color)
                    return True, value, readings
            
            if len(readings) > 1:
                print(f"  Current: {value:.2f} (readings: {len(readings)})", end="\r")
            
            time.sleep(check_interval)
            
        except Exception as e:
            print_status(f"Error reading value: {e}", "warning", use_color)
            time.sleep(check_interval)
    
    print()
    print_status(f"Timeout waiting for stability after {timeout_s}s", "error", use_color)
    return False, readings[-1]["value"] if readings else None, readings


def prompt_user(message: str, auto_advance: bool = False) -> bool:
    """Interactive prompt with auto-advance support."""
    if auto_advance:
        print(f"{message} [auto-advance: yes]")
        return True
    
    while True:
        response = input(f"{message} (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        print("Please enter 'y' or 'n'")
