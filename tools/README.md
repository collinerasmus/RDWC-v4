# Tools

## commissioning_readiness.py

Readiness snapshot — verifies the service is healthy and key endpoints respond.

Usage on Pi:

```bash
python tools/commissioning_readiness.py
```

Compact JSON output (CI / log-friendly):

```bash
python tools/commissioning_readiness.py --compact
```

Remote via SSH:

```powershell
ssh pi@192.168.88.55 "cd ~/RDWC-v4 && python tools/commissioning_readiness.py --compact"
```

Checks:
- API reachable and sensors online
- Relay status / estop state
- pH and EC values present
- Settings accessible
