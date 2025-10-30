# Tools

## smoke.sh

30-second smoke test to verify the service is healthy and key endpoints respond.

Usage on Pi:

```bash
bash tools/smoke.sh 127.0.0.1 8080
```

Usage from your PC:

```powershell
ssh pi@192.168.88.49 "bash ~/RDWC-v4/tools/smoke.sh 127.0.0.1 8080"
```

Checks:
- /health returns 200
- /relay/status reachable
- /sensors/read reachable
- /settings returns shape
- /relay/set GET path toggles lights (subject to cooldown)
- /debug/relay_requests reachable
- /debug/lights_log reachable
