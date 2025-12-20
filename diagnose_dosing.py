import requests
import json

s = requests.get('http://192.168.88.55:8080/api/ph/status').json()
print('=== pH Status ===')
print(f'pH: {s["ph"]}')
print(f'Targets: [{s["targets"]["low"]}, {s["targets"]["high"]}]')
print(f'Auto enabled: {s["auto"]["enabled"]}')
print(f'Holding reason: {s["auto"]["holding_reason"]}')
print(f'Learned ml/pH: {s["auto"]["learned_ml_per_pH"]}')
print('\n=== Guards ===')
for k, v in s["guards"].items():
    if v:
        print(f'  ✗ {k}: {v}')
    elif k in ["since_last_ok_s", "since_last_ec_s", "today_total_ml", "min_interval_s", "daily_cap_ml"]:
        print(f'  · {k}: {v}')
        
print('\n=== Diagnosis ===')
if s["auto"]["holding_reason"]:
    print(f'HOLDING because: {s["auto"]["holding_reason"]}')
else:
    active_guards = [k for k, v in s["guards"].items() if v and k not in ["since_last_ok_s", "since_last_ec_s", "today_total_ml", "min_interval_s", "daily_cap_ml"]]
    if active_guards:
        print(f'BLOCKED by guards: {", ".join(active_guards)}')
    else:
        print('No obvious block - investigate auto loop logic')
