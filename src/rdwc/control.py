import time, threading, datetime
from .config import settings

class LightScheduler(threading.Thread):
    """Turns lights on/off by schedule (local time)."""
    def __init__(self, relays):
        super().__init__(daemon=True)
        self.relays = relays
        self.on_hr = int(getattr(settings, "lights_on_hour", 6))
        self.off_hr = int(getattr(settings, "lights_off_hour", 22))
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            now = datetime.datetime.now()
            hour = now.hour
            lights_on = self.on_hr <= hour < self.off_hr
            
            # Use new centralized lights control with proper whitelisting
            try:
                from app.relays_core import set_lights
                set_lights(lights_on, "schedule_on" if lights_on else "schedule_off")
            except ImportError:
                # Fallback for standalone use
                self.relays.set("lights", lights_on)
            
            self._stop.wait(60)

    def stop(self):
        self._stop.set()

class Controller:
    def __init__(self, sampler, relays):
        self.sampler = sampler
        self.relays = relays
        self.last_ph_dose_ts = 0

        # default pump states
        self.relays.set("main_pump", settings.main_pump_on)
        self.relays.set("chiller_pump", settings.chiller_pump_on)

        # start light schedule
        self.lights = LightScheduler(relays)
        self.lights.start()

    def loop_once(self):
        data = self.sampler.latest()
        ph = data.get("pH")
        if ph is None:
            return data
        lo = settings.ph_setpoint - settings.ph_deadband
        now = time.time()
        if ph < lo and (now - self.last_ph_dose_ts) > settings.ph_up_cooldown_sec:
            self.relays.set("ph_up", True)
            time.sleep(settings.ph_up_max_sec)
            self.relays.set("ph_up", False)
            self.last_ph_dose_ts = time.time()
        return data