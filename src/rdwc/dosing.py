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

    def execute_to_ec(self, week:int, volume_l:float|None, target_us:int, tol_us:int,
                      step_ml_per_10l:int, max_ml_per_10l:int, stabilize_wait_sec:int,
                      dry_run:bool=False):
        if self.is_mock and not settings.allow_dosing_when_mock:
            raise DoseError("Dosing blocked: FORCE_MOCK_SENSORS is active.")
        plan_total_cap = max_ml_per_10l * ( (float(volume_l) if volume_l else settings.total_volume_l) / 10.0 )
        step_ml = step_ml_per_10l * ( (float(volume_l) if volume_l else settings.total_volume_l) / 10.0 )
        sched = get_week_schedule(week)
        # compute per-step ml by ratio
        total_ratio = sched["grow"] + sched["micro"] + sched["bloom"]
        def per_comp_ml(total_ml):
            return {
                "grow": total_ml * (sched["grow"]/total_ratio),
                "micro": total_ml * (sched["micro"]/total_ratio),
                "bloom": total_ml * (sched["bloom"]/total_ratio)
            }
        added_ml = {"grow":0.0,"micro":0.0,"bloom":0.0}
        total_added = 0.0

        def dose_ml(component, ml):
            secs = ml / max(0.1, settings.ml_per_sec[component])
            remaining = secs
            while remaining > 0:
                step = min(settings.dose_max_sec_per_run, remaining)
                if not dry_run:
                    self.relays.set(component, True)
                    time.sleep(step)
                    self.relays.set(component, False)
                remaining -= step
                if remaining > 0:
                    time.sleep(settings.dose_cooldown_sec)

        with self._lock:
            self._busy = True
            try:
                while total_added < plan_total_cap:
                    # read current EC
                    ec_now = self.sampler.latest().get("ec")
                    if ec_now is None:
                        raise DoseError("No EC reading available.")
                    # done?
                    if ec_now >= (target_us - tol_us):
                        return {"ok": True, "stopped":"target_reached", "ec": ec_now, "added_ml": added_ml, "total_added_ml": total_added}
                    # dose one small step according to ratio
                    split = per_comp_ml(step_ml)
                    for comp, ml in split.items():
                        if ml <= 0: continue
                        dose_ml(comp, ml)
                        added_ml[comp] += ml
                        total_added += ml
                        time.sleep(settings.dose_cooldown_sec)
                    # wait for mixing, then re-check EC
                    time.sleep(stabilize_wait_sec)
                return {"ok": True, "stopped":"max_cap_reached", "ec": self.sampler.latest().get("ec"), "added_ml": added_ml, "total_added_ml": total_added}
            finally:
                self._busy = False