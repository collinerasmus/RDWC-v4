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
    """Common function to get sensor data"""
    try:
        return _provider.read_all()
    except Exception as e:
        logger.error(f"[SensorsAPI] Unexpected error: {e}")
        # Return safe fallback
        return {
            "temperature_c": None,
            "ec_mscm": None,
            "ph": None,
            "cal": {
                "temp": {"is_calibrated": False, "detail": "error"},
                "ec": {"is_calibrated": False, "detail": "error"},
                "ph": {"is_calibrated": False, "detail": "error"}
            },
            "online": False,
            "ts": None
        }

@sensors_router.get('/sensors')
async def get_sensors():
    """
    GET /api/sensors
    Returns current sensor readings with calibration status
    Always returns 200 OK (even if hardware offline)
    
    Hard timeout enforced at API level to prevent UI freeze.
    """
    timeout_s = float(os.getenv("RDWC_SENSORS_API_TIMEOUT_S", "2.8"))
    
    try:
        # Wrap blocking call in asyncio.to_thread with timeout
        data = await asyncio.wait_for(
            asyncio.to_thread(_get_sensors_data),
            timeout=timeout_s
        )
        return JSONResponse(content=data, status_code=200)
    
    except asyncio.TimeoutError:
        logger.warning(f"[SensorsAPI] Timeout after {timeout_s}s - returning safe fallback")
        # Return safe fallback (always 200 OK)
        data = {
            "temperature_c": None,
            "ec_mscm": None,
            "ph": None,
            "temp_comp_applied": False,
            "temp_comp_reason": "api-timeout",
            "online": False,
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "cal": {
                "temp": {"is_calibrated": False, "detail": "timeout"},
                "ec": {"is_calibrated": False, "detail": "timeout"},
                "ph": {"is_calibrated": False, "detail": "timeout"}
            }
        }
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
