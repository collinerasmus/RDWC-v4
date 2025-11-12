# UI Reorganization - Calibration Consolidation

**Date:** 2025-01-XX  
**Status:** ✅ COMPLETE  
**Agent Execution:** Autonomous (user observes UI)

## Objective
Consolidate all calibration wizards into Settings → Calibration tab, eliminating duplication and creating a unified calibration interface.

## Problem Identified
User review revealed:
- **pH Calibration**: ✅ Already in Settings → Calibration only
- **Dosing Calibration**: ✅ Already in Settings → Calibration only
- **EC Calibration**: ❌ DUPLICATED
  - Incomplete 6-line placeholder in Settings → Calibration
  - Full 40-line wizard in EC Controller → Calibration tab
- Confusion from having calibration in controller cards AND Settings

## Changes Made

### 1. Settings → Calibration Tab (`app/static/js/settings.js`)
**Status:** ✅ Complete

**Replaced:** 6-line EC placeholder "coming soon" message  
**With:** Full 42-line EC Calibration wizard including:
- Warning banner (calibration affects all readings)
- Current status grid (Cal status, K factor, current EC reading)
- Step-by-step instructions (5 steps)
- 4 calibration buttons:
  - Clear Calibration
  - Low Point (1413 µS/cm)
  - High Point (12,880 µS/cm)
  - Set K=1.0
- Message display area with status feedback

**Event Handlers Added:**
```javascript
// 5 EC calibration button handlers added to settings.js
- btnEcCalRefreshStatus → GET /api/ec/cal/status
- btnEcCalClear → POST /api/ec/cal/clear
- btnEcCalLow → POST /api/ec/cal/low
- btnEcCalHigh → POST /api/ec/cal/high
- btnEcCalSetK → POST /api/ec/k (body: {k:1.0})
```

**Initialization:** Added `ecStatus()` to panel load sequence (line 442)

### 2. EC Controller Card (`app/static/index.html`)
**Status:** ✅ Complete

**Removed:**
- Entire EC Calibration tab section (40 lines, lines 1571-1610)
- Calibration tab button and onclick handlers

**Updated:**
- Tab buttons now only toggle 3 tabs: Status, Manual, Auto
- Removed all references to `ec-tab-calibration` from onclick handlers

### 3. Final UI Structure
**Status:** ✅ Verified

#### Controller Cards (pH & EC)
Both controllers now have identical 3-tab structure:
- **Status** - Recent dose history
- **Manual** - Direct dosing controls
- **Auto** - Automation toggle and learned values

#### Settings → Calibration Tab
Unified calibration interface with 3 sections:
1. **pH Calibration** (complete wizard)
   - Read/stabilize functions
   - LED controls (on/off/blink)
   - 3-point calibration (mid/low/high)
   - Clear function
   - Calibration log
2. **EC Calibration** (complete wizard - newly moved)
   - Refresh status
   - Current readings display
   - 1-point or 2-point calibration
   - K factor adjustment
   - Clear function
3. **Dosing Calibration** (complete wizard)
   - Pump selection
   - Prime toggle
   - Run for X seconds
   - Compute & save rate
   - Calibration log

## Benefits
1. **Single Source of Truth**: All calibrations in one place (Settings → Calibration)
2. **No Duplication**: Eliminated incomplete/duplicate EC calibration in controller card
3. **Consistent UX**: Controllers focus on operation (Status/Manual/Auto); Settings handles calibration/configuration
4. **Clear Navigation**: Users know where to find calibrations (Settings tab, not scattered across controller cards)
5. **Reduced Confusion**: No conflicting calibration interfaces

## Verification Checklist
- ✅ Settings → Calibration tab contains pH, EC, Dosing wizards
- ✅ pH Controller has 3 tabs (Status/Manual/Auto)
- ✅ EC Controller has 3 tabs (Status/Manual/Auto)
- ✅ EC calibration event handlers wired to backend endpoints
- ✅ EC status loads on Settings → Calibration panel open
- ✅ No duplicate calibration sections in index.html
- ✅ All calibration buttons have proper onclick handlers

## Testing Required (On Live Pi)
1. Open UI → Settings → Calibration tab
2. Verify all 3 calibration sections render correctly
3. Click "Refresh" in EC Calibration → verify status loads
4. Test EC calibration buttons (Clear/Low/High/SetK) → verify API calls work
5. Confirm pH and Dosing calibrations still function correctly
6. Verify controller cards (pH/EC) show only 3 operational tabs

## Files Modified
- `app/static/js/settings.js` (+54 lines for EC wizard HTML and event handlers)
- `app/static/index.html` (-40 lines removed duplicate EC calibration tab)

## Rollback Plan
If issues arise:
1. Revert `app/static/js/settings.js` to restore placeholder
2. Revert `app/static/index.html` to restore EC calibration tab in controller card
3. Restart web service: `sudo systemctl restart rdwc-api`

## Next Steps
1. Deploy to Pi via `deploy/deploy_controllers.ps1`
2. Restart web service
3. Test calibration UI on live system
4. Document any UI refinements needed
5. Update user documentation with new calibration location

---

**Agent Notes:**
- User requested: "all calibrations need to be at their relevant place, i think ec is duplicated, the one here is incomplete and needs to be deleted"
- Interpreted "relevant place" as Settings → Calibration tab (where pH and Dosing already live)
- Executed consolidation autonomously; user to verify via UI observation
- Architecture matches project convention: Settings for configuration/calibration, Controllers for operation
