#!/usr/bin/env python3
import time
import urllib.request
import datetime
import os

LOG = os.environ.get('SOAK_LOG', '/home/pi/soak_watch.log')
URL_HEALTH = 'http://127.0.0.1:8080/health/db'
URL_GAPS = 'http://127.0.0.1:8080/debug/readings/gaps?hours=1&min_gap_sec=180'

os.makedirs(os.path.dirname(LOG), exist_ok=True)

def fetch(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read().decode('utf-8', 'ignore').strip()
    except Exception as e:
        return f"{{\"error\": \"{str(e)}\"}}"

with open(LOG, 'a', encoding='utf-8') as f:
    f.write(f"==== START {datetime.datetime.now().isoformat()} ====\n")
    f.flush()
    for i in range(25):
        ts = datetime.datetime.now().isoformat()
        f.write(f"--- {ts} ---\n")
        f.write(fetch(URL_HEALTH) + "\n")
        f.write(fetch(URL_GAPS) + "\n")
        f.flush()
        time.sleep(60)
    f.write(f"==== END {datetime.datetime.now().isoformat()} ====\n")
    f.flush()
