#!/usr/bin/env python3
"""UI dose verification test - enable Rapid Test, dose 3 pumps, check logs."""
import urllib.request
import json
import time
import subprocess

BASE = "http://localhost:8080"

def main():
    # Enable Rapid Test Mode (min interval 10s)
    print("[1] Enable Rapid Test Mode (ec.min_interval_sec=10)")
    payload = json.dumps({"ec.min_interval_sec": 10}).encode()
    req = urllib.request.Request(
        BASE + "/api/settings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    resp = urllib.request.urlopen(req).read().decode()
    print("SETTINGS:", resp)
    time.sleep(2)

    # Trigger three 0.4s doses via /api/ec/dose
    def dose(pump):
        print(f"\n[{pump.upper()}] Triggering 0.4s dose...")
        d = json.dumps({
            "pump": pump,
            "seconds": 0.4,
            "reason": "ui-manual",
            "actor": "user"
        }).encode()
        req = urllib.request.Request(
            BASE + "/api/ec/dose",
            data=d,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req).read().decode()
        print("RESPONSE:", resp)

    dose("grow")
    time.sleep(11)
    dose("micro")
    time.sleep(11)
    dose("bloom")

    # Fetch recent doses
    print("\n[RECENT] Fetching last 3 doses:")
    resp = urllib.request.urlopen(BASE + "/api/ec/dose/recent?limit=3").read().decode()
    j = json.loads(resp)
    for e in j["events"]:
        ts = e["ts_iso"]
        pump = e["pump"].upper()
        sec = e["seconds"]
        ml = e["volume_ml"]
        print(f"  {ts} | {pump} | {sec}s | {ml}ml")

    # Check service logs
    print("\n[LOGS] Recent rdwc.service POST /api/ec/dose entries:")
    try:
        log_out = subprocess.check_output(
            ["sudo", "journalctl", "-u", "rdwc.service", "-n", "80", "--no-pager"],
            text=True
        )
        count = 0
        for line in log_out.splitlines():
            if "/api/ec/dose" in line and "POST" in line:
                print("  ", line[-200:])
                count += 1
        print(f"\nFound {count} POST /api/ec/dose log entries")
    except Exception as e:
        print(f"Could not fetch logs: {e}")

if __name__ == "__main__":
    main()
