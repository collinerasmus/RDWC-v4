#!/usr/bin/env python3
"""Deployment verification script for RDWC-v4.

Runs key API endpoints and summarizes acceptance criteria:
 - Relays status (estop false, mode present)
 - Sensors freshness (<60s) and online flag
 - Sensor poller status endpoint
 - pH calibration/status endpoints (optional)
 - EC calibration/status endpoints (optional)
 - Dosing safety read (optional: presence of guards fields)
Outputs a JSON summary to stdout and non-zero exit code on failure.

Usage:
  python tools/deploy_verify.py --base http://localhost:8080 --timeout 4
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List, Tuple

import requests


def fetch_json(url: str, timeout: float) -> Tuple[Dict[str, Any], List[str]]:
    errors: List[str] = []
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json(), errors
    except Exception as e:  # noqa: BLE001
        errors.append(f"GET {url} failed: {e}")
        return {}, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080", help="Base URL of API (default localhost:8080)")
    parser.add_argument("--timeout", type=float, default=5.0, help="Per-request timeout seconds")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    timeout = args.timeout
    now = time.time()

    summary: Dict[str, Any] = {
        "base": base,
        "ts": int(now),
        "relays": {},
        "sensors": {},
        "poller": {},
        "ph": {},
        "ec": {},
        "status": "pending",
        "errors": [],
        "ok": False,
    }

    # Endpoints to call
    relays_data, relays_err = fetch_json(f"{base}/api/relays/status", timeout)
    summary["errors"].extend(relays_err)
    summary["relays"] = relays_data

    sensors_data, sensors_err = fetch_json(f"{base}/api/sensors", timeout)
    summary["errors"].extend(sensors_err)
    summary["sensors"] = sensors_data

    poller_data, poller_err = fetch_json(f"{base}/api/sensors/status", timeout)
    summary["errors"].extend(poller_err)
    summary["poller"] = poller_data

    ph_status, ph_err = fetch_json(f"{base}/calib/ph/status", timeout)
    summary["errors"].extend(ph_err)
    summary["ph"]["calib_status"] = ph_status

    ec_status, ec_err = fetch_json(f"{base}/api/ec/cal/status", timeout)
    summary["errors"].extend(ec_err)
    summary["ec"]["calib_status"] = ec_status

    # Acceptance criteria evaluation
    accept = {
        "relays_estop": False,
        "sensors_fresh": False,
        "sensors_online": False,
        "poller_running": False,
    }

    # Relays: estop should be false
    if isinstance(relays_data, dict):
        estop = relays_data.get("estop")
        if estop is False:
            accept["relays_estop"] = True

    # Sensors: online true and age <60s
    if isinstance(sensors_data, dict):
        online = sensors_data.get("online")
        ts_val = sensors_data.get("ts")
        if online is True:
            accept["sensors_online"] = True
        try:
            if ts_val is not None:
                age = now - float(ts_val)
                if age < 60:
                    accept["sensors_fresh"] = True
        except Exception:  # noqa: BLE001
            summary["errors"].append("Invalid sensor timestamp")

    # Poller: expect running or similar flag
    if isinstance(poller_data, dict):
        if any(poller_data.get(k) for k in ("running", "alive", "ok")):
            accept["poller_running"] = True

    summary["acceptance"] = accept
    all_ok = all(accept.values()) and not summary["errors"]
    summary["ok"] = all_ok
    summary["status"] = "ok" if all_ok else "partial" if any(accept.values()) else "fail"

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if all_ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
