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
        Read all sensor values using sensors_core as single source of truth
        Adds calibration status for UI display
        """
        from app.sensors_core import read_all_sensors as core_read
        
        try:
            # Get data from core (includes temp_comp_applied, ts, etc)
            data = core_read()
            
            # Add calibration status for UI (stub for now - can enhance later)
            if "cal" not in data:
                data["cal"] = {
                    "temp": {"is_calibrated": False, "detail": "unknown"},
                    "ec": {"is_calibrated": False, "detail": "unknown"},
                    "ph": {"is_calibrated": False, "detail": "unknown"}
                }
            
            return data
            
        except Exception as e:
            logger.error(f"[SensorsProvider] Read failed: {e}")
            return {
                "temperature_c": None,
                "ec_mscm": None,
                "ph": None,
                "temp_comp_applied": False,
                "ts": datetime.utcnow().isoformat() + "Z",
                "online": False,
                "cal": {
                    "temp": {"is_calibrated": False, "detail": "unknown"},
                    "ec": {"is_calibrated": False, "detail": "unknown"},
                    "ph": {"is_calibrated": False, "detail": "unknown"}
                },
                "errors": {"provider_error": str(e)}
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
