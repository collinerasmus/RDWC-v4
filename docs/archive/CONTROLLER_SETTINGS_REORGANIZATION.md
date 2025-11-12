# UI Reorganization Complete - Controller Settings Distribution

## Summary
Successfully reorganized the RDWC dashboard by:
1. Merging Camera + Overview tabs into a single Overview tab
2. Distributing controller-specific settings from System Settings tab to their respective controller tabs
3. All controller settings now appear in collapsible `<details>` sections (default hidden)
4. System Settings tab now only contains truly general/system-wide settings

## Changes Made

### 1. index.html Updates

#### pH Controller Tab
Added collapsible settings section with:
- **Target Range**: Low pH, High pH
- **Dosing Parameters**: Grow/Micro/Bloom pulse amounts, Max ml/hour, Max ml/day, Mix delay, pH Up ml/s calibration
- **Alert Thresholds**: Low alert pH, High alert pH
- Save button wired to controller_settings.js

#### EC Controller Tab
Added collapsible settings section with:
- **Target Range**: Target EC (ppm), Tolerance (ppm)
- **Alert Thresholds**: Low alert EC, High alert EC
- Save button wired to controller_settings.js

#### Temperature Controller Tab
Enhanced existing collapsible settings section with:
- **Temperature Settings**: Target (°C), Hysteresis (°C), Growth stage
- **Alert Thresholds**: Low alert (°C), High alert (°C)
- **Chiller Safety**: Min OFF time (s), Min ON time (s)
- **Manual Override**: Emergency force ON/OFF controls
- Save button wired to controller_settings.js

#### Circulation Controller Tab
Added collapsible settings section with:
- **Pump Safety Settings**: Main pump min OFF (s), Chiller pump min OFF (s)
- Save button wired to controller_settings.js

#### Script Loading
- Added `controller_settings.js` to dynamic script loading chain
- Order: range.js → trends.js → ph_chart.js → ph.js → settings.js → **controller_settings.js** → relays_v2.js → tabs.js → lights_control.js → chiller.js → schedule.js → sensors.js → overview.js

### 2. New File: controller_settings.js
Created comprehensive settings handler for all controller tabs:
- **initPhSettings()**: Loads and saves pH-related settings (11 fields)
- **initEcSettings()**: Loads and saves EC-related settings (4 fields)
- **initTempSettings()**: Loads and saves temperature-related settings (5 fields)
- **initCircSettings()**: Loads and saves circulation pump safety settings (2 fields)

Each init function:
- Fetches current settings from `/api/settings`
- Populates form fields on load
- Handles save button click
- POSTs updated settings to `/api/settings`
- Updates UI displays (pH band, EC band, temp target, etc.)
- Shows success/error alerts

### 3. settings.js Updates
Removed controller-specific settings from GROUP_DEF:

#### Removed Groups
- **targets**: Entire group removed (pH/EC/temp targets now in controller tabs)
- **dosing**: Entire group removed (pH dosing params now in pH Controller tab)

#### Removed Fields from Existing Groups
From **safety** group:
- `main_pump_min_off_s` → moved to Circulation Controller
- `chiller_pump_min_off_s` → moved to Circulation Controller  
- `chiller_min_off_s` → moved to Temperature Controller
- `chiller_min_on_s` → moved to Temperature Controller

From **alerts** group:
- `ph_hi_alert` → moved to pH Controller
- `ph_lo_alert` → moved to pH Controller
- `ec_hi_alert` → moved to EC Controller
- `ec_lo_alert` → moved to EC Controller
- `temp_hi_alert` → moved to Temperature Controller
- `temp_lo_alert` → moved to Temperature Controller

#### Remaining in System Settings Tab
- **General**: grow_name, timezone, reservoir_liters, grow_start_date (4 fields)
- **Safety**: estop_persist, allow_force, maintenance_override, allow_stale_on_override (4 fields)
- **Alerts**: email_to, alert_cooldown_s (2 fields)
- **UI**: default_sensor_range, relays_poll_ms, sensors_poll_ms (3 fields)
- **Calibration**: Custom pH/EC/Dosing calibration UI (custom-rendered)

**Total**: 13 general settings + calibration tools remain in System Settings

## Benefits

### User Experience
1. **Contextual Settings**: Settings appear near the controls they affect
2. **Reduced Clutter**: System Settings tab is cleaner with only 13 general fields
3. **Logical Organization**: pH settings → pH tab, EC settings → EC tab, etc.
4. **Progressive Disclosure**: Settings hidden by default in collapsible sections
5. **Consistent Pattern**: All controller tabs follow same collapsible `<details>` pattern

