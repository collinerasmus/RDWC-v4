from typing import Dict
from gpiozero import OutputDevice
from app.config import RELAY_ACTIVE_LOW, PINMAP

class RelayBank:
    """Generic, name-based relay controller using the project PINMAP."""
    def __init__(self):
        self._active_low = RELAY_ACTIVE_LOW
        self._relays: Dict[str, OutputDevice] = {}
        # Lazy initialization to avoid GPIO conflicts at startup
        
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

    def set(self, name: str, on: bool):
        dev = self._ensure_relay(name)
        if dev:
            dev.on() if on else dev.off()

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
    def __init__(self):
        self._bank = RelayBank()
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