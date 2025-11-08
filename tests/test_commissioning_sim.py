"""Commissioning simulation test: exercises key endpoints with FastAPI TestClient
without requiring physical hardware. Provides a JSON summary similar to
human commissioning acceptance criteria.
"""
import os
import sys
import types
import json
from typing import Dict, Any
from fastapi.testclient import TestClient

# Provide a lightweight smbus2 shim on non-Linux (Windows CI/dev) so imports succeed.
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
    # Provide minimal fcntl shim for endpoints that import it
if os.name == 'nt' and 'fcntl' not in sys.modules:
    fcntl_mod = types.ModuleType('fcntl')
    def ioctl(fd, request, arg=0, mutate_flag=True):
        return 0
    fcntl_mod.ioctl = ioctl  # type: ignore
    sys.modules['fcntl'] = fcntl_mod

os.environ.setdefault("CALIB_ENABLE", "1")

from app.main import app  # type: ignore

client = TestClient(app)
ACCEPT: Dict[str, Any] = {}


def _get(path: str):
    r = client.get(path)
    assert r.status_code == 200, f"GET {path} failed: {r.status_code} {r.text}"
    return r.json()


def _post(path: str, json_body: Dict[str, Any] | None = None):
    r = client.post(path, json=json_body) if json_body is not None else client.post(path)
    assert r.status_code == 200, f"POST {path} failed: {r.status_code} {r.text}"
    return r.json()


def test_commissioning_flow():
    relays = _get("/api/relays/status")
    ACCEPT["relays_mode"] = relays.get("mode")
    ACCEPT["estop"] = relays.get("estop")

    poller = _get("/api/sensors/status")
    sensors_cached = _get("/api/sensors")
    ACCEPT["sensor_poller_running"] = poller.get("running")
    ACCEPT["sensors_online"] = sensors_cached.get("online")

    fix = _post("/fix_ezo")
    ACCEPT["fix_ezo_keys"] = sorted(list(fix.keys()))

    ph_single = _get("/calib/ph/read")
    ph_status = _get("/calib/ph/status")
    ph_stable = _get("/calib/ph/read_stable?timeout_s=8&delta=0.08&min_samples=3&poll_s=2")
    ACCEPT["ph_single"] = ph_single.get("value")
    ACCEPT["ph_flags"] = ph_status.get("flags")
    ACCEPT["ph_stable"] = ph_stable.get("value")
    ACCEPT["ph_stable_samples"] = ph_stable.get("samples")

    ec_status = _get("/api/ec/cal/status")
    ACCEPT["ec_status_keys"] = sorted(list(ec_status.keys()))

    pumps = _get("/calib/dose/pumps")
    ACCEPT["pumps_list"] = sorted(list(pumps.keys())) if isinstance(pumps, dict) else None

    settings_payload = {"general.reservoir_liters": "100"}
    settings_update = _post("/api/settings/import", settings_payload)
    ACCEPT["settings_update_ok"] = settings_update.get("ok", False)

    sensors_final = _get("/api/sensors")
    ACCEPT["final_online"] = sensors_final.get("online")
    ACCEPT["final_ts"] = sensors_final.get("ts")

    ACCEPT["ph_numeric"] = isinstance(ACCEPT["ph_single"], (int, float))
    if isinstance(ACCEPT["ph_single"], (int, float)):
        ACCEPT["ph_in_reasonable_range"] = 3.0 <= ACCEPT["ph_single"] <= 9.0
    else:
        ACCEPT["ph_in_reasonable_range"] = False

    print("\n=== COMMISSIONING SIM SUMMARY ===")
    print(json.dumps(ACCEPT, indent=2))

    assert ACCEPT["relays_mode"] is not None, "Relay mode missing"
    assert isinstance(ACCEPT["pumps_list"], list), "Pumps list missing"
    assert ACCEPT["settings_update_ok"], "Settings import failed"