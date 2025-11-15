"""
Sensors API for RDWC v4 (FastAPI)
Provides /api/sensors endpoint with real-time sensor readings
"""
import os
import asyncio
import datetime
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.sensors_provider import SensorsProvider
from app.services.sensors_fallback import get_last_reading

logger = logging.getLogger(__name__)

sensors_router = APIRouter(prefix="/api", tags=["sensors"])

# Initialize provider once (check env for mock mode)
USE_MOCK = os.getenv('RDWC_SENSORS_MOCK', '0') == '1'
_provider = SensorsProvider(use_mock=USE_MOCK)

logger.info(f"[SensorsAPI] Initialized with mock={USE_MOCK}")

def _get_sensors_data():
    """
    Return sensor data without touching I2C directly.
    Priority:
    1) Cached reading from background loop in app.main (fresh < 60s)
    2) Database fallback via services.sensors_fallback.get_last_reading()
    3) Final safe empty payload

    This guarantees a single place performs I2C reads (the background loop),
    eliminating contention and flakiness when multiple controllers request data.
    """
    try:
        from app.main import _last, _last_t
        age_sec = (datetime.datetime.now(datetime.UTC).timestamp() - _last_t)
        if age_sec < 60 and _last.get("temp_c") is not None:
            # Health state: green (<60s), yellow (60-300s), red (>=300s or offline)
            health_state = "green" if age_sec < 60 else ("yellow" if age_sec < 300 else "red")
            return {
                "temperature_c": _last.get("temp_c"),
                "ec_mscm": _last.get("ec_ms_cm"),
                "ph": _last.get("ph"),
                "online": True,
                "ts": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
                "age_seconds": age_sec,
                "stale": bool(age_sec > 60),
                "health_state": health_state,
                "temp_comp_applied": False,
                "temp_comp_reason": "cached",
                "cal": {
                    "temp": {"is_calibrated": False, "detail": "cached"},
                    "ec": {"is_calibrated": False, "detail": "cached"},
                    "ph": {"is_calibrated": False, "detail": "cached"}
                }
            }
    except Exception as e:
        logger.warning(f"[SensorsAPI] Cache access failed, will try DB fallback: {e}")

    # DB fallback
    try:
        last = get_last_reading()
        if last:
            # Check freshness of DB reading (sensor poller writes every 5s)
            age_sec = last.get("stale_seconds", 9999)
            is_fresh = age_sec < 60
            # Health state: green (<60s), yellow (60-300s), red (>=300s)
            if age_sec < 60:
                health_state = "green"
            elif age_sec < 300:
                health_state = "yellow"
            else:
                health_state = "red"
            return {
                "temperature_c": last.get("temperature_c"),
                "ec_mscm": last.get("ec_mscm"),
                "ph": last.get("ph"),
                "online": is_fresh,
                "ts": last.get("ts"),
                "age_seconds": age_sec,
                "stale": bool(age_sec > 60),
                "health_state": health_state,
                "temp_comp_applied": is_fresh,
                "temp_comp_reason": "sensor_poller" if is_fresh else f"stale-db ({age_sec}s)",
                "cal": {
                    "temp": {"is_calibrated": False, "detail": "db"},
                    "ec": {"is_calibrated": False, "detail": "db"},
                    "ph": {"is_calibrated": False, "detail": "db"}
                }
            }
    except Exception as e:
        logger.error(f"[SensorsAPI] DB fallback failed: {e}")

    # Final safe payload
    return {
        "temperature_c": None,
        "ec_mscm": None,
        "ph": None,
        "online": False,
        "ts": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
        "age_seconds": None,
        "stale": True,
        "health_state": "red",
        "temp_comp_applied": False,
        "temp_comp_reason": "no-data",
        "cal": {
            "temp": {"is_calibrated": False, "detail": "none"},
            "ec": {"is_calibrated": False, "detail": "none"},
            "ph": {"is_calibrated": False, "detail": "none"}
        }
    }

@sensors_router.get('/sensors')
async def get_sensors():
    """
    GET /api/sensors
    Unified sensors endpoint that always reads from the DB cache written by the
    background poller and applies maintenance overrides when active.
    This avoids direct I²C access and ensures consistent mode/override behavior.
    """
    try:
        from app.sensors_core import read_sensors_from_db
        d = read_sensors_from_db(max_age_sec=60)
        age_sec = d.get("age_sec")
        online = d.get("online", False)
        if online and age_sec is not None and age_sec < 60:
            health_state = "green"
        elif online and age_sec is not None and age_sec < 300:
            health_state = "yellow"
        else:
            health_state = "red"

        result = {
            "temperature_c": d.get("temperature_c"),
            "ec_mscm": d.get("ec_mscm"),
            "ph": d.get("ph"),
            "online": online,
            "ts": d.get("ts"),
            "age_seconds": age_sec,
            "stale": bool(age_sec is not None and age_sec > 60),
            "health_state": health_state,
            "temp_comp_applied": online,
            "temp_comp_reason": "sensor_poller" if online else f"stale (age:{d.get('age_sec','?')}s)",
            # Calibration placeholder for UI
            "cal": {
                "temp": {"is_calibrated": False, "detail": "db"},
                "ec": {"is_calibrated": False, "detail": "db"},
                "ph": {"is_calibrated": False, "detail": "db"}
            },
            # Mode/overrides and original/effective echo for diagnostics/UI
            "mode": d.get("mode"),
            "overrides": d.get("overrides", {}),
            "original_temperature_c": d.get("original_temperature_c"),
            "original_ph": d.get("original_ph"),
            "original_ec_mscm": d.get("original_ec_mscm"),
            "effective_temperature_c": d.get("temperature_c"),
            "effective_ph": d.get("ph"),
            "effective_ec_mscm": d.get("ec_mscm"),
        }
        return JSONResponse(content=result, status_code=200)
    except Exception as e:
        logger.error(f"[SensorsAPI] unified read failed: {e}")
        # Fallback to previous behavior
        data = _get_sensors_data()
        return JSONResponse(content=data, status_code=200)

@sensors_router.get('/sensors/last')
async def api_sensors_last():
    """
    GET /api/sensors/last
    Returns the most recent sensor reading from database (stale fallback).
    Used when live sensors are offline to show last known values.
    """
    data = await asyncio.to_thread(get_last_reading)
    return data or {
        "temperature_c": None,
        "ec_mscm": None,
        "ph": None,
        "ts": None,
        "stale_seconds": None,
        "online": False,
        "temp_comp_applied": False,
        "temp_comp_reason": "fallback-empty"
    }
