import threading, time
from .config import settings
from .nutrients import get_week_schedule

class DoseError(Exception): pass

class Doser:
    """
    Simple, safe, sequential dosing executor.
    - Computes ml from EHG ratios (ml/10L) * (volume/10).
    - Converts ml -> seconds via per-pump ml/sec calibration.
    - Enforces max run per pump and cooldown between components.
    - Uses a lock so only one dosing job can run at a time.
    """
    def __init__(self, relays, sampler, is_mock: bool):
        self.relays = relays
        self.sampler = sampler
        self.is_mock = is_mock
        self._lock = threading.Lock()
        self._busy = False

    def plan(self, week: int, volume_l: float | None = None):
        vol = float(volume_l) if volume_l is not None else settings.total_volume_l
        sched = get_week_schedule(week)
        # ml needed per component
        plan_ml = {k: v * (vol/10.0) for k, v in sched.items()}
        # convert to seconds using calibration
        plan_sec = {
            "grow": plan_ml["grow"]  / max(0.1, settings.ml_per_sec["grow"]),
            "micro": plan_ml["micro"]/ max(0.1, settings.ml_per_sec["micro"]),
            "bloom": plan_ml["bloom"]/ max(0.1, settings.ml_per_sec["bloom"]),
        }
        return {"week": week, "volume_l": vol, "ml": plan_ml, "seconds": plan_sec}

    def execute(self, week: int, volume_l: float | None = None, dry_run: bool = False):
        if self.is_mock and not settings.allow_dosing_when_mock:
            raise DoseError("Dosing blocked: FORCE_MOCK_SENSORS is active.")
        if self._busy:
            raise DoseError("A dosing job is already running.")
        plan = self.plan(week, volume_l)
        # safety: slice long runs into chunks of <= DOSE_MAX_SEC_PER_RUN
        seq = [("grow", plan["seconds"]["grow"]),
               ("micro", plan["seconds"]["micro"]),
               ("bloom", plan["seconds"]["bloom"])]
        def run_component(name, total_sec):
            remaining = float(total_sec)
            while remaining > 0:
                step = min(settings.dose_max_sec_per_run, remaining)
                if not dry_run:
                    self.relays.set(name, True)
                    time.sleep(step)
                    self.relays.set(name, False)
                remaining -= step
                if remaining > 0:
                    time.sleep(settings.dose_cooldown_sec)
        # execute sequentially
        with self._lock:
            self._busy = True
            try:
                for name, secs in seq:
                    if secs <= 0: continue
                    run_component(name, secs)
                    time.sleep(settings.dose_cooldown_sec)
            finally:
                self._busy = False
        return {"ok": True, "plan": plan}