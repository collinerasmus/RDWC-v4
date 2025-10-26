from gpiozero import OutputDevice
from app.config import PUMP_MAIN_PIN, PUMP_CHILLER_PIN, RELAY_ACTIVE_LOW

class PumpController:
    def __init__(self):
        self._active_low = RELAY_ACTIVE_LOW
        self.main = OutputDevice(PUMP_MAIN_PIN, active_high=not self._active_low, initial_value=False)
        self.chiller = OutputDevice(PUMP_CHILLER_PIN, active_high=not self._active_low, initial_value=False)

    def set(self, name: str, on: bool):
        dev = self._get(name)
        if on: dev.on()
        else:  dev.off()

    def get(self, name: str) -> bool:
        dev = self._get(name)
        # OutputDevice.value is True when "on" (active), independent of polarity
        return bool(dev.value)

    def status(self):
        return {"main": self.get("main"), "chiller": self.get("chiller")}

    def _get(self, name: str) -> OutputDevice:
        if name == "main":    return self.main
        if name == "chiller": return self.chiller
        raise ValueError("unknown pump")