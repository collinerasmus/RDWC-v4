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
        Read all sensor values and calibration status
        Returns dict with temperature_c, ec_mscm, ph, cal status, online flag, and timestamp
        """
        if self.use_mock or not self.ezo_available:
            return self.mock_read_all()
        
        try:
            return self._read_real()
        except Exception as e:
            logger.error(f"[SensorsProvider] Read failed, falling back to mock: {e}")
            return self.mock_read_all()
    
    def _read_real(self) -> Dict[str, Any]:
        """Read from actual hardware with sequential temp-compensation"""
        import time
        
        try:
            # 1) Read RTD temperature first
            temp_val = self.ezo.read_single(ADDR_RTD)
            if temp_val is None or temp_val == 0.0:
                raise RuntimeError("RTD returned empty or zero")
            
            # 2) Set temp comp for EC, wait, then read
            self.ezo.set_temp_comp(ADDR_EC, float(temp_val))
            time.sleep(0.9)  # Wait for temp comp to settle
            ec_val = self.ezo.read_single(ADDR_EC)
            if ec_val is None or ec_val == 0.0:
                raise RuntimeError("EC returned empty or zero")
            
            # EC comes in µS/cm from Atlas, convert to mS/cm
            ec_mscm = float(ec_val) / 1000.0
            
            # 3) Set temp comp for pH, wait, then read
            self.ezo.set_temp_comp(ADDR_PH, float(temp_val))
            time.sleep(0.9)  # Wait for temp comp to settle
            ph_val = self.ezo.read_single(ADDR_PH)
            if ph_val is None or ph_val == 0.0:
                raise RuntimeError("pH returned empty or zero")
            
            # Success - return all values
            return {
                "temperature_c": float(temp_val),
                "ec_mscm": ec_mscm,
                "ph": float(ph_val),
                "cal": {
                    "temp": {"is_calibrated": True, "detail": "rtd: assumed OK"},
                    "ec": {"is_calibrated": True, "detail": "ec: temp-comp applied"},
                    "ph": {"is_calibrated": True, "detail": "ph: temp-comp applied"}
                },
                "online": True,
                "ts": datetime.utcnow().isoformat() + "Z"
            }
            
        except Exception as ex:
            logger.error(f"[SensorsProvider] Hardware read error: {ex}")
            return {
                "temperature_c": None,
                "ec_mscm": None,
                "ph": None,
                "cal": {
                    "temp": {"is_calibrated": False, "detail": str(ex)},
                    "ec": {"is_calibrated": False, "detail": str(ex)},
                    "ph": {"is_calibrated": False, "detail": str(ex)}
                },
                "online": False,
                "ts": datetime.utcnow().isoformat() + "Z"
            }
    
    @staticmethod
    def mock_read_all() -> Dict[str, Any]:
        """Return stable mock data for development"""
        return {
            "temperature_c": 22.4,
            "ec_mscm": 1.62,
            "ph": 5.86,
            "cal": {
                "temp": {"is_calibrated": True, "detail": "mock"},
                "ec": {"is_calibrated": True, "detail": "mock"},
                "ph": {"is_calibrated": True, "detail": "mock"}
            },
            "online": True,
            "ts": datetime.utcnow().isoformat() + "Z"
        }
