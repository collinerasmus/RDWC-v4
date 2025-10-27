from typing import Dict
from gpiozero import OutputDevice
from app.config import RELAY_ACTIVE_LOW, PINMAP

class RelayBank:
    """Generic, name-based relay controller using the project PINMAP."""
    def __init__(self):
        self._active_low = RELAY_ACTIVE_LOW
        self._relays: Dict[str, OutputDevice] = {}
        for name, bcm in PINMAP.items():
            self._relays[name] = OutputDevice(
                bcm, active_high=not self._active_low, initial_value=False
            )

    def names(self):
        return list(self._relays.keys())

    def set(self, name: str, on: bool):
        dev = self._get(name)
        dev.on() if on else dev.off()

    def get(self, name: str) -> bool:
        return bool(self._get(name).value)

    def status(self) -> Dict[str, bool]:
        return {n: bool(d.value) for n, d in self._relays.items()}

    def _get(self, name: str) -> OutputDevice:
        if name not in self._relays:
            raise ValueError(f"Unknown relay '{name}'")
        return self._relays[name]

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