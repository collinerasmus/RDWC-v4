# app/scheduler.py
import os, json, time, threading
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from .hardware import RelayBank

STATE_DIR = os.environ.get("RDWC_STATE_DIR", os.path.expanduser("~/.rdwc"))
SCHED_FILE = os.path.join(STATE_DIR, "schedule.json")
LOG_FILE   = os.path.join(STATE_DIR, "schedule_log.jsonl")

DEFAULT = {
    "enabled": False,
    "entries": [
        # NOTE: grow_lights schedule is now dynamically generated from settings
        # Dosing pulses (Micro/Grow/Bloom) at 09:00/09:05/09:10 for 120s
        {"name":"micro_pump", "kind":"pulse", "at":"09:00", "duration_sec":120, "days":[0,1,2,3,4,5,6]},
        {"name":"grow_pump",  "kind":"pulse", "at":"09:05", "duration_sec":120, "days":[0,1,2,3,4,5,6]},
        {"name":"bloom_pump", "kind":"pulse", "at":"09:10", "duration_sec":120, "days":[0,1,2,3,4,5,6]},
    ],
    # Hard safety caps per relay per day (seconds)
    "daily_caps": {"micro_pump":300, "grow_pump":300, "bloom_pump":300, "ph_up":120, "grow_lights":24*3600}
}

def _ensure_dir():
    try: os.makedirs(STATE_DIR, exist_ok=True)
    except Exception: pass

def load_cfg() -> Dict:
    _ensure_dir()
    if not os.path.exists(SCHED_FILE):
        save_cfg(DEFAULT)
        return json.loads(json.dumps(DEFAULT))
    with open(SCHED_FILE,"r") as f:
        return json.load(f)

def save_cfg(cfg: Dict):
    _ensure_dir()
    tmp = SCHED_FILE + ".tmp"
    with open(tmp,"w") as f: json.dump(cfg, f, indent=2)
    os.replace(tmp, SCHED_FILE)

def log_event(ev: Dict):
    _ensure_dir()
    with open(LOG_FILE,"a") as f:
        f.write(json.dumps({"ts": int(time.time()), **ev}) + "\n")

def _now_tuple():
    t = time.localtime()
    return t.tm_wday, t.tm_hour, t.tm_min, t.tm_sec  # Mon=0..Sun=6

def _today_key():
    return time.strftime("%Y-%m-%d")

