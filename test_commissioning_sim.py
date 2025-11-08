"""Commissioning simulation test: exercises key endpoints with FastAPI TestClient
without requiring physical hardware. Provides a JSON summary similar to
human commissioning acceptance criteria.
"""
import os
import json
from typing import Dict, Any
from fastapi.testclient import TestClient

# Ensure calibration writes allowed for test
os.environ.setdefault("CALIB_ENABLE", "1")

# Import app
from app.main import app  # type: ignore

client = TestClient(app)

ACCEPT: Dict[str, Any] = {}


def get(path: str):
    r = client.get(path)
    assert r.status_code == 200, f"GET {path} failed: {r.status_code} {r.text}"  # basic check
    return r.json()


def post(path: str, json_body: Dict[str, Any] | None = None):
    r = client.post(path, json=json_body) if json_body is not None else client.post(path)
    assert r.status_code == 200, f"POST {path} failed: {r.status_code} {r.text}"  # basic check
    return r.json()


def test_commissioning_flow():
    # 1 Relays/estop
    relays = get("/api/relays/status")
    ACCEPT["relays_mode"] = relays.get("mode")
    ACCEPT["estop"] = relays.get("estop")

    # 2 Sensor poller status + cached sensors
    poller = get("/api/sensors/status")
    sensors_cached = get("/api/sensors")
    ACCEPT["sensor_poller_running"] = poller.get("running")
    ACCEPT["sensors_online"] = sensors_cached.get("online")

    # 3 fix_ezo (identification + read_all)
    fix = post("/fix_ezo")
    ACCEPT["fix_ezo_keys"] = sorted(list(fix.keys()))

    # 4 pH reads
    ph_single = get("/calib/ph/read")
    ph_status = get("/calib/ph/status")
    ph_stable = get("/calib/ph/read_stable?timeout_s=8&delta=0.08&min_samples=3&poll_s=2")
    ACCEPT["ph_single"] = ph_single.get("value")
    ACCEPT["ph_flags"] = ph_status.get("flags")
    ACCEPT["ph_stable"] = ph_stable.get("value")
    ACCEPT["ph_stable_samples"] = ph_stable.get("samples")

    # 5 EC calibration status (non-destructive)
    ec_status = get("/api/ec/cal/status")
    ACCEPT["ec_status_keys"] = sorted(list(ec_status.keys()))

    # 6 Dosing pumps listing (no actuation)
    pumps = get("/calib/dose/pumps")
    ACCEPT["pumps_list"] = sorted(list(pumps.keys())) if isinstance(pumps, dict) else None

    # 7 Settings update (reservoir volume) + verify
    settings_payload = {"general.reservoir_liters": "100"}
    settings_update = post("/api/settings/import", settings_payload)
    ACCEPT["settings_update_ok"] = settings_update.get("ok", False)

    # 8 Final sensors snapshot
    sensors_final = get("/api/sensors")
    ACCEPT["final_online"] = sensors_final.get("online")
    ACCEPT["final_ts"] = sensors_final.get("ts")

    # Basic acceptance heuristics (non-failing if missing real hardware)
    ACCEPT["ph_numeric"] = isinstance(ACCEPT["ph_single"], (int, float))
    # pH range broad since simulation or stale may produce defaults
    if isinstance(ACCEPT["ph_single"], (int, float)):
        ACCEPT["ph_in_reasonable_range"] = 3.0 <= ACCEPT["ph_single"] <= 9.0
    else:
        ACCEPT["ph_in_reasonable_range"] = False

    # Print summary for developer
    print("\n=== COMMISSIONING SIM SUMMARY ===")
    print(json.dumps(ACCEPT, indent=2))

    # Assert critical structural keys (not sensor correctness)
    assert ACCEPT["relays_mode"] is not None, "Relay mode missing"
    assert isinstance(ACCEPT["pumps_list"], list), "Pumps list missing"
    assert ACCEPT["settings_update_ok"], "Settings import failed"


if __name__ == "__main__":  # Allow standalone run
    test_commissioning_flow()