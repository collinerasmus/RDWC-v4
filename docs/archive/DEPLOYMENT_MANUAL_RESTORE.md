# pH Manual Tab Restoration - Deployment Guide

## Branch: `fix/ph-manual-restore`

## Features Implemented

### ✅ Backend (`app/ph_control.py`)
- **Accepts both `ms` and `seconds`**: Endpoint now handles `{ms: 200}` or `{seconds: 0.2}` or `{ml: 1}`
- **Maintenance override**: When `safety.maintenance_override = true`, bypasses cooldown and daily cap
- **Safety preserved**: Still enforces E-STOP, stale sensors, empty reservoir, and single-dose clamp
- **GPIO safety**: Finally block ensures GPIO returns to HIGH (OFF) even on errors
- **Volume calculation**: Uses calibration (`dosing.ph_up_ml_per_sec`) if > 0, else null

### ✅ Settings (`app/settings.py`, `app/static/js/settings.js`)
- **New setting**: `safety.maintenance_override` (default: false)
- **UI toggle**: Settings → Safety → "Maintenance override (test only)"
- **Tooltip**: "Bypasses cooldown/daily cap; clamps single dose; E-STOP/empty reservoir still enforced"

### ✅ Frontend (`app/static/index.html`, `app/static/js/ph.js`)
- **Manual tab restored**: Prime (200 ms), +1 ml, +5 ml, Custom ml + Dose
- **Maintenance badge**: Shows red "Maintenance override active" badge when enabled
- **Cooldown UX**: 
  - Countdown pill shows remaining seconds
  - Buttons disabled during cooldown (unless override active)
  - Immediate update on blocked responses
- **Immediate refresh after dose**:
  1. `tick()` → Updates Recent doses list
  2. `refreshSummary()` → Updates Today/Week totals
  3. `refreshDoseChart()` → Reloads Dose History chart with new marker
- **Toast notifications**: Success shows volume/duration, errors show reason + countdown

### ✅ Tests (`conftest.py`)
- **gpiozero MockFactory**: Tests run on Windows/non-Pi hosts
- **Relay reset fixture**: Clears state between tests for deterministic results
- **All tests passing**: 15 passed, 0 failed

## Deployment to Raspberry Pi (192.168.88.49)

### 1. SSH to Pi
```bash
ssh pi@192.168.88.49
```

### 2. Deploy the branch
```bash
cd ~/RDWC-v4
git fetch origin
git checkout fix/ph-manual-restore
git pull
```

### 3. Restart service
```bash
sudo systemctl restart rdwc
sleep 2
curl -s http://127.0.0.1:8080/api/ph/status | jq
```

Expected: Status should return with `maintenance_override: false`

## Verification Steps

### A. Basic UI Check (from browser)
1. Navigate to `http://192.168.88.49:8080`
2. Hard refresh: `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac)
3. Scroll to **pH Control** card
4. Verify tabs: **Status** | **Manual** | **Automation**
5. Click **Manual** tab
6. Verify buttons:
   - **Prime** (should show tooltip "Prime (200 ms)")
   - **+1 ml**
   - **+5 ml**
   - Custom ml input box
   - **Dose** button

### B. Maintenance Override Toggle
1. Scroll to **System Settings** card
2. Click **Safety** tab
3. Find "Maintenance override (test only)" checkbox
4. Enable it → Click **Save**
5. Return to **pH Control → Manual** tab
6. Should see **red badge**: "Maintenance override active"

### C. Prime Test (with override)
1. With maintenance override enabled
2. Click **Prime** button
3. Expected behavior:
   - Relay BCM 5 clicks (goes LOW for 200ms, then HIGH)
   - Toast: "Dose complete: ~0.X ml" or "200 ms"
   - **Recent** section updates with new row
   - **Today** total increases
   - **Dose History** chart shows new marker

### D. Cooldown Test (disable override)
1. Settings → Safety → **Disable** "Maintenance override" → Save
2. Return to pH Control → Manual
3. Badge should disappear
4. Try **Prime** again within 5 minutes
5. Expected:
   - Toast: "Blocked by min interval (XXXs remaining)"
   - Countdown pill appears: "⏱ XXXs"
   - Buttons disabled until countdown reaches 0

### E. Calibration Banner Test
1. If `dosing.ph_up_ml_per_sec` is 0 or not set:
   - Should see banner: "Set pH Up ml/s in Settings → Dosing to enable volume totals"
2. Set calibration: Settings → Dosing → "pH Up ml/s" = 4.0 → Save
3. Banner should disappear
4. Next dose should show volume: "Dose complete: X.X ml"

## GPIO Safety Verification

### Check relays_core.py ensures safe-off:
```python
# In _actuate_ph_up():
try:
    set_dosing_ph_up(True, reason="ph_dose", force=True)  # LOW = ON
    time.sleep(duration_ms / 1000.0)
    return {"ok": True}
