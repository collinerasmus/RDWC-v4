import time
from .config import settings

class Controller:
    def __init__(self, sensors, relays):
        self.sensors = sensors
        self.relays = relays
        self.last_ph_dose_ts = 0

        # default pump states
        self.relays.set("main_pump", settings.main_pump_on)
        self.relays.set("chiller_pump", settings.chiller_pump_on)

    def loop(self):
        data = self.sensors.sample()
        ph = data["pH"]
        lo = settings.ph_setpoint - settings.ph_deadband
        hi = settings.ph_setpoint + settings.ph_deadband

        now = time.time()
        # If pH is below band, we add base (pH-Up) briefly, then cooldown
        if ph < lo and (now - self.last_ph_dose_ts) > settings.ph_up_cooldown_sec:
            self.relays.set("ph_up", True)
            time.sleep(settings.ph_up_max_sec)
            self.relays.set("ph_up", False)
            self.last_ph_dose_ts = time.time()

        return data