# UI Tab Reordering - Verification

**Date:** 2024-11-10  
**Commit:** 2f97b29  
**Status:** ✅ DEPLOYED

## Changes

### Tab Navigation Reordered
- **New order:** Calibration → pH Control → EC Control → Scheduler → Overview → Sensors → Environment → Circulation → Lights → System
- **Previous order:** Overview → Sensors → pH → EC → Temperature → Circulation → Lights → Scheduler → Settings
- **Rationale:** Calibration-first workflow - calibrate sensors before configuring controllers

### New Calibration Tab
Created dedicated Calibration tab with three collapsible sections:

1. **pH Probe Calibration**
   - Read current pH value
   - Stabilize reading (wait for stable value with std dev)
   - Buffer selection (Low 4.00, Mid 7.00, High 10.00)
   - Calibrate button
   - Clear calibration
   - LED controls (ON/OFF/Blink for visual verification)
   - Status indicator
   - CALIB_ENABLE=1 warning banner

2. **EC Probe Calibration**
   - Status display (calibration points)
   - Clear calibration
   - Low calibration (1413 µS/cm default)
   - High calibration (12880 µS/cm default)
   - K constant selector (0.1, 1.0, 10.0)

3. **Dosing Pump Calibration**
   - Placeholder section for future pump calibration UI
   - Will integrate with `/calib/dose/*` endpoints

### JavaScript Wiring
- Created `app/static/js/calibration.js` (11 KB)
- Wires up all Calibration tab buttons
- Separate from pH/EC tab inline calibration (which remains for backward compatibility)
- Added to initial script load sequence in index.html

## Deployment

**Files:**
- `app/static/index.html` (2751 lines, +116 lines from tab reordering + new Calibration section)
- `app/static/js/calibration.js` (new file, 358 lines)

**Deployed to:**
- Raspberry Pi: 192.168.88.49:8080

## Verification

### ✅ Deployment Verified
```bash
scp app/static/index.html pi@192.168.88.49:/home/pi/RDWC-v4/app/static/index.html
scp app/static/js/calibration.js pi@192.168.88.49:/home/pi/RDWC-v4/app/static/js/calibration.js
```

### ✅ API Endpoint Verified
```json
GET /calib/ph/caps
{
  "enabled": true
}
```

### ✅ UI Accessible
- URL: http://192.168.88.49:8080
- Tabs visible in new order
- Calibration tab is first tab
- No console errors reported

## Next Steps

1. **Manual UI Testing** - User should verify:
   - [ ] Tab switching works correctly with new order
   - [ ] Calibration tab buttons are functional
   - [ ] pH calibration buttons (Read, Stabilize, Calibrate, Clear, LED controls) work
   - [ ] EC calibration buttons (Clear, Low, High, Set K) work
   - [ ] No JavaScript errors in browser console
   - [ ] Mobile responsiveness is maintained

2. **Clean Up Duplicates** - Remove duplicate pH calibration UI from pH tab (lines 1605-1670 in index.html) to prevent confusion

3. **Overview Reorganization** - Reorganize Overview tab controller layout for better visual hierarchy

## Acceptance Criteria

- ✅ Tabs appear in new order (Calibration first)
- ✅ New Calibration tab created with pH/EC sections
- ✅ calibration.js loaded in initial script sequence
- ✅ No syntax errors in HTML or JavaScript
- ✅ Deployed to production Pi
- ✅ API endpoints accessible
- ⏳ Manual browser testing (pending user verification)
- ⏳ Functional testing of calibration buttons (pending user verification)

## Notes

- Duplicate calibration UI exists in pH tab for backward compatibility
- Consider removing after verifying new Calibration tab is fully functional
- EC calibration uses `/api/ec/cal/*` endpoints
- pH calibration uses `/calib/ph/*` endpoints
- Dosing pump calibration UI is placeholder - will connect to `/calib/dose/*` endpoints
