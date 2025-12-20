import requests
import json

try:
    r = requests.get('http://localhost:8080/api/settings', timeout=5)
    settings = r.json()
    targets = settings.get('targets', {})
    print("=== /api/settings targets ===")
    for k in ['ph_low', 'ph_high', 'ec_low', 'ec_high']:
        print(f"{k}: {targets.get(k)}")
except Exception as e:
    print(f"Error: {e}")
