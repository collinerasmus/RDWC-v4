"""Commissioning snapshot blueprint.
Produces an aggregated JSON summary without performing direct hardware reads.
Safe to call frequently; relies on existing cached/db-backed helpers.
"""
from fastapi import APIRouter
import time

router = APIRouter(prefix="/api/commissioning", tags=["commissioning"])

def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default

@router.get("/snapshot")
def commissioning_snapshot():
    from app.relays_core import get_relay_status, get_estop_status
    from app.sensors_core import read_sensors_from_db
    from app.ph_control import ph_status
    from app.ec_control import get_ec_status
    from app.settings import get_all_settings
    # pumps (reuse logic from main calib_dose_pumps without importing main to avoid circular import)
    _PUMP_MAP = {
        "ph_up": "dosing_ph_up",
        "grow": "dosing_grow",
        "micro": "dosing_micro",
        "bloom": "dosing_bloom",
    }
    _RATE_KEY = {
        "ph_up": "dosing.ph_up_ml_per_sec",
        "grow": "dosing.grow_ml_per_sec",
        "micro": "dosing.micro_ml_per_sec",
        "bloom": "dosing.bloom_ml_per_sec",
    }
    settings = _safe(get_all_settings, {})
    pump_rates = {k: float(settings.get(_RATE_KEY[k], "0") or 0) for k in _PUMP_MAP.keys()}
    pumps = [{"key": k, "relay": _PUMP_MAP[k], "ml_per_sec": pump_rates.get(k, 0.0)} for k in _PUMP_MAP]

    relays = _safe(get_relay_status, {})
    estop = _safe(get_estop_status, False)
    sensors = _safe(lambda: read_sensors_from_db(max_age_sec=300), {})
    ph = _safe(ph_status, {})
    ec = _safe(get_ec_status, {})
    now = time.time()
    ts = sensors.get("ts") if isinstance(sensors, dict) else None
    ts_age = (now - ts) if isinstance(ts, (int, float)) else None

    return {
        "ok": True,
        "relay_estop": estop,
        "relay_count": len(relays) if isinstance(relays, dict) else 0,
        "relays": relays,
        "sensors_online": sensors.get("online") if isinstance(sensors, dict) else False,
        "sensors_age_s": int(ts_age) if ts_age is not None else None,
        "ph_flags": ph.get("flags") if isinstance(ph, dict) else [],
        "ph_ok": ph.get("ok") if isinstance(ph, dict) else False,
        "ec_status": ec.get("cal") if isinstance(ec, dict) else None,
        "ec_ok": ec.get("ok") if isinstance(ec, dict) else False,
        "pump_count": len(pumps),
        "pumps": pumps,
        "ts": int(now),
    }