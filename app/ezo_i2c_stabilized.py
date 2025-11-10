"""Stabilized Atlas EZO I2C helper for minimal smbus2 environments.

Only uses byte/byte_data primitives (no i2c_rdwr / block ops). Adds optional
debug logging of status bytes via RDWC_EZO_DEBUG=1.
"""

from time import sleep, monotonic
from smbus2 import SMBus
import logging
import os

PH_ADDR = 0x63
EC_ADDR = 0x64
RTD_ADDR = 0x66

logger = logging.getLogger(__name__)


class EZO:
    def __init__(self, bus_num: int, addr: int, name: str):
        self.bus_num = bus_num
        self.addr = addr
        self.name = name
        self.bus = SMBus(bus_num)
        # Capability flags (we won't use advanced ones but log them)
        self.has_i2c_rdwr = hasattr(self.bus, 'i2c_rdwr')
        self.has_block_io = hasattr(self.bus, 'write_i2c_block_data') and hasattr(self.bus, 'read_i2c_block_data')
        logger.debug(
            f"EZO {name} (0x{addr:02x}): has_i2c_rdwr={self.has_i2c_rdwr}, "
            f"has_block_io={self.has_block_io}")

    def _write(self, payload: bytes):
        for b in payload:
            if hasattr(self.bus, 'write_byte_data'):
                self.bus.write_byte_data(self.addr, 0x00, b)  # type: ignore[attr-defined]
            else:
                self.bus.write_byte(self.addr, b)
            sleep(0.0015)

    def _read(self, n: int) -> bytes:
        out = []
        for _ in range(n):
            out.append(self.bus.read_byte_data(self.addr, 0x00))  # type: ignore[attr-defined]
        return bytes(out)

    def cmd(self, cmd: str, read_len: int = 32, settle: float = 0.3) -> str:
        if cmd:
            self._write(cmd.encode('ascii'))
        sleep(settle)
        if not read_len:
            return ""
        raw = self._read(read_len)
        if not raw:
            return ""
        status = raw[0]
        data_bytes = raw[1:].rstrip(b"\x00")
        data = data_bytes.decode('ascii', errors='ignore').strip()
        if status != 1:
            if os.getenv("RDWC_EZO_DEBUG", "0") == "1":
                logger.debug(f"EZO {self.name} status={status} raw={raw!r} partial='{data}'")
            return ""
        return data

    def init_once(self):
        # Disable continuous mode only (keep LED for diagnostics)
        try:
            self.cmd("C,0", read_len=0, settle=0.06)
        except Exception:
            pass

    def read_value(self, request: str = "R", timeout: float = 1.8, poll: float = 0.15) -> str:
        start = monotonic()
        self.cmd(request, read_len=0, settle=0.02)
        result = ""
        while monotonic() - start < timeout:
            result = self.cmd("", read_len=32, settle=0.06)
            if result:
                break
            sleep(poll)
        if not result:
            raise TimeoutError(f"{self.name} no data")
        return result.split(",")[0].strip()


def read_all(bus_num: int = 1):
    """Sequential compensated read of RTD, pH, EC sensors."""
    rtd = EZO(bus_num, RTD_ADDR, "RTD")
    ph = EZO(bus_num, PH_ADDR, "pH")
    ec = EZO(bus_num, EC_ADDR, "EC")

    for dev in (rtd, ph, ec):
        dev.init_once()
    sleep(0.25)

    temp_c = float(rtd.read_value(timeout=1.2))
    try:
        ph.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.25)
    except Exception:
        pass
    ph_val = float(ph.read_value(timeout=1.5))
    try:
        ec.cmd(f"T,{temp_c:.2f}", read_len=0, settle=0.25)
    except Exception:
        pass
    ec_val = float(ec.read_value(timeout=1.5))

    return {"temperature": temp_c, "ph": ph_val, "ec_ms": ec_val}