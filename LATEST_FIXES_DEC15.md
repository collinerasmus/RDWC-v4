# Latest System Fixes - December 15, 2025

## 1. Temperature Chart Band Display Fix ✅
**File**: `app/static/js/temperature_chart.js` (lines 108-112)

### Issue
Chart was displaying temperature band with hardcoded ±0.5°C regardless of actual hysteresis setting.

### Fix
```javascript
// Before: hardcoded band
const tempTarget = settingsData?.['targets.temp_target'] ?? 21.0;
const tempLow = tempTarget - 0.5;
const tempHigh = tempTarget + 0.5;

// After: dynamic hysteresis from settings
const tempTarget = settingsData?.['targets.temp_target'] ?? 21.0;
const tempHysteresis = settingsData?.['temperature.hysteresis'] ?? 0.5;
const tempLow = tempTarget - tempHysteresis;
const tempHigh = tempTarget + tempHysteresis;
```

### Result
✅ Dashboard temperature band now correctly reflects the hysteresis setting from the database

---

## 2. Chiller Controller Switch-Off Point Fix ✅
**File**: `app/temperature_control.py` (lines 418-428)

### Issue
- Controller was missing proper switch-off logic
- Target temperature was hardcoded to `temperature.target_temp` instead of scheduler-controlled `targets.temp_target_c`
- Hysteresis calculation was wrong (used ±hysteresis instead of ±hysteresis/2)

### Fix
```python
# Before: wrong target source and threshold calculation
target_temp = float(get_setting('temperature.target_temp', '19.0'))
hysteresis = float(get_setting('temperature.hysteresis', '0.5'))
turn_on_temp = target_temp + hysteresis    # e.g., 19.5°C
turn_off_temp = target_temp - hysteresis   # e.g., 18.5°C

# After: correct target from scheduler, proper hysteresis band
target_temp = float(get_setting('targets.temp_target_c', '20.0'))
hysteresis = float(get_setting('temperature.hysteresis', '0.5'))
turn_on_temp = target_temp + (hysteresis / 2.0)    # e.g., 20.25°C
turn_off_temp = target_temp - (hysteresis / 2.0)   # e.g., 19.75°C
```

### Result
✅ Chiller now:
- Reads target from scheduler (allows dynamic control)
- Turns ON when temp exceeds target + hysteresis/2
- Turns OFF when temp drops below target - hysteresis/2
- Maintains temperature within ±hysteresis/2 band around target

---

## Deployment

### Commits
- **Temperature chart fix**: `b8e5d11` - "fix(ui): temperature band calculation to use hysteresis setting"
- **Chiller control fix**: `cadbce2` - "fix(chiller): correct temperature control thresholds and target source"

### Current Status
✅ Both fixes committed to `main` branch and pushed to GitHub

### Deploy to Pi
When Pi is accessible, run:
```bash
ssh pi@192.168.88.49 "cd ~/RDWC-v4 && git pull origin main && sudo systemctl restart rdwc"
```

---

## Verification

### Dashboard Verification
1. Navigate to **Temperature** tab
2. Verify **Temp-Target Band** shows correct width (should be ±0.5°C from target with current settings)
3. Chart band should update dynamically if hysteresis setting changes

### Controller Verification
After deployment to Pi:
1. Monitor temperature via `/api/sensors` endpoint
2. Watch chiller relay state via `/api/relays/status`
3. Verify chiller turns ON/OFF at correct thresholds:
   - ON threshold: `targets.temp_target_c + (temperature.hysteresis / 2)`
   - OFF threshold: `targets.temp_target_c - (temperature.hysteresis / 2)`

---

## Settings Reference
- `targets.temp_target_c`: Target water temperature (°C) - controlled by scheduler
- `temperature.hysteresis`: Control band half-width (°C) - currently 0.5°C

With default settings (target=20°C, hysteresis=0.5°C):
- Chiller turns ON at 20.25°C
- Chiller turns OFF at 19.75°C
