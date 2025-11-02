#!/usr/bin/env python3
import argparse
import json
import sys
import time
from datetime import datetime

import requests

API = "http://localhost:8080"

def get_relays():
    try:
        r = requests.get(f"{API}/api/relays/status", timeout=5)
        r.raise_for_status()
        return r.json().get("relays", {})
    except Exception as e:
        return {"_error": str(e)}


def dose_ec(amount_ml: float, mode: str = "schedule"):
    # Matches backend contract: { ml, mix_ratio, custom? }
    r = requests.post(f"{API}/api/ec/dose", json={"ml": amount_ml, "mix_ratio": mode}, timeout=30)
    return r.status_code, (r.json() if r.headers.get("content-type","" ).startswith("application/json") else r.text)


def get_ec_log_latest():
    r = requests.get(f"{API}/api/ec/dose_log?limit=1", timeout=5)
    if r.ok:
        data = r.json()
        return data[0] if data else None
    return None


def main():
    p = argparse.ArgumentParser(description="Verify EC dosing and relay actuation")
    p.add_argument("--ec", type=float, default=5.0, help="EC test dose in ml (default 5.0)")
    p.add_argument("--sleep", type=float, default=0.5, help="Polling interval for relays while dosing")
    args = p.parse_args()

    print("== RDWC Dosing Verification ==")
    print("Time:", datetime.now().isoformat())

    # Snapshot relays before
    print("\nRelays BEFORE:")
    before = get_relays()
    print(json.dumps(before, indent=2))

    # Trigger dose
    print(f"\nTriggering EC dose: {args.ec} ml (schedule)")
    code, resp = dose_ec(args.ec, "schedule")
    print("Response code:", code)
    print("Response:", json.dumps(resp, indent=2) if isinstance(resp, dict) else resp)

    # Poll relays for a few seconds to catch on/off events
    print("\nPolling relays for activity (6s)...")
    for i in range(12):
        st = get_relays()
        active = {k:v for k,v in st.items() if isinstance(v, dict) and v.get("is_on")}
        print(f"t+{i*args.sleep:.1f}s on:", list(active.keys()))
        time.sleep(args.sleep)

    # Snapshot relays after
    print("\nRelays AFTER:")
    after = get_relays()
    print(json.dumps(after, indent=2))

    # Check latest EC log
    print("\nLatest EC dose log entry:")
    last = get_ec_log_latest()
    print(json.dumps(last, indent=2))

    # Simple pass criteria
    ok = False
    if isinstance(resp, dict) and resp.get("ok"):
        ok = True
    if last and last.get("volume_ml"):
        ok = True

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
