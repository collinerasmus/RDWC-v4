# Minimal smbus2 shim for Windows/dev to satisfy imports in tests
class SMBus:  # pragma: no cover - shim only
    def __init__(self, bus):
        self.bus = bus
    def read_byte_data(self, addr, reg):
        return 0
    def write_byte(self, addr, val):
        pass
    def close(self):
        pass

class i2c_msg:  # placeholder
    pass

class I2cFunc:  # placeholder
    pass
