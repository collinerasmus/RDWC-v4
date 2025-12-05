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

    def close(self):
        """Close the I2C bus connection to release file descriptor."""
        if self.bus is not None:
            try:
                self.bus.close()
            except Exception:
                pass
            self.bus = None

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
            logger.warning(f"EZO {self.name} cmd='{cmd}' status={status} raw_len={len(raw)} raw_head={raw[:8]!r} partial='{data}'")
            return ""
        # Log query commands (Cal,? and K,?) to diagnose empty responses
        if cmd in ("Cal,?", "K,?"):
            logger.warning(f"EZO {self.name} cmd='{cmd}' returned: status={status} data='{data}'")
        return data

    def cmd_with_polling(self, cmd: str, timeout: float = 2.0, poll: float = 0.15) -> str:
        """Send command and poll for response (for query commands like Cal,? and K,?)."""
        from time import monotonic
        self._write(cmd.encode('ascii'))
        # Query commands might need more time to process
        sleep(0.5)
        
        start = monotonic()
        while monotonic() - start < timeout:
            raw = self._read(32)
            if not raw:
                sleep(poll)
                continue
            status = raw[0]
            if status == 1:  # success
                data_bytes = raw[1:].replace(b"\xff", b"\x00").rstrip(b"\x00")
                data = data_bytes.decode('ascii', errors='ignore').strip()
                logger.warning(f"EZO {self.name} cmd_with_polling('{cmd}') success: {data}")
                return data
            elif status == 2:
                # Device error
                logger.warning(f"EZO {self.name} cmd_with_polling('{cmd}') error frame")
                return ""
            # 254/255/0 => processing / not ready; wait then retry
            sleep(poll)
        
        logger.warning(f"EZO {self.name} cmd_with_polling('{cmd}') timeout after {timeout}s")
        return ""


    def init_once(self):
        # Disable continuous mode only (keep LED for diagnostics)
        try:
            self.cmd("C,0", read_len=0, settle=0.06)
        except Exception:
            pass
        
        # Restore EC probe K value from settings (if this is EC sensor)
        if self.addr == EC_ADDR:
            try:
                from app.settings import get_all_settings
                settings = get_all_settings()
                k_value = float(settings.get("ec.k_value", "1.0"))
                # Set K value on device to ensure it matches persisted setting
                # Format with sufficient precision for common k values (0.1, 1.0, 10.0)
                self.cmd(f"K,{k_value:.2f}", read_len=0, settle=0.3)
                logger.info(f"EC probe K value restored to {k_value} from settings")
            except Exception as e:
                logger.warning(f"Failed to restore EC K value from settings: {e}")

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

    try:
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
        ec_raw = float(ec.read_value(timeout=1.5))
        
        # EZO EC circuit returns µS/cm by default; convert to mS/cm
        # Heuristic: if value > 10, assume it's µS/cm and divide by 1000
        ec_val = ec_raw / 1000.0 if ec_raw > 10 else ec_raw

        return {"temperature": temp_c, "ph": ph_val, "ec_ms": ec_val}
    finally:
        # Always close bus connections to prevent file descriptor leak
        for dev in (rtd, ph, ec):
            dev.close()