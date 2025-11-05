# Manual Dosing System - Deployment & Verification Guide

## Overview
This document outlines the deployment and verification steps for the unified manual dosing system with safety caps, dose logging, and trend markers.

## Branch: `feat/manual-dosing-safe-caps`

### Commits
1. **ac24df2** - Core unified dosing system (backend + UI controls + logs)
2. **777eae9** - Trends dose markers overlay
3. **3ef4380** - Settings UI for safety caps + deploy script

---

## Deployment Steps

### 1. Run Deployment Script

From your local machine (PowerShell):

```powershell
.\deploy\deploy_controllers.ps1 -PiHost "raspberrypi.local" -User "pi"
```

**What it does:**
- Pulls `feat/manual-dosing-safe-caps` branch on Pi
- Restarts `rdwc.service`
- Verifies health endpoints:
  - `/api/health`
  - `/api/sensors/last`
  - `/api/settings` (safety caps)
  - `/api/dose/recent?limit=5`
- Checks I²C ownership (should be `rdwc-sensors.service` only)
- Displays service status for both services

**Expected output:**
- ✓ Branch pulled
- ✓ rdwc.service active
- Health JSON responses
- I²C owned by rdwc-sensors.service

---

## Verification Tests

### Test 1: Happy Path (0.5s Grow dose)

```bash
curl -X POST http://localhost:5000/api/dose/grow \
  -H 'Content-Type: application/json' \
  -d '{"seconds":0.5,"reason":"happy path test","actor":"ops"}'
```

**Expected result:**
```json
{
  "ok": true,
  "pump": "grow",
  "seconds": 0.5,
  "caps": {
    "max_press": 1.5,
    "max_daily": 120,
    "min_off": 2
  },
  "guards": {
    "ph_high": false,
    "ec_high": false,
    "sensor_stale": false,
    "estop": false,
    "safeoff": false,
    "mix_lock": false
  },
  "kpis_before": {...},
  "kpis_after": {...}
}
```

### Test 2: Press Cap Block (9.0s exceeds max_seconds_per_press)

```bash
curl -X POST http://localhost:5000/api/dose/grow \
  -H 'Content-Type: application/json' \
  -d '{"seconds":9.0,"reason":"press cap test","actor":"ops"}'
```

**Expected result:**
```json
HTTP 409 Conflict
{
  "blocked_by": "press_cap",
  "message": "Dose 9.0s exceeds press cap 1.5s"
}
```

### Test 3: Min-Off Block (immediate repeat)

Wait 0-1 seconds after Test 1, then repeat:

```bash
curl -X POST http://localhost:5000/api/dose/grow \
  -H 'Content-Type: application/json' \
  -d '{"seconds":0.3,"reason":"min-off test","actor":"ops"}'
```

**Expected result:**
```json
HTTP 409 Conflict
{
  "blocked_by": "min_off",
  "message": "Min off window 2.0s not elapsed; 0.5s since last dose"
}
```

### Test 4: Dose History Listing

```bash
curl -s 'http://localhost:5000/api/dose/recent?limit=20' | jq
```

**Expected result:**
- List of dose events (successful + blocked)
- Each event includes: `ts`, `pump`, `seconds`, `reason`, `actor`, `ph_before`, `ec_before`, `temp_c`, `blocked_by`, `note`

---

## Demo Mode (optional)

If EC guard blocks nutrient dosing in your environment, use this temporary override to demo a Grow happy path, then revert:

```powershell
# Raise EC targets just for the demo
Invoke-RestMethod -Uri "http://<PI_HOST>:8080/api/settings" -Method Put -ContentType "application/json" -Body '{"targets.ec_target":"9.99","targets.ec_tolerance":"0.01","targets.ec_low":"0.0","targets.ec_high":"10.0"}' | ConvertTo-Json -Depth 5

# Run a small Grow pulse
Invoke-RestMethod -Uri "http://<PI_HOST>:8080/api/dose/grow" -Method Post -ContentType "application/json" -Body '{"seconds":0.3,"reason":"demo grow","actor":"ui"}' | ConvertTo-Json -Depth 6

# Revert to your normal values (edit as needed)
Invoke-RestMethod -Uri "http://<PI_HOST>:8080/api/settings" -Method Put -ContentType "application/json" -Body '{"targets.ec_low":"0.8","targets.ec_high":"1.2","targets.ec_target":"1.8","targets.ec_tolerance":"0.2"}'
```


---

## UI Verification

### 1. Settings Tab
- Navigate to Settings → Safety panel
- Verify new fields visible:
  - **Max seconds per dose press**: 1.5 (default)
  - **Max total seconds per 24h (per pump)**: 120 (default)
  - **Min off between doses (s)**: 2 (default)
- Tooltips explain server-side enforcement
- Save button updates settings via PUT `/api/settings`

### 2. Dose Buttons

#### pH Tab (Manual Dosing section)
- **Prime** → 0.2s ph_up dose
- **+1 ml** → 0.5s ph_up dose
- **+5 ml** → 1.0s ph_up dose
- **Custom** → user-specified seconds

**On click:**
- Button disabled for 2s (visual min_off enforcement)
- Toast shows success or block reason
- Dose Log table updates

#### EC Tab (Direct Pump Control section)
- **Grow** → 0.3s grow dose
- **Micro** → 0.3s micro dose
- **Bloom** → 0.3s bloom dose

**On click:**
- Same behavior as pH buttons

### 3. Dose Log Tables

#### pH Tab
- Table shows last 20 `ph_up` events
- Columns: Time, Pump, Seconds, pH Before, pH After, Note
- Refresh button reloads from `/api/dose/recent`

