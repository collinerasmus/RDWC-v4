"""
Sensors API for RDWC v4 (FastAPI)
Provides /api/sensors endpoint with real-time sensor readings
"""
import os
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.sensors_provider import SensorsProvider

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
    """
    data = _get_sensors_data()
    return JSONResponse(content=data, status_code=200)

@sensors_router.get('/sensors/read')
async def get_sensors_read():
    """
    GET /sensors/read
    Shim for legacy frontend - returns same data as /api/sensors
    Always returns 200 OK (even if hardware offline)
    """
    data = _get_sensors_data()
    return JSONResponse(content=data, status_code=200)
