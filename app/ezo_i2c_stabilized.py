# app/ezo_i2c_stabilized.py
# Hardened Atlas EZO I²C helper (pH/EC/RTD)
from time import sleep, monotonic
from smbus2 import SMBus
try:
    from smbus2 import i2c_msg
    HAS_I2C_MSG = True
except ImportError:
    HAS_I2C_MSG = False

PH_ADDR  = 0x63
EC_ADDR  = 0x64
RTD_ADDR = 0x66

class EZO:
    def __init__(self, bus_num: int, addr: int, name: str):
        self.bus_num = bus_num
        self.addr = addr
        self.name = name
        self.bus = SMBus(bus_num)
        # Detect available I2C methods
        self.has_i2c_rdwr = hasattr(self.bus, 'i2c_rdwr')
        self.has_block_io = hasattr(self.bus, 'write_i2c_block_data') and hasattr(self.bus, 'read_i2c_block_data')
        # Debug: log capabilities
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"EZO {name} (0x{addr:02x}): has_i2c_rdwr={self.has_i2c_rdwr}, has_block_io={self.has_block_io}, HAS_I2C_MSG={HAS_I2C_MSG}")

    def _xfer(self, payload: bytes = b"", read_len: int = 0, tries: int = 5, pause: float = 0.08):
        last = None
        for i in range(tries):
            try:
                if payload:
                    # Try i2c_msg method first if available (works with i2c_rdwr)
                    if HAS_I2C_MSG and self.has_i2c_rdwr:
                        self.bus.i2c_rdwr(i2c_msg.write(self.addr, payload))
                    # Fallback to block I/O
                    elif self.has_block_io:
                        # Block write: prepend register 0x00, convert to list
                        data = [0x00] + list(payload)
                        self.bus.write_i2c_block_data(self.addr, data[0], data[1:])
                    # Last resort: try i2c_msg even if i2c_rdwr detection failed
                    elif HAS_I2C_MSG:
                        try:
                            self.bus.i2c_rdwr(i2c_msg.write(self.addr, payload))
                        except AttributeError:
                            raise NotImplementedError("No supported I2C write method available")
                    else:
                        raise NotImplementedError("No supported I2C write method available")
                
                if read_len:
                    # Try i2c_msg method first if available
                    if HAS_I2C_MSG and self.has_i2c_rdwr:
                        buf = i2c_msg.read(self.addr, read_len)
                        self.bus.i2c_rdwr(buf)
                        return bytes(buf)
                    # Fallback to block I/O
                    elif self.has_block_io:
                        # Block read from register 0x00
                        raw = self.bus.read_i2c_block_data(self.addr, 0x00, read_len)
                        return bytes(raw)
                    # Last resort: try i2c_msg even if i2c_rdwr detection failed
                    elif HAS_I2C_MSG:
                        try:
                            buf = i2c_msg.read(self.addr, read_len)
                            self.bus.i2c_rdwr(buf)
                            return bytes(buf)
                        except AttributeError:
                            raise NotImplementedError("No supported I2C read method available")
                    else:
                        raise NotImplementedError("No supported I2C read method available")
                
                return b""
            except OSError as e:
                last = e
                sleep(pause * (1 + i))
        raise last

    def cmd(self, cmd: str, read_len: int = 32, settle: float = 0.3):
        self._xfer(cmd.encode("ascii"), read_len=0)
        sleep(settle)
        if not read_len:
            return ""
        raw = self._xfer(b"", read_len)
        if not raw:
            return ""
        status = raw[0]
        data = raw[1:].rstrip(b"\x00").decode("ascii", errors="ignore")
        if status != 1:
            return ""
        return data.strip()

    def init_once(self):
        # Keep LEDs ON for visual diagnostics; only disable continuous mode
        for c in ("C,0",):  # Continuous off only
            try:
                self.cmd(c, read_len=0, settle=0.06)
            except Exception:
                pass

    def read_value(self, request: str = "R", timeout: float = 1.8, poll: float = 0.15):
        start = monotonic()
        self.cmd(request, read_len=0, settle=0.02)
        result = ""
        while monotonic() - start < timeout:
            result = self.cmd("", read_len=32, settle=0.02)
            if result:
                break
            sleep(poll)
        if not result:
            raise TimeoutError(f"{self.name} no data")
        return result.split(",")[0].strip()

def read_all(bus_num: int = 1):
    """
    Sequential sensor read with explicit waits per Atlas EZO timing specs.
    
    Sequence:
    1. Read RTD (temperature) - 600ms settle
    2. Write temp compensation to pH - 300ms settle
    3. Read pH - 900ms poll
    4. Write temp compensation to EC - 300ms settle  
    5. Read EC - 900ms poll
    
    Total cycle: ~3.0s for full compensated readings
    """
    rtd, ph, ec = (EZO(bus_num, RTD_ADDR, "RTD"),
                   EZO(bus_num, PH_ADDR,  "pH"),
                   EZO(bus_num, EC_ADDR,  "EC"))

    for dev in (rtd, ph, ec):
        dev.init_once()
    
    # Allow devices to settle after init (C,0 command)
    sleep(0.3)

    # Step 1: Read temperature (RTD response time: 600ms)
    temp_c = float(rtd.read_value(timeout=1.2))
    
    # Step 2: Write temperature compensation to pH sensor
    try:
        ph.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.3)  # 300ms for T command to apply
    except Exception as e:
        # Non-fatal: continue with uncompensated read
        pass
    
    # Step 3: Read pH (response time: 900ms)
    ph_val = float(ph.read_value(timeout=1.5))
    
    # Step 4: Write temperature compensation to EC sensor
    try:
        ec.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.3)  # 300ms for T command to apply
    except Exception as e:
        # Non-fatal: continue with uncompensated read
        pass
    
    # Step 5: Read EC (response time: 900ms)
    ec_val = float(ec.read_value(timeout=1.5))
    
    return {"temperature": temp_c, "ph": ph_val, "ec_ms": ec_val}