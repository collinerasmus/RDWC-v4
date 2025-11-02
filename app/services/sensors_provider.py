"""
Sensors Provider for RDWC v4
Reads temperature, EC, and pH from Atlas EZO sensors via I2C
Supports mock mode for development/testing
"""
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Atlas EZO I2C default addresses (from app.ezo_i2c)
ADDR_RTD = 0x66  # Temperature (RTD)
ADDR_EC = 0x64   # Electrical Conductivity
ADDR_PH = 0x63   # pH

class SensorsProvider:
    """
    Provides sensor readings from Atlas EZO devices over I2C
    Falls back to mock data if hardware unavailable
    """
    
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        self.ezo_available = False
        
        if not use_mock:
            try:
                # Try to import existing ezo_i2c module
                from app import ezo_i2c
                self.ezo = ezo_i2c
                self.ezo_available = True
                logger.info("[SensorsProvider] Initialized with real hardware (ezo_i2c)")
            except (ImportError, Exception) as e:
                logger.warning(f"[SensorsProvider] Could not init hardware, using mock: {e}")
                self.use_mock = True
    
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