### Maintainability
1. **Separation of Concerns**: Controller-specific logic isolated from general system settings
2. **Easier Testing**: Can test controller settings independently
3. **Clear Ownership**: Each controller tab owns its settings
4. **Reduced Cognitive Load**: Settings grouped by functional area

## Settings Distribution Map

| Setting | Original Location | New Location |
|---------|------------------|--------------|
| ph_low, ph_high | System Settings → Targets | pH Controller |
| pulse_ml_grow/micro/bloom | System Settings → Dosing | pH Controller |
| max_ml_hour, max_ml_day | System Settings → Dosing | pH Controller |
| mix_delay_s | System Settings → Dosing | pH Controller |
| ph_up_ml_per_sec | System Settings → Dosing | pH Controller |
| ph_hi_alert, ph_lo_alert | System Settings → Alerts | pH Controller |
| ec_target, ec_tolerance | System Settings → Targets | EC Controller |
| ec_hi_alert, ec_lo_alert | System Settings → Alerts | EC Controller |
| temp_target_c | System Settings → Targets | Temperature Controller |
| temp_hi_alert, temp_lo_alert | System Settings → Alerts | Temperature Controller |
| chiller_min_off_s, chiller_min_on_s | System Settings → Safety | Temperature Controller |
| main_pump_min_off_s | System Settings → Safety | Circulation Controller |
| chiller_pump_min_off_s | System Settings → Safety | Circulation Controller |

**Total moved**: 22 settings across 4 controller tabs

## File Changes Summary

### Modified Files
1. **app/static/index.html** (4 controller sections enhanced, script loading updated)
2. **app/static/js/settings.js** (GROUP_DEF simplified, 22 fields removed)

### New Files
1. **app/static/js/controller_settings.js** (247 lines, 4 controller handlers)

## Testing Checklist

Before deployment, verify:
- [ ] All controller tabs load without errors
- [ ] Settings sections are collapsible (default closed)
- [ ] Each "Save" button is wired correctly
- [ ] Settings load from API on tab open
- [ ] Settings save successfully via POST to /api/settings
- [ ] UI displays update after save (pH band, EC band, temp target)
- [ ] System Settings tab shows only general settings
- [ ] No duplicate settings between System Settings and controller tabs
- [ ] All moved settings function identically in new location
- [ ] Calibration UI still works in System Settings

## Deployment Steps

1. **Backup current files**:
   ```bash
   ssh pi@10.0.0.66
   cd /home/pi/RDWC-v4
   cp -r app/static app/static.backup.$(date +%Y%m%d_%H%M%S)
   ```

2. **Deploy updated files**:
   ```powershell
   # From Windows PC
   scp app/static/index.html pi@10.0.0.66:/home/pi/RDWC-v4/app/static/
   scp app/static/js/settings.js pi@10.0.0.66:/home/pi/RDWC-v4/app/static/js/
   scp app/static/js/controller_settings.js pi@10.0.0.66:/home/pi/RDWC-v4/app/static/js/
   ```

3. **Clear browser cache**:
   - Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
   - Or append `?v=$(date +%s)` to URL to bust cache

4. **Verify deployment**:
   - Open dashboard in browser
   - Navigate to each controller tab (pH, EC, Temperature, Circulation)
   - Expand settings section in each tab
   - Verify settings load correctly
   - Make a test change and save in one tab
   - Confirm save succeeds and UI updates

5. **Monitor for errors**:
   ```bash
   ssh pi@10.0.0.66
   journalctl -u rdwc -f
   ```

## Rollback Plan

If issues occur:
```bash
ssh pi@10.0.0.66
cd /home/pi/RDWC-v4
# Find most recent backup
ls -la app/static.backup.*
# Restore backup (replace with actual backup timestamp)
rm -rf app/static
mv app/static.backup.YYYYMMDD_HHMMSS app/static
sudo systemctl restart rdwc
```

## Next Steps

1. Deploy and test on Pi
2. Verify all controller settings work correctly
3. Test settings persistence across page refresh
4. Verify settings sync between System Settings tab and controller tabs (if opened simultaneously)
5. Document any edge cases or issues found
6. Consider adding "Dirty" indicators to controller settings forms
7. Consider syncing controller settings to System Settings tab in real-time (if needed)

## Notes

- All settings still use same backend `/api/settings` endpoint
- No backend changes required - purely UI reorganization
- Settings remain backward compatible
- System Settings tab calibration UI unchanged
- Temperature Controller already had collapsible section - enhanced it with more fields
- All other controllers follow same pattern now

## Status: ✅ READY FOR TESTING

All code changes complete. Ready for deployment and testing on Pi.