#### EC Tab
- Table shows last 20 `grow/micro/bloom` events
- Columns: Time, Pump, Seconds, EC Before, EC After, Note

### 4. Trends Chart Markers

- Navigate to Trends tab
- Load any preset (24h, Grow range, or custom)
- **Expected markers:**
  - **pH Up**: Amber triangles at ~95% of pH axis
  - **Grow**: Emerald circles at ~90% of EC axis
  - **Micro**: Cyan circles at ~85% of EC axis
  - **Bloom**: Purple circles at ~80% of EC axis
- Markers appear at dose timestamps
- Legend shows: "↑ pH Up", "↑ Grow", "↑ Micro", "↑ Bloom"

---

## Service Logs Check

### rdwc.service (main app)
```bash
sudo journalctl -u rdwc.service -n 50 --no-pager
```

**Look for:**
- `[DOSE] Pump: grow, Requested: 0.5s, ...` (successful dose)
- `[DOSE_BLOCK] Pump: grow, Blocked: press_cap, ...` (blocked attempts)
- No I²C access errors (sensors handled by rdwc-sensors.service)

### rdwc-sensors.service (I²C sensor poller)
```bash
sudo journalctl -u rdwc-sensors.service -n 50 --no-pager
```

**Look for:**
- Regular sensor polling (every 15s by default)
- No errors or I²C bus contention
- Sensor readings written to `readings` table

---

## Safety Enforcement Summary

### Always Enforced (even with `maintenance_override=true`)
1. **Press cap**: `max_seconds_per_press` (default 1.5s)
2. **Daily cap**: `max_total_seconds_per_24h` per pump (default 120s, resets midnight UTC)
3. **Min off**: `min_off_window_sec` between doses (default 2s)
4. **pH high**: Blocks all doses if pH ≥ 6.6
5. **EC high**: Blocks Grow/Micro/Bloom if EC ≥ target + 0.2 or ec_high
6. **Sensor stale**: Blocks if latest reading > 60s old (unless `allow_stale_on_override=true`)
7. **E-STOP**: Blocks all doses if E-STOP active
8. **Safe-off**: Blocks all doses if safe-off mode active
9. **Mix lock**: Blocks if mixing in progress

### Database Logging
- All dose attempts (successful + blocked) logged to `dose_events` table
- Fields: `ts`, `pump`, `seconds`, `reason`, `actor`, `ph_before`, `ec_before`, `temp_c`, `blocked_by`, `controller_state_json`
- Queryable via `/api/dose/recent?limit=N&hours=H`

---

## Post-Verification Checklist

- [ ] Deploy script ran successfully
- [ ] All health endpoints returned valid JSON
- [ ] I²C ownership correct (rdwc-sensors.service only)
- [ ] Test 1 (happy path): `ok:true` returned
- [ ] Test 2 (press cap): HTTP 409 `blocked_by:"press_cap"` returned
- [ ] Test 3 (min-off): HTTP 409 `blocked_by:"min_off"` returned
- [ ] Test 4 (history): Dose log listing shows all attempts
- [ ] UI: Settings panel shows new safety cap fields
- [ ] UI: Dose buttons work and disable for 2s
- [ ] UI: Dose Log tables update after button press
- [ ] UI: Trends markers visible and color-coded correctly
- [ ] Logs: rdwc.service shows dose events
- [ ] Logs: rdwc-sensors.service polling normally, no I²C errors

---

## Next Steps

1. **Paste verification outputs** in conversation:
   - Deploy script output
   - All 4 test curl responses
   - UI screenshots (optional but helpful)
   - `journalctl` logs for both services

2. **Open Pull Request** from `feat/manual-dosing-safe-caps` to `main`:
   - Title: "Unified manual dosing with safety caps, logging, and trend markers"
   - Body: Link to this guide; summarize features
   - Checklist: All verification items above

3. **Code review** and merge (if tests pass)

---

## Troubleshooting

### Issue: Service won't start
```bash
sudo systemctl status rdwc.service
sudo journalctl -u rdwc.service -n 100
```
- Check for Python import errors
- Verify `dose_events` table created (migration should be idempotent)

### Issue: I²C contention
```bash
sudo lsof /dev/i2c-1
```
- Should only show `rdwc-sensors.service` (Python process)
- If rdwc.service also accessing I²C: **BUG** (dosing module should NOT touch I²C)

### Issue: Dose buttons not working
- Open browser console (F12)
- Check for JS errors
- Verify `/api/dose/{pump}` endpoints reachable: `curl http://localhost:5000/api/dose/recent`

### Issue: Trends markers not showing
- Open browser console, check for fetch errors
- Verify `/api/dose/recent` returns data
- Check `fetchDoseEvents()` called before `render()` in trends.js

---

## Summary

**What was built:**
- ✅ Centralized dosing module (`app/dosing.py`) with 9 guard types
- ✅ Four POST endpoints (`/api/dose/{grow,micro,bloom,ph_up}`)
- ✅ GET endpoint (`/api/dose/recent`) for history
- ✅ UI dose buttons in pH/EC tabs with 2s disable + toast feedback
- ✅ Dose Log tables showing last 20 events
- ✅ Trends chart markers colored by pump type
- ✅ Settings UI fields for safety caps
- ✅ PowerShell deploy script with health checks

**Safety guarantees:**
- No dose exceeds press cap (even with maintenance override)
- Daily usage tracked per pump, enforced server-side
- Minimum off time prevents rapid-fire dosing
- pH/EC guards prevent over-dosing when sensors indicate risk
- All attempts logged for audit trail

**Next:**
- Deploy to Pi ✓
- Run verification tests → paste outputs
- Open PR with checklist
