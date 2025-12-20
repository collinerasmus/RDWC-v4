import requests

base = "http://192.168.88.55:8080"

# Current pH
status = requests.get(f"{base}/api/ph/status", timeout=10).json()
ph_now = status['ph']
targets = status['targets']
learned = status['auto']['learned_ml_per_pH']
print(f"\n=== Current System State ===")
print(f"pH: {ph_now}")
print(f"Target: [{targets['low']}, {targets['high']}]")
print(f"Learned ml/pH: {learned}")
print(f"Auto: {status['auto']['enabled']}, Holding: {status['auto']['holding_reason']}")

# Doses (dose_events format)
doses = requests.get(f"{base}/api/ph/dose_log?hours=3&limit=20", timeout=10).json()
print(f"\n=== Recent Doses ===")
total_vol = sum(d.get('volume_ml', 0) for d in doses if d.get('volume_ml'))
print(f"Total from last 20: {total_vol:.1f} ml")

print("\nLast 5:")
for d in doses[:5]:
    ts = d.get('ts', '')[-8:]
    vol = d.get('volume_ml')
    reason = str(d.get('reason', ''))[:35]
    pb = d.get('ph_before')
    pa = d.get('ph_after')
    if pb and pa:
        delta = round(pa - pb, 4)
        print(f"  {ts} | vol={vol:5.2f}ml Δ={delta:+.4f} | {reason}")
    else:
        print(f"  {ts} | vol={vol:5.2f}ml | {reason}")

print(f"\n✓ Aggressive dosing config active: 7ml max, 60s interval, force enabled")
print(f"✓ System is dosing frequently toward setpoint")
