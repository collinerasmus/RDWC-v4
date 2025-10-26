import os, time, threading
from typing import Dict, Any
from smbus2 import SMBus
from .config import settings

RUNNING_ON_PI = os.path.exists("/sys/firmware/devicetree/base/model")

class EZO:
    """
    Atlas Scientific I2C protocol helper with 'fixer':
    - Write ASCII command
    - Wait
    - Read 32 bytes: first byte is status (1=success, 254=processing, 2/255=error)
    - If 254, retry for a short period
    - Parse ASCII up to first null
    """
    def __init__(self, bus: int, addr: int, mock_override: bool = False):
        self.addr = addr
        self.mock = mock_override or not RUNNING_ON_PI
        self.busno = bus
        self.bus = None if self.mock else SMBus(bus)

    def _write(self, cmd: str):
        if self.mock: return
        # send ascii bytes (no null terminator)
        self.bus.write_i2c_block_data(self.addr, 0x00, list(cmd.encode("ascii")))

    def _read_raw(self):
        if self.mock:
            # Mock returns: status byte + ascii "1,7.00" bytes
            return [1] + list(b"7.00") + [0]
        data = self.bus.read_i2c_block_data(self.addr, 0x00, 32)
        return data

    def _exchange(self, cmd: str, delay: float = 0.9, retries: int = 6) -> str:
        # write then wait
        self._write(cmd)
        time.sleep(delay)
        for _ in range(retries):
            raw = self._read_raw()
            status = raw[0]
            if status == 254:  # still processing
                time.sleep(0.3)
                continue
            if status != 1:
                raise RuntimeError(f"EZO status {status} on addr {hex(self.addr)} cmd {cmd}")
            # parse ascii after status until null
            bytes_ascii = []
            for b in raw[1:]:
                if b == 0: break
                bytes_ascii.append(b)
            return bytes(bytearray(bytes_ascii)).decode("ascii")
        raise TimeoutError(f"EZO timeout on addr {hex(self.addr)} cmd {cmd}")

    def read_float(self, cmd="R", delay=0.9) -> float:
        text = self._exchange(cmd, delay=delay)
        # Some modules return "1.234" or "OK,1.234" or "1,1.234"
        if "," in text:
            parts = text.split(",")
            # take last part that looks like a number
            text = parts[-1]
        return float(text)

class Sensors:
    def __init__(self):
        mock = settings.force_mock_sensors
        self.ph = EZO(settings.i2c_bus, settings.ph_addr, mock_override=mock)
        self.ec = EZO(settings.i2c_bus, settings.ec_addr, mock_override=mock)
        self.rtd = EZO(settings.i2c_bus, settings.rtd_addr, mock_override=mock)

    def sample_once(self) -> Dict[str, Any]:
        # Temperature first
        t = self.rtd.read_float("R")
        # Temp compensation (uncomment if your EZO boards have T compensation enabled)
        try:
            self.ec._exchange(f"T,{t:.2f}", delay=0.3)
        except Exception:
            pass
        try:
            self.ph._exchange(f"T,{t:.2f}", delay=0.3)
        except Exception:
            pass
        ec = self.ec.read_float("R")
        ph = self.ph.read_float("R")
        return {"temperature_c": t, "ec": ec, "pH": ph}

class Sampler:
    """Background sampler that updates latest reading every N seconds."""
    def __init__(self, sensors: Sensors, interval_sec: int):
        self.sensors = sensors
        self.interval = max(2, interval_sec)
        self._last = {"temperature_c": None, "ec": None, "pH": None, "ts": 0.0}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if not self._th.is_alive():
            self._th.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                data = self.sensors.sample_once()
                from .history import log_sample
                log_sample(data)
                data["ts"] = time.time()
                with self._lock:
                    self._last = data
            except Exception as e:
                with self._lock:
                    self._last = {"temperature_c": None, "ec": None, "pH": None, "ts": time.time(), "error": str(e)}
            self._stop.wait(self.interval)

    def latest(self):
        with self._lock:
            return dict(self._last)