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

@sensors_router.get('/sensors')
async def get_sensors():
    """
    GET /api/sensors
    Returns current sensor readings with calibration status
    Always returns 200 OK (even if hardware offline)
    """
    try:
        data = _provider.read_all()
        return JSONResponse(content=data, status_code=200)
    except Exception as e:
        logger.error(f"[SensorsAPI] Unexpected error: {e}")
        # Return safe fallback
        return JSONResponse(content={
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
        }, status_code=200)
