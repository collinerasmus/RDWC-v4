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
        # Lights 06:00-22:00 daily
        {"name":"grow_lights", "kind":"span", "on_at":"06:00", "off_at":"22:00", "days":[0,1,2,3,4,5,6]},
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

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.stop.clear()
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

        # handle span entries (on_at..off_at)
        for e in cfg.get("entries", []):
            if wday not in e.get("days",[0,1,2,3,4,5,6]): continue
            if e.get("kind") == "span":
                on_h,on_m = map(int, e["on_at"].split(":"))
                off_h,off_m = map(int, e["off_at"].split(":"))
                a = on_h*60+on_m; b = off_h*60+off_m
                want_on = (a <= now_min < b) if a < b else not (b <= now_min < a)  # support wrap
                self.relays.set(e["name"], bool(want_on))
                if want_on:
                    self.daily_used[e["name"]] = min(caps.get(e["name"], 10**9),
                                                     self.daily_used.get(e["name"],0)+1)

        # handle pulse entries at exact minute/second 0
        for e in cfg.get("entries", []):
            if e.get("kind") != "pulse": continue
            if wday not in e.get("days",[0,1,2,3,4,5,6]): continue
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