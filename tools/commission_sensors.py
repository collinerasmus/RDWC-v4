"""
Commissioning: Sensors

Exit Codes:
- 0: Success
- 1: Hardware not detected
- 2: API error
"""
import os

def check_i2c_device(dev_path: str = "/dev/i2c-1") -> bool:
    """Return True if the I2C device path exists.
    Designed for unit tests to patch os.path.exists.
    """
    try:
        return bool(os.path.exists(dev_path))
    except Exception:
        return False