class Scheduler:
    def __init__(self, relays: RelayBank):
        self.relays = relays
        self.thread: Optional[threading.Thread] = None
        self.stop = threading.Event()
        self.daily_used: Dict[str, int] = {}
        self.daily_key = _today_key()
        self._pulse_work: Dict[str, int] = {}  # relay -> remaining_sec
        self._last_lights_config = None  # track when to update lights schedule
        self._current_lights_on_time = None
        self._current_lights_off_time = None

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.stop.clear()
        # Initialize lights schedule - NO MORE CATCHUP
        self._update_lights_schedule()
        # CATCHUP DISABLED: No periodic enforcement - pure edge-only control
        self.thread = threading.Thread(target=self._loop, name="rdwc_scheduler", daemon=True)
        self.thread.start()

    def shutdown(self):
        self.stop.set()

    def _reset_daily_if_needed(self):
        if _today_key() != self.daily_key:
            self.daily_key = _today_key()
            self.daily_used = {}
            # clear any leftover pulses
            self._pulse_work = {}
            # recompute lights schedule for new day
            self._update_lights_schedule()

    def _update_lights_schedule(self):
        """Update lights schedule based on current settings"""
        try:
            from .settings import get_settings, get_todays_lights_window
            from datetime import datetime
            import pytz
            
            settings = get_settings()
            
            # Check if settings changed
            current_config = (settings.lights_on_time, settings.lights_duration_hours)
            if current_config == self._last_lights_config:
                return  # no change needed
            
            self._last_lights_config = current_config
            
            # Get today's window
            on_dt, off_dt = get_todays_lights_window()
            
            # Store times for catch-up logic
            self._current_lights_on_time = on_dt.strftime("%H:%M")
            self._current_lights_off_time = off_dt.strftime("%H:%M")
            
            log_event({
                "kind": "lights_schedule_updated",
                "on_time": self._current_lights_on_time,
                "off_time": self._current_lights_off_time,
                "on_datetime": on_dt.isoformat(),
                "off_datetime": off_dt.isoformat()
            })
            
            # Handle case where lights span midnight (off_time < on_time the next day)
            if off_dt.date() > on_dt.date():
                # Split into two spans: today->midnight and midnight->off_time
                self._current_lights_off_time = "23:59"  # end today
                # TODO: handle next day portion (for now, assume duration <= 24h)
            
        except Exception as e:
            log_event({"kind": "lights_schedule_error", "error": str(e)})
            # Fall back to default
            self._current_lights_on_time = "06:00"
            self._current_lights_off_time = "22:00"

    def is_within_window(self, now_min: int, on_min: int, off_min: int) -> bool:
        """Pure function to determine if now is within the lights window."""
        if on_min <= off_min:  # same-day window
            return on_min <= now_min < off_min
        else:  # wrap across midnight
            return now_min >= on_min or now_min < off_min

    def _handle_lights_catchup(self):
        """DISABLED: No more catchup enforcement - pure edge-only control"""
        log_event({"kind": "catchup_disabled", "message": "Periodic catchup enforcement disabled - pure edge-only scheduling"})

    def _loop(self):
        while not self.stop.is_set():
            try:
                self._tick()
            except Exception as e:
                log_event({"kind":"error","msg":str(e)})
            self.stop.wait(1.0)  # 1s resolution

    def _tick(self):
        self._reset_daily_if_needed()
        cfg = load_cfg()
        if not cfg.get("enabled", False):
            # ensure dosing pumps are off when disabled
            for name in ("micro_pump","grow_pump","bloom_pump","ph_up"):
                self.relays.set(name, False)
            return

        wday,h,m,s = _now_tuple()
        now_min = h*60 + m
        caps = cfg.get("daily_caps", {})

        # Handle lights scheduling - PURE EDGE-ONLY (zero periodic enforcement)
        if self._current_lights_on_time and self._current_lights_off_time:
            try:
                from app.relays_core import set_lights, REASON_SCHEDULE_ON, REASON_SCHEDULE_OFF
                
                on_h, on_m = map(int, self._current_lights_on_time.split(":"))
                off_h, off_m = map(int, self._current_lights_off_time.split(":"))
                
                # PURE EDGE DETECTION: Only act at exact scheduled times
                # No guards, no periodic checks, no continuous enforcement
                if s == 0:  # Only at exact minute boundaries
                    if h == on_h and m == on_m:
                        # Lights ON edge - execute once and trust it
                        result = set_lights(True, REASON_SCHEDULE_ON)
                        log_event({"kind": "lights_schedule_on", "time": f"{h:02d}:{m:02d}", "changed": result["changed"]})
                        if result["changed"]:
                            self.daily_used["grow_lights"] = self.daily_used.get("grow_lights", 0) + 1
                    
                    elif h == off_h and m == off_m:
                        # Lights OFF edge - execute once and trust it
                        result = set_lights(False, REASON_SCHEDULE_OFF)
                        log_event({"kind": "lights_schedule_off", "time": f"{h:02d}:{m:02d}", "changed": result["changed"]})
                
                # NO GUARD ENFORCEMENT - eliminated to prevent periodic "off dips"
                    
            except Exception as e:
                log_event({"kind": "lights_error", "error": str(e)})

        # Handle other span entries (non-lights) - EDGE-ONLY to eliminate ALL periodic activity
        for e in cfg.get("entries", []):
            if wday not in e.get("days",[0,1,2,3,4,5,6]):
                continue
            if e.get("kind") == "span" and e.get("name") != "grow_lights":  # skip lights, handled above
                on_h, on_m = map(int, e["on_at"].split(":"))
                off_h, off_m = map(int, e["off_at"].split(":"))
                
                # EDGE-ONLY: Only act at exact on/off times (s == 0)
                if s == 0:
                    if h == on_h and m == on_m:
                        # Span ON edge
                        self.relays.set(e["name"], True)
                        self.daily_used[e["name"]] = min(caps.get(e["name"], 10**9),
                                                         self.daily_used.get(e["name"],0)+1)
                        log_event({"kind": "span_schedule_on", "relay": e["name"], "time": f"{h:02d}:{m:02d}"})
                    elif h == off_h and m == off_m:
                        # Span OFF edge
                        self.relays.set(e["name"], False)
                        log_event({"kind": "span_schedule_off", "relay": e["name"], "time": f"{h:02d}:{m:02d}"})

        # handle pulse entries at exact minute/second 0
        for e in cfg.get("entries", []):
            if e.get("kind") != "pulse":
                continue
            if wday not in e.get("days",[0,1,2,3,4,5,6]):
                continue
            hh,mm = map(int, e["at"].split(":"))
            if h==hh and m==mm and s==0:
                cap = caps.get(e["name"], 0)
                used = self.daily_used.get(e["name"],0)
                dur  = int(e.get("duration_sec",60))
                if used >= cap:
                    log_event({"kind":"skip_cap", "relay":e["name"], "needed":dur, "used":used, "cap":cap})
                else:
                    grant = min(dur, max(0, cap-used))
                    self._pulse_work[e["name"]] = grant
                    self.relays.set(e["name"], True)
                    log_event({"kind":"pulse_start","relay":e["name"],"sec":grant})

        # decrement any active pulses
        for r in list(self._pulse_work.keys()):
            self._pulse_work[r] -= 1
            self.daily_used[r] = self.daily_used.get(r,0)+1
            if self._pulse_work[r] <= 0:
                self.relays.set(r, False)
                log_event({"kind":"pulse_end","relay":r})
                self._pulse_work.pop(r, None)