finally:
    set_dosing_ph_up(False, reason="ph_dose", force=True)  # HIGH = OFF
```

### Hardware test:
- Use multimeter on BCM 5 (GPIO pin)
- Before dose: should read ~3.3V (HIGH = OFF)
- During dose: should drop to ~0V (LOW = ON)
- After dose: should return to ~3.3V (HIGH = OFF)
- On error/interrupt: should immediately return to ~3.3V

## Safety Guardrails (Still Enforced with Maintenance Override)

### Always enforced (cannot bypass):
- ✅ **E-STOP active** → blocks all relay changes
- ✅ **Empty reservoir** (reservoir_liters ≤ 0)
- ✅ **Stale sensor** (pH reading > 90s old)
- ✅ **Single-dose clamp** (duration_ms ≤ max_ms, default 5000ms)

### Bypassed by maintenance override:
- ⚠️ Min interval cooldown (default 300s between doses)
- ⚠️ Daily cap (default 50 ml/day)

## Troubleshooting

### Issue: Buttons don't respond
**Fix**: Hard refresh (Ctrl+Shift+R) to clear browser cache

### Issue: "Blocked by guard" even with override
**Check**:
1. E-STOP not active: Relays card → verify E-STOP is OFF
2. Sensor not stale: Sensors card → pH reading < 90s ago
3. Reservoir set: Settings → General → "Reservoir liters" > 0

### Issue: Chart doesn't refresh after dose
**Check browser console**:
```javascript
// Should see:
[pH] Chart refresh after dose complete
[pH] Summary refresh after dose complete
```
If errors appear, check network tab for `/api/ph/dose_log` and `/api/ph/dose_summary` responses

### Issue: No relay click (GPIO not actuating)
**Check**:
1. Service status: `sudo systemctl status rdwc`
2. GPIO permissions: `groups pi` should include `gpio`
3. Backend logs: `sudo journalctl -u rdwc -f`
4. Relay hardware: Test with multimeter

## Rollback Plan

If issues arise:
```bash
cd ~/RDWC-v4
git checkout main
sudo systemctl restart rdwc
```

## Next Steps After Verification

1. Test all dose buttons (Prime, +1ml, +5ml, Custom ml)
2. Verify chart updates immediately after each dose
3. Test cooldown enforcement (override OFF)
4. Test override bypass (override ON)
5. Verify calibration banner logic
6. Create PR to merge to main:
   ```bash
   gh pr create --title "fix(ph): restore Manual tab + maintenance override + ms|seconds + chart refresh" \
     --body "Restores original Manual UI; adds test-only maintenance override; endpoint accepts ms/seconds; cooldown UX; immediate chart/summary refresh; active-low safety preserved."
   ```
7. Merge and deploy to main:
   ```bash
   gh pr merge --merge
   ssh pi@192.168.88.49 "cd ~/RDWC-v4 && git checkout main && git pull && sudo systemctl restart rdwc"
   ```

## Commit History

```
4d1f400 feat(ph): restore Manual tab with maintenance override; accept ms|seconds; cooldown UX; refresh chart/summary after dose
fa2e80f fix(ph): add _dose_daily compatibility shim for test_ph_dose_telemetry
4313161 test(infra): add conftest.py with gpiozero MockFactory and relay reset fixture for Windows tests
```

## Files Changed

- `conftest.py` (new) - Test infrastructure with MockFactory
- `app/ph_control.py` - Added `_dose_daily()` compatibility shim
- `app/settings.py` - Added `safety.maintenance_override` default
- `app/static/index.html` - Replaced Force checkbox with Maintenance badge
- `app/static/js/ph.js` - Updated dose logic, badge visibility, chart refresh
- `app/static/js/settings.js` - Added maintenance override toggle in Safety tab

---

**Status**: ✅ Ready for deployment testing
**Tests**: ✅ 15 passed, 0 failed
**Branch**: `fix/ph-manual-restore`
**Target Pi**: 192.168.88.49
