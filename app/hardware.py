from typing import Dict
from gpiozero import OutputDevice
from app.config import RELAY_ACTIVE_LOW, PINMAP
import json
import os
import time
STATE_DIR = os.environ.get("RDWC_STATE_DIR", os.path.join(os.path.expanduser("~"), ".rdwc"))
STATE_FILE = os.path.join(STATE_DIR, "relay_state.json")

class RelayBank:
    """Generic, name-based relay controller using the project PINMAP."""
    def __init__(self):
        self._active_low = RELAY_ACTIVE_LOW
        self._relays: Dict[str, OutputDevice] = {}
        self._ensure_all()
        
    def _ensure_all(self):
        # Materialize all OutputDevice instances up-front (no lazy init)
        for name, bcm in PINMAP.items():
            if name not in self._relays:
                self._relays[name] = OutputDevice(
                    bcm, active_high=not self._active_low, initial_value=False
                )

    def _ensure_relay(self, name: str):
        """Lazy initialize relay device on first use."""
        if name not in self._relays and name in PINMAP:
            try:
                bcm = PINMAP[name]
                self._relays[name] = OutputDevice(
                    bcm, active_high=not self._active_low, initial_value=False
                )
            except Exception as e:
                print(f"Warning: Could not initialize relay '{name}' on GPIO{PINMAP[name]}: {e}")
                return None
        return self._relays.get(name)

    def names(self):
        return list(PINMAP.keys())
    
    def cleanup(self):
        """Clean up GPIO resources."""
        for relay in self._relays.values():
            try:
                relay.close()
            except Exception:
                pass
        self._relays.clear()

    def _ensure_dir(self):
        try: os.makedirs(STATE_DIR, exist_ok=True)
        except Exception: pass

    def save_state(self, allowlist=None):
        self._ensure_dir()
        data = {n: bool(d.value) for n, d in self._relays.items()}
        if allowlist:
            data = {k: v for k, v in data.items() if k in allowlist}
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"ts": int(time.time()), "relays": data}, f)
        os.replace(tmp, STATE_FILE)

    def load_state(self, allowlist=None, default_off=True):
        self._ensure_all()  # make sure all relay devices exist
        try:
            with open(STATE_FILE, "r") as f:
                payload = json.load(f)
                data = payload.get("relays", {})
        except Exception:
            data = {}
        for name in PINMAP.keys():  # iterate canonical names (not self._relays.items())
            dev = self._relays[name]
            if allowlist and name not in allowlist:
                if default_off: dev.off()
                continue
            val = data.get(name)
            if isinstance(val, bool):
                dev.on() if val else dev.off()

    def set(self, name: str, on: bool):
        dev = self._get(name)
        dev.on() if on else dev.off()
        # Persist only main/chiller by default
        self.save_state(allowlist=["main_pump", "chiller_pump"])

    def get(self, name: str) -> bool:
        dev = self._ensure_relay(name)
        return bool(dev.value) if dev else False

    def status(self) -> Dict[str, bool]:
        result = {}
        for name in PINMAP.keys():
            dev = self._ensure_relay(name)
            result[name] = bool(dev.value) if dev else False
        return result

    def _get(self, name: str) -> OutputDevice:
        dev = self._ensure_relay(name)
        if not dev:
            raise ValueError(f"Relay '{name}' could not be initialized")
        return dev

# Back-compat shim for old "pump_*" usage in routes:
class PumpController:
    def __init__(self, relay_bank: RelayBank):
        self._bank = relay_bank
        self._main_name = "main_pump"
        self._chiller_name = "chiller_pump"

    def set(self, name: str, on: bool):
        if name == "main":
            self._bank.set(self._main_name, on)
        elif name == "chiller":
            self._bank.set(self._chiller_name, on)
        else:
            raise ValueError("unknown pump")

    def get(self, name: str) -> bool:
        if name == "main":
            return self._bank.get(self._main_name)
        if name == "chiller":
            return self._bank.get(self._chiller_name)
        raise ValueError("unknown pump")

    def status(self):
        return {"main": self.get("main"), "chiller": self.get("chiller")}