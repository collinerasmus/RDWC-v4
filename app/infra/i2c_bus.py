"""
I²C Bus singleton for RDWC-v4
Provides process-wide shared SMBus connection to prevent FD leaks
"""

import atexit
from smbus2 import SMBus

_BUS = None

def get_bus():
    """Get the singleton SMBus(1) instance"""
    global _BUS
    if _BUS is None:
        _BUS = SMBus(1)
    return _BUS

def close_bus():
    """Close the singleton bus (idempotent)"""
    global _BUS
    if _BUS is not None:
        try:
            _BUS.close()
        except Exception:
            pass  # Ignore close errors
        _BUS = None

# Register cleanup on exit
atexit.register(close_bus)