import time
from .config import settings

class Controller:
    def __init__(self, sampler, relays):
        self.sampler = sampler
        self.relays = relays
        self.last_ph_dose_ts = 0

        # default pump states
        self.relays.set("main_pump", settings.main_pump_on)
        self.relays.set("chiller_pump", settings.chiller_pump_on)

    def loop_once(self):
        data = self.sampler.latest()
        ph = data.get("pH")
        if ph is None:
            return data

        lo = settings.ph_setpoint - settings.ph_deadband
        now = time.time()

        # If pH is below lower band, add base briefly, then cooldown
        if ph < lo and (now - self.last_ph_dose_ts) > settings.ph_up_cooldown_sec:
            self.relays.set("ph_up", True)
            time.sleep(settings.ph_up_max_sec)
            self.relays.set("ph_up", False)
            self.last_ph_dose_ts = time.time()

        return data