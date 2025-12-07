"""
Sensors Provider for RDWC v4
Reads temperature, EC, and pH from Atlas EZO sensors via I2C
Supports mock mode for development/testing

NOTE: This provider does NOT access I2C directly. All I2C operations are routed
through app.sensor_controller, which is the single source of truth for sensor I/O.
This ensures no race conditions from concurrent reads.
"""
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Atlas EZO I2C default addresses (for reference only - actual I/O is in sensor_controller)
ADDR_RTD = 0x66  # Temperature (RTD)
ADDR_EC = 0x64   # Electrical Conductivity
ADDR_PH = 0x63   # pH

class SensorsProvider:
    """
    Provides sensor readings from Atlas EZO devices via sensor_controller
    Falls back to mock data if hardware unavailable
    
    Architecture:
    - Never accesses I2C directly
    - Routes all reads through app.sensor_controller
    - Provides cached/DB fallback for resilience
    """
    
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        # No longer storing ezo reference - all access goes through sensor_controller
    
    def read_all(self) -> Dict[str, Any]:
        """
        Read sensors in a contention-free way:
        - Prefer cached reading from app.main background loop (fresh <60s)
        - Otherwise fall back to last DB reading
        - Never touches I2C directly here
        """
        try:
            # Try cached background reading
            from app.main import _last, _last_t
            import time
            age = time.time() - _last_t
            if age < 60 and _last.get("temp_c") is not None:
                return {
                    "temperature_c": _last.get("temp_c"),
                    "ec_mscm": _last.get("ec_ms_cm"),
                    "ph": _last.get("ph"),
                    "temp_comp_applied": False,
                    "temp_comp_reason": "cached",
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "online": True,
                    "cal": {
                        "temp": {"is_calibrated": False, "detail": "cached"},
                        "ec": {"is_calibrated": False, "detail": "cached"},
                        "ph": {"is_calibrated": False, "detail": "cached"}
                    }
                }
        except Exception as e:
            logger.warning(f"[SensorsProvider] Cache read failed: {e}")

        # DB fallback
        try:
            from app.services.sensors_fallback import get_last_reading
            last = get_last_reading()
            if last:
                return {
                    "temperature_c": last.get("temperature_c"),
                    "ec_mscm": last.get("ec_mscm"),
                    "ph": last.get("ph"),
                    "temp_comp_applied": False,
                    "temp_comp_reason": "fallback-db",
                    "ts": last.get("ts"),
                    "online": False,
                    "cal": {
                        "temp": {"is_calibrated": False, "detail": "fallback"},
                        "ec": {"is_calibrated": False, "detail": "fallback"},
                        "ph": {"is_calibrated": False, "detail": "fallback"}
                    }
                }
        except Exception as e:
            logger.error(f"[SensorsProvider] DB fallback failed: {e}")

        # Final safe payload
        return {
            "temperature_c": None,
            "ec_mscm": None,
            "ph": None,
            "temp_comp_applied": False,
            "temp_comp_reason": "no-data",
            "ts": datetime.utcnow().isoformat() + "Z",
            "online": False,
            "cal": {
                "temp": {"is_calibrated": False, "detail": "none"},
                "ec": {"is_calibrated": False, "detail": "none"},
                "ph": {"is_calibrated": False, "detail": "none"}
            }
        }
    
    def mock_read_all(self) -> Dict[str, Any]:
        """Return stable mock data for development"""
        return {
            "temperature_c": 22.4,
            "ec_mscm": 1.62,
            "ph": 5.86,
            "temp_comp_applied": False,  # Mock doesn't do real temp comp
            "cal": {
                "temp": {"is_calibrated": True, "detail": "mock"},
                "ec": {"is_calibrated": True, "detail": "mock"},
                "ph": {"is_calibrated": True, "detail": "mock"}
            },
            "online": True,
            "ts": datetime.utcnow().isoformat() + "Z"
        }
