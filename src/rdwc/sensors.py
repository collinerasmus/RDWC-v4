import os, time
from smbus2 import SMBus

RUNNING_ON_PI = os.path.exists("/sys/firmware/devicetree/base/model")

class EZO:
    def __init__(self, bus: int, addr: int):
        self.mock = not RUNNING_ON_PI
        self.addr = addr
        self.busno = bus
        if not self.mock:
            self.bus = SMBus(bus)

    def _write(self, cmd: str):
        if self.mock:
            return
        self.bus.write_i2c_block_data(self.addr, 0x00, list(cmd.encode('ascii')))

    def _read(self) -> str:
        if self.mock:
            # Return different mock values based on address
            if self.addr == 0x66:  # RTD/Temperature sensor
                return "1,22.5"
            elif self.addr == 0x64:  # EC sensor  
                return "1,1250"
            elif self.addr == 0x63:  # pH sensor
                return "1,6.8"
            else:
                return "1,7.00"
        time.sleep(0.3)
        data = self.bus.read_i2c_block_data(self.addr, 0x00, 32)
        chars = []
        for c in data:
            if c == 0:
                break
            chars.append(chr(c))
        return "".join(chars)

    def read_value(self, cmd="R"):
        self._write(cmd)
        resp = self._read()
        parts = resp.split(",")
        if parts[0] != "1":
            raise RuntimeError(f"EZO error: {resp}")
        return float(parts[1])

class Sensors:
    def __init__(self, bus: int, ph_addr: int, ec_addr: int, rtd_addr: int):
        self.ph = EZO(bus, ph_addr)
        self.ec = EZO(bus, ec_addr)
        self.rtd = EZO(bus, rtd_addr)

    def sample(self):
        t = self.rtd.read_value("R")
        # Optional temp compensation hooks for later:
        # self.ec._write(f"T,{t:.2f}")
        # self.ph._write(f"T,{t:.2f}")
        ec = self.ec.read_value("R")
        ph = self.ph.read_value("R")
        return {"temperature_c": t, "ec": ec, "pH": ph}