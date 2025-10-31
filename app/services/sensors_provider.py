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
        """Read from actual hardware using ezo_i2c module"""
        result = {
            "temperature_c": None,
            "ec_mscm": None,
            "ph": None,
            "cal": {
                "temp": {"is_calibrated": False, "detail": "unknown"},
                "ec": {"is_calibrated": False, "detail": "unknown"},
                "ph": {"is_calibrated": False, "detail": "unknown"}
            },
            "online": True,
            "ts": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            # Read temperature first (used for compensation)
            temp_val = self.ezo.read_single(ADDR_RTD)
            if temp_val is not None and temp_val != 0.0:
                result["temperature_c"] = float(temp_val)
                
                # Send temperature compensation to EC and pH
                self.ezo.set_temp_comp(ADDR_EC, temp_val)
                self.ezo.set_temp_comp(ADDR_PH, temp_val)
            
            # Read EC (with temp comp if available)
            ec_val = self.ezo.read_single(ADDR_EC, temp_c=temp_val if temp_val else None)
            if ec_val is not None and ec_val != 0.0:
                # Atlas EC returns µS/cm, convert to mS/cm
                result["ec_mscm"] = float(ec_val) / 1000.0
            
            # Read pH (with temp comp if available)
            ph_val = self.ezo.read_single(ADDR_PH, temp_c=temp_val if temp_val else None)
            if ph_val is not None and ph_val != 0.0:
                result["ph"] = float(ph_val)
            
            # Read calibration status (best effort)
            result["cal"]["temp"] = self._get_cal_status(ADDR_RTD, "RTD")
            result["cal"]["ec"] = self._get_cal_status(ADDR_EC, "EC")
            result["cal"]["ph"] = self._get_cal_status(ADDR_PH, "pH")
            
        except Exception as e:
            logger.error(f"[SensorsProvider] Hardware read error: {e}")
            result["online"] = False
        
        return result
    
    def _get_cal_status(self, addr: int, name: str) -> Dict[str, Any]:
        """Get calibration status for a sensor (best effort, may not work on all devices)"""
        try:
            from app.infra.i2c_bus import get_bus
            bus = get_bus()
            
            # Send Cal,? command
            cmd_data = list("Cal,?".encode("ascii")) + [0x00]
            bus.write_i2c_block_data(addr, 0x00, cmd_data)
            
            # Wait and read response
            import time
            time.sleep(0.3)
            raw = bus.read_i2c_block_data(addr, 0x00, 32)
            
            if raw[0] == 1:  # Success status
                payload = bytes(raw[1:]).decode("ascii", errors="ignore").strip().rstrip('\x00')
                if payload.startswith("?Cal,"):
                    points = payload.split(",")[1] if "," in payload else "0"
                    is_cal = int(points) > 0
                    return {
                        "is_calibrated": is_cal,
                        "detail": f"{points}-point" if is_cal else "not calibrated"
                    }
        except Exception as e:
            logger.debug(f"[SensorsProvider] Cal status for {name}: {e}")
        
        # Default to unknown
        return {"is_calibrated": False, "detail": "unknown"}
    
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
