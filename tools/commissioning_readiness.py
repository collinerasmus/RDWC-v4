"""Commissioning readiness snapshot.
Runs a subset of endpoint calls (without hardware dependency) using FastAPI TestClient
to produce a JSON summary of current application readiness for physical commissioning.

Safe to run on dev machines (Windows) thanks to light shims similar to test_commissioning_sim.
"""
from __future__ import annotations
import os, sys, types, json, time, argparse
from typing import Any, Dict

# Shims for Windows so smbus2 / fcntl imports succeed when app modules load.
if os.name == 'nt' and 'smbus2' not in sys.modules:
    fake = types.ModuleType('smbus2')
    class SMBus:  # minimal stub
        def __init__(self, bus): self.bus = bus
        def read_byte_data(self, addr, reg): return 0
        def write_byte(self, addr, val): pass
        def close(self): pass
    fake.SMBus = SMBus
    fake.i2c_msg = object
    fake.I2cFunc = object
    sys.modules['smbus2'] = fake
if os.name == 'nt' and 'fcntl' not in sys.modules:
    fcntl_mod = types.ModuleType('fcntl')
    def ioctl(fd, request, arg=0, mutate_flag=True):
        return 0
    fcntl_mod.ioctl = ioctl  # type: ignore
    sys.modules['fcntl'] = fcntl_mod

os.environ.setdefault("CALIB_ENABLE", "1")

from fastapi.testclient import TestClient  # type: ignore
from app.main import app  # type: ignore

client = TestClient(app)

def _get(path: str) -> Dict[str, Any]:
    r = client.get(path)
    return {"ok": r.status_code == 200, "status": r.status_code, "data": r.json() if r.status_code == 200 else r.text}

def _post(path: str, body: Dict[str, Any] | None = None) -> Dict[str, Any]:
    r = client.post(path, json=body) if body is not None else client.post(path)
    return {"ok": r.status_code == 200, "status": r.status_code, "data": r.json() if r.status_code == 200 else r.text}

def summarize() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    relays = _get("/api/relays/status")
    sensors_status = _get("/api/sensors/status")
    sensors_cached = _get("/api/sensors")
    ph_read = _get("/calib/ph/read")
    ph_status = _get("/calib/ph/status")
    ec_status = _get("/api/ec/cal/status")
    pumps = _get("/calib/dose/pumps")
    settings_import = _post("/api/settings/import", {"general.reservoir_liters": "100"})

    # Basic derived acceptance checks
    ph_val = ph_read.get("data", {}).get("value") if ph_read.get("ok") else None
    ph_numeric = isinstance(ph_val, (int, float))
    out["relay_mode"] = relays.get("data", {}).get("mode") if relays.get("ok") else None
    out["estop"] = relays.get("data", {}).get("estop") if relays.get("ok") else None
    out["sensor_poller_running"] = sensors_status.get("data", {}).get("running") if sensors_status.get("ok") else None
    out["sensors_online_flag"] = sensors_cached.get("data", {}).get("online") if sensors_cached.get("ok") else None
    out["ph_value"] = ph_val
    out["ph_numeric"] = ph_numeric
    out["ph_reasonable_range"] = (3.0 <= ph_val <= 9.0) if ph_numeric else False
    out["ph_flags"] = ph_status.get("data", {}).get("flags") if ph_status.get("ok") else None
    out["ec_status_keys"] = sorted(list(ec_status.get("data", {}).keys())) if ec_status.get("ok") else []
    pumps_dict = pumps.get("data") if pumps.get("ok") and isinstance(pumps.get("data"), dict) else {}
    out["pump_ids"] = sorted(list(pumps_dict.keys()))
    out["settings_import_ok"] = settings_import.get("ok") and settings_import.get("data", {}).get("ok")
    out["ts_age_seconds"] = None
    if sensors_cached.get("ok"):
        ts = sensors_cached.get("data", {}).get("ts")
        if isinstance(ts, (int, float)):
            out["ts_age_seconds"] = max(0, int(time.time()) - int(ts))

    out["raw"] = {
        "relays": relays,
        "sensors_status": sensors_status,
        "sensors_cached": sensors_cached,
        "ph_read": ph_read,
        "ph_status": ph_status,
        "ec_status": ec_status,
        "pumps": pumps,
        "settings_import": settings_import,
    }
    return out

def main():
    parser = argparse.ArgumentParser(description="Commissioning readiness snapshot")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON (no raw section)")
    args = parser.parse_args()
    summary = summarize()
    if args.compact:
        compact = {k: v for k, v in summary.items() if k != "raw"}
        print(json.dumps(compact))
    else:
        print(json.dumps(summary, indent=2))
    essential_ok = all([
        summary.get("relay_mode") is not None,
        summary.get("sensor_poller_running") is not None,
        isinstance(summary.get("pump_ids"), list),
    ])
    if not essential_ok:
        print("READINESS: partial (some essentials missing)")
        sys.exit(1)
    print("READINESS: baseline snapshot complete")

if __name__ == "__main__":
    main()