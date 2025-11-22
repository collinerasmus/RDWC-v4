# UI Cleanup and Circulation Interlock - Deployment Guide

This guide provides instructions for deploying the UI cleanup and circulation safety interlock features to the Pi.

## What's New

### UI Cleanup
1. **Single E-STOP Button**: Consolidated to main header (top-right), removed from all tab headers
2. **Mode Control Centralized**: Mode selection removed from Overview, Sensors, Schedule tabs - now only in System tab
3. **Cleaner Interface**: Less clutter, more focused controls

### Circulation Safety Interlock
1. **Three-Layer Safety System**:
   - Main Pump must be ON before chiller can start
   - Chiller auto-starts chiller pump when turning ON
   - Chiller pump cannot turn OFF while chiller is running

2. **Real-Time Status**:
   - Interlock banner shows current state
   - Pre-flight checks before operations
   - Clear error messages when blocked

## Deployment Instructions

### Step 1: Deploy to Pi

From your Windows machine with PowerShell:

```powershell
# Set Pi connection details
$env:PI_HOST = "192.168.88.49"
$env:PI_USER = "pi"

# Deploy this branch
ssh pi@192.168.88.49 'cd RDWC-v4 && git fetch origin && git checkout copilot/remove-duplicate-pump-calibrations-again && git pull'

# Restart services
ssh pi@192.168.88.49 'sudo systemctl restart rdwc.service && sudo systemctl restart rdwc-sensors.service'

# Wait for services to start
Start-Sleep -Seconds 5

# Verify services are running
ssh pi@192.168.88.49 'systemctl is-active rdwc.service rdwc-sensors.service'
```

### Step 2: Verify UI Changes

Open browser to http://192.168.88.49:8080

**Check E-STOP:**
1. Look for single E-STOP button in top-right of header (next to build info)
2. Navigate between tabs - should NOT see E-STOP buttons in tab headers
3. Click E-STOP button - should turn red and say "E-STOP ACTIVE"
4. All tabs should update within 2-3 seconds
5. Release E-STOP - button returns to normal

**Check Mode Control:**
1. Go to Overview tab - should NOT see Auto/Manual/Maintenance buttons
2. Go to Sensors tab - should NOT see mode buttons
3. Go to Schedule tab - should NOT see mode buttons
4. Go to System tab - SHOULD see mode selection buttons (only place they exist)

### Step 3: Test Circulation Interlock

**Scenario A: Normal Operation**
1. Ensure E-STOP is OFF (released)
2. Go to Circulation tab
3. Turn ON main pump
4. Go to Chiller tab
5. Use Force ON button for chiller
6. **Expected**: Chiller turns ON, chiller pump auto-starts
7. **Expected**: Green banner "✅ INTERLOCK ACTIVE: Chiller running with circulation pumps"

**Scenario B: Interlock Protection**
1. Turn OFF main pump (via Circulation tab)
2. Go to Chiller tab
3. Try to Force ON chiller
4. **Expected**: Error message "Cannot turn ON chiller: Main pump must be ON first (circulation required)"
5. **Expected**: Red banner "⚠️ INTERLOCK: Main pump must be ON before chiller can start"

**Scenario C: Pump Protection**
1. With chiller running (from Scenario A)
2. Go to Circulation tab
3. Try to turn OFF chiller pump
4. **Expected**: Blocked with message about chiller running
5. Go to Chiller tab
6. Turn OFF chiller first
7. **Expected**: Chiller turns OFF
8. Now chiller pump can be turned OFF

## Verification Checklist

- [ ] Single E-STOP button visible in main header (top-right)
- [ ] No E-STOP buttons in tab headers (Overview, Sensors, Temp, Lights, Circulation, pH, EC)
- [ ] Mode buttons only in System tab
- [ ] E-STOP toggle updates all tabs within 3 seconds
- [ ] Main pump ON allows chiller to start
- [ ] Chiller auto-starts chiller pump
- [ ] Interlock banner shows correct status
- [ ] Cannot start chiller without main pump
- [ ] Cannot stop chiller pump while chiller running
- [ ] All services running without errors

## Rollback Procedure

If issues are found:

```powershell
# Rollback to previous commit
ssh pi@192.168.88.49 'cd RDWC-v4 && git checkout main && git pull'

# Restart services
ssh pi@192.168.88.49 'sudo systemctl restart rdwc.service rdwc-sensors.service'
```

## Troubleshooting

### Issue: E-STOP Button Not Working
**Check**: Browser cache - do hard refresh (Ctrl+F5)
**Check**: JavaScript console for errors (F12 → Console tab)
**Fix**: Clear cache or check if relays_v2.js loaded correctly

### Issue: Interlock Not Working
**Check**: Backend logs: `ssh pi@192.168.88.49 'journalctl -u rdwc.service -n 50'`
**Look for**: "[CHILLER INTERLOCK]" messages in logs
**Fix**: Verify relays_core.py has updated set_chiller_power() function

### Issue: Chiller Pump Not Auto-Starting
**Check**: Logs for "Auto-starting chiller_pump" message
**Check**: Main pump was actually ON before chiller turned ON
**Fix**: Verify interlock logic in relays_core.py lines 566-596

### Issue: Mode Buttons Still Visible
**Check**: Browser cache - do hard refresh
**Check**: Correct branch deployed (`git branch --show-current` should show the new branch)
**Fix**: Verify index.html has updated header sections

## Technical Details

### Files Changed
- `app/static/index.html` - E-STOP consolidation, mode button removal
- `app/static/js/relays_v2.js` - Global E-STOP wiring
- `app/static/js/chiller.js` - Interlock UI and status
- `app/relays_core.py` - Interlock enforcement
- `app/chiller_control.py` - Updated logic

### Safety Features
1. **Interlock Reasons**: 
   - `interlock_main_pump_off` - Main pump prerequisite
   - `interlock_chiller_running` - Pump protection
   - `chiller_autostart` - Auto-start reason

2. **Error Messages**:
   - Clear, actionable messages
   - Logged to backend for troubleshooting
   - Displayed in UI toasts and banners

3. **Status Indicators**:
   - Green: INTERLOCK ACTIVE (system running correctly)
   - Red: INTERLOCK blocked (prerequisite not met)
   - Gray: STANDBY (ready to start)

## Success Criteria

All of the following must be true:

✅ Single E-STOP button in main header only
✅ Mode buttons only in System tab
✅ Chiller requires main pump ON
✅ Chiller auto-starts chiller pump
✅ Chiller pump protected while chiller running
✅ Interlock banner shows correct real-time status
✅ All error messages are clear and actionable
✅ No JavaScript errors in console
✅ Services running without backend errors

## Support

If you encounter issues:
1. Check logs: `journalctl -u rdwc.service -n 100`
2. Check browser console (F12)
3. Verify correct branch deployed
4. Try hard refresh (Ctrl+F5)
5. Review this troubleshooting section

## Next Steps

After successful deployment and verification:
1. Monitor system for 24 hours
2. Check for any unexpected behavior
3. Review backend logs for interlock triggers
4. Update documentation if needed
5. Consider merging to main branch if stable
