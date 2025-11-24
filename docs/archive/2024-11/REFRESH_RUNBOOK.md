# Refresh Runbook (Clean UI + Service Restart)

Purpose: Recover from stale assets, stuck relay UI, or perceived slowness. Produces a deterministic, cache-busted running instance.

## 1. Local Repo Sync (optional)
```
cd /home/pi/RDWC-v4
git fetch --all
git reset --hard origin/main
```

## 2. (Optional) Dependency Hygiene
```
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt --upgrade --no-cache-dir
```

## 3. Systemd Assets Updated
Ensure `systemd/rdwc.service` now contains:
```
Environment=ASSET_VERSION=%h-%t
```
This yields a fresh token each restart (host-timestamp). After updating unit file:
```
sudo cp systemd/rdwc.service /etc/systemd/system/rdwc.service
sudo systemctl daemon-reload
```

## 4. Restart Service (Cache Bust Trigger)
```
sudo systemctl restart rdwc.service
journalctl -u rdwc.service -n 50 --no-pager
```
Look for uvicorn start line and absence of tracebacks.

## 5. Browser Hard Reload
Use Ctrl+F5 (or Cmd+Shift+R) on dashboard. Verify updated JS:
```
Network panel -> relays_v2.js?* (new query param)
```

## 6. Functional Relay Toggle Test
1. Open Relays tab.
2. Toggle `lights` relay.
3. Expect a toast: `lights toggled (ON|OFF) in <X>ms`.
4. Network panel shows single POST: `/api/relay/lights/toggle?v=<asset>`.
5. (Optional) Curl verification:
```
curl -s http://<pi-ip>:8080/api/relays/status | jq '.relays.lights.is_on'
```

## 7. Guard Integrity Check
```
curl -s http://<pi-ip>:8080/api/relays/verify | jq .
```
Expect: `ok_all: true`, `anomalies.count: 0`.

## 8. Latency Sampling (3 toggles)
Toggle any relay 3 times, record toast ms values. Normal LAN baseline <150ms. If >300ms repeatedly:
- Check Pi CPU load: `top` or `uptime`.
- Check DB file size: `ls -lh data/rdwc.db`.

## 9. Optional Deep Clean
```
git clean -fdx   # WARNING: removes untracked files (back up first)
```
Recreate venv and restart service.

## 10. Post-Refresh Checklist
| Item | Pass Criteria |
|------|---------------|
| Service status | `active (running)` |
| Relay toggle | Toast + state change |
| Verify endpoint | `ok_all=true` |
| No anomalies | `anomalies.count=0` |
| Latency | <200ms typical |

## 11. Rollback (if regressions)
```
# Use previous commit hash from `git log`
git reset --hard <old-commit>
sudo systemctl restart rdwc.service
```

## 12. Next Steps After Successful Refresh
- Proceed to manual dosing tests (EC or pH) with guarded relay writes.
- Capture sample logs for RelayGuard (journalctl tail while toggling).
- Enable alerting if needed.

---
Revision: Generated on refresh workflow automation.
