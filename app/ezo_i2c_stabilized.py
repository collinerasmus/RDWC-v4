# app/ezo_i2c_stabilized.py
# Hardened Atlas EZO I²C helper (pH/EC/RTD)
from time import sleep, monotonic
from smbus2 import SMBus, i2c_msg

PH_ADDR  = 0x63
EC_ADDR  = 0x64
RTD_ADDR = 0x66

class EZO:
    def __init__(self, bus_num: int, addr: int, name: str):
        self.bus_num = bus_num
        self.addr = addr
        self.name = name
        self.bus = SMBus(bus_num)

    def _xfer(self, payload: bytes = b"", read_len: int = 0, tries: int = 5, pause: float = 0.08):
        last = None
        for i in range(tries):
            try:
                if payload:
                    self.bus.i2c_rdwr(i2c_msg.write(self.addr, payload))
                if read_len:
                    buf = i2c_msg.read(self.addr, read_len)
                    self.bus.i2c_rdwr(buf)
                    return bytes(buf)
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
        for c in ("L,0", "C,0"):  # LED off, continuous off
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
    rtd, ph, ec = (EZO(bus_num, RTD_ADDR, "RTD"),
                   EZO(bus_num, PH_ADDR,  "pH"),
                   EZO(bus_num, EC_ADDR,  "EC"))

    for dev in (rtd, ph, ec):
        dev.init_once()

    temp_c = float(rtd.read_value())
    for dev in (ph, ec):
        try: dev.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.06)
        except Exception: pass

    ph_val = float(ph.read_value())
    ec_val = float(ec.read_value())
    return {"temperature": temp_c, "ph": ph_val, "ec_ms": ec_val}