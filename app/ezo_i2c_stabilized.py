"""Stabilized Atlas EZO I2C helper.

Tries to prefer system smbus2 (with i2c_rdwr + block I/O). If unavailable,
falls back to minimal byte/byte_data primitives.
"""

from time import sleep, monotonic
import logging
import sys
from pathlib import Path

# Prefer system smbus2 over any vendored copy in the repo (Linux/Pi only)
_repo_root = Path(__file__).resolve().parents[1]
_removed = False
if str(_repo_root) in sys.path:
    sys.path.remove(str(_repo_root))
    _removed = True
try:
    from smbus2 import SMBus, i2c_msg
    _HAS_I2C_MSG = True
    _HAS_SMBUS = True
except Exception:  # pragma: no cover
    # Windows/dev: smbus2 unavailable (no fcntl); use mock
    SMBus = None  # type: ignore
    i2c_msg = None  # type: ignore
    _HAS_I2C_MSG = False
    _HAS_SMBUS = False
finally:
    if _removed:
        sys.path.insert(0, str(_repo_root))

PH_ADDR = 0x63
EC_ADDR = 0x64
RTD_ADDR = 0x66

logger = logging.getLogger(__name__)


class EZO:
    def __init__(self, bus_num: int, addr: int, name: str):
        self.bus_num = bus_num
        self.addr = addr
        self.name = name
        if SMBus is None:
            raise RuntimeError("SMBus not available (Windows/dev environment)")
        self.bus = SMBus(bus_num)
        # Capability flags
        self.has_i2c_rdwr = hasattr(self.bus, 'i2c_rdwr') and (i2c_msg is not None)
        self.has_block_io = hasattr(self.bus, 'write_i2c_block_data') and hasattr(self.bus, 'read_i2c_block_data')
        logger.debug(
            f"EZO {name} (0x{addr:02x}): has_i2c_rdwr={self.has_i2c_rdwr}, "
            f"has_block_io={self.has_block_io}")

    def _write(self, payload: bytes):
        # Prefer i2c_rdwr transaction; else block write; else byte-by-byte
        if self.has_i2c_rdwr and i2c_msg is not None:
            msg = i2c_msg.write(self.addr, payload)
            self.bus.i2c_rdwr(msg)
            return
        if self.has_block_io:
            self.bus.write_i2c_block_data(self.addr, 0x00, list(payload))  # type: ignore[attr-defined]
            return
        for b in payload:
            if hasattr(self.bus, 'write_byte_data'):
                self.bus.write_byte_data(self.addr, 0x00, b)  # type: ignore[attr-defined]
            else:
                self.bus.write_byte(self.addr, b)
            sleep(0.0015)

    def _read(self, n: int) -> bytes:
        # Prefer i2c_rdwr read (more faithful), then block I/O, then byte-by-byte
        if self.has_i2c_rdwr and i2c_msg is not None:
            rx = i2c_msg.read(self.addr, n)
            self.bus.i2c_rdwr(rx)
            return bytes(rx)
        if self.has_block_io:
            return bytes(self.bus.read_i2c_block_data(self.addr, 0x00, n))  # type: ignore[attr-defined]
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
        # Treat 0xFF as padding (observed on minimal reads) same as 0x00
        data_bytes = raw[1:].replace(b"\xff", b"\x00").rstrip(b"\x00")
        data = data_bytes.decode('ascii', errors='ignore').strip()
        # Always log non-ready status for diagnostics (RTD timeout investigation)
        if status != 1:
            logger.debug(f"EZO {self.name} status={status} raw_len={len(raw)} raw_head={raw[:8]!r} partial='{data}'")
            return ""
        return data

    def init_once(self):
        # Disable continuous mode only (keep LED for diagnostics)
        try:
            self.cmd("C,0", read_len=0, settle=0.06)
        except Exception:
            pass

    def read_value(self, request: str = "R", timeout: float = 1.8, poll: float = 0.15) -> str:
        """Issue a single measurement command and poll until ready or timeout.

        Atlas EZO timing (approx): RTD ~600-650ms, pH/EC ~900-950ms. We give
        a generous first wait then poll with shorter intervals. We rely on
        i2c_rdwr when available to ensure proper repeated-start framing.
        """
        start = monotonic()
        # Send command (no immediate read)
        self.cmd(request, read_len=0, settle=0.0)
        initial_wait = 0.65 if self.name == "RTD" else 0.95
        sleep(initial_wait)

        # Poll loop: one read per attempt, break on status=1
        while monotonic() - start < timeout:
            raw = self._read(32)
            if not raw:
                sleep(poll)
                continue
            status = raw[0]
            if status == 1:  # success
                data_bytes = raw[1:].replace(b"\xff", b"\x00").rstrip(b"\x00")
                data = data_bytes.decode('ascii', errors='ignore').strip()
                if not data:
                    break
                return data.split(",")[0].strip()
            elif status == 2:
                # Device error frame
                raise RuntimeError(f"{self.name} sensor error frame")
            # 254/255/0 => processing / not ready; wait then retry
            sleep(poll if poll < 0.08 else 0.08)

        raise TimeoutError(f"{self.name} no data")


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