# Controller Mode Synchronization Issue

## Problem Statement
When changing system mode on the Overview tab, the individual controller tabs (Sensors, Circulation, Lights, Schedule) do NOT update their UI mode buttons to reflect the change. Similarly, when changing system mode from Manual to Auto, the controller tabs remain showing their old mode.

## Expected Behavior
1. **Top-down sync**: Change system mode to "Manual" on Overview → All controller tabs should show "Manual" within seconds
2. **Bottom-up sync**: Change all controllers to "Manual" individually → Overview system mode should switch to "Manual" 
3. **Live updates**: Controller tab UIs should refresh when system mode changes, not require page reload

## Current Status (What Works)
✅ Backend propagation: `/api/system_mode` POST correctly updates all controller modes in database
✅ Backend state is correct: `/api/controllers/status` shows all controllers with correct modes
✅ Overview system mode polling: Updates every 3 seconds
✅ Individual controller polling: Each polls their mode every 5 seconds

## Current Status (What Fails)
❌ Sensors tab buttons don't update when system mode changes
❌ Circulation tab buttons don't update when system mode changes  
❌ Lights tab buttons may not update when system mode changes
❌ Schedule tab buttons don't update (but schedule has no backend endpoint)

## Root Cause Analysis

### Architecture Overview
- **Backend**: 5 controllers tracked in `controller_modes.py`: `["ph", "ec", "lights", "chiller", "circulation"]`
- **Frontend**: 5+ controller UIs with mode buttons: Sensors, pH, EC, Circulation, Lights, Schedule
- **System mode**: Master mode stored in settings table, propagates to all controllers via `system_mode.py::set_system_mode()`

### Code Flow (Expected)
1. User clicks "Manual" on Overview
2. `relays_v2.js::setSystemMode()` → POST `/api/system_mode` with `{mode: "manual"}`
3. Backend `app/main.py::set_system_mode_api()` calls `system_mode.set_system_mode("manual", propagate_to_controllers=True)`
4. `system_mode.py` updates settings table AND calls `controller_modes.set_mode()` for each controller
5. Backend state now correct ✓
6. Frontend `refreshAllControllerModes()` calls each controller's sync function
7. Each controller: `refreshServerMode()`, `syncCircModeFromBackend()`, `syncLightsModeFromBackend()`, `syncScheduleModeFromBackend()`
8. Sync functions fetch from `/api/sensors/mode`, `/api/controller/circulation/mode`, etc.
9. UI updates buttons to show new mode

### Where It's Failing
The UI buttons are not updating even though:
- Backend state is correct (verified via `/api/controllers/status`)
- Polling is active (every 5 seconds per controller)
- Sync functions are being called (should be visible in console logs)

### Potential Issues

#### 1. **Sync Functions Not Actually Updating UI**
The sync functions fetch the mode but may not be calling the right UI update functions:
- `sensors.js::refreshServerMode()` - calls `setActive()` on buttons
- `circulation.js::syncCircModeFromBackend()` - calls `circSetMode(mode, false)` which should update buttons
- `lights_v2.js::syncModeFromBackend()` - calls `setMode(mode, false)` which should update buttons
- `schedule.js::syncScheduleModeFromBackend()` - calls `scheduleSetMode(mode)` which should update buttons

**Check**: Are these UI update functions actually manipulating the DOM correctly?

#### 2. **Button State Management Issues**
Each controller uses different patterns:
- **Sensors**: `btn.classList.add('active')` / `btn.classList.remove('active')`
- **Circulation**: `btn.classList.toggle('active', m === next)`
- **Lights**: `btn.classList.add('active')` / `btn.classList.remove('active')`
- **Schedule**: `btn.classList.toggle('active', m === next)`

**Check**: Are button IDs correct? Are buttons actually in DOM when functions run?

#### 3. **Async Timing Issues**
- `refreshAllControllerModes()` waits 100ms then calls all syncs in parallel with `Promise.all()`
- Individual controller syncs may complete before backend fully updates
- Race condition between POST completing and sync functions reading

**Check**: Does adding longer delays help?

#### 4. **Mode Value Mismatches**
- Backend uses: "auto", "manual", "maintenance"
- Some UIs use: "auto", "manual", "maint" (shortened)
- Normalization code exists but may not be applied everywhere

**Check**: Are mode values being normalized correctly in all sync functions?

#### 5. **Endpoint Availability**
- `/api/sensors/mode` - exists? ✓ (assumed)
- `/api/controller/circulation/mode` - exists? ✓ (assumed)
- `/api/controller/lights/mode` - exists? ✓ (assumed)
- `/api/controller/schedule/mode` - does NOT exist (schedule is frontend-only)

**Check**: Are sync functions failing silently due to 404s?

## Files Involved

### Backend
- `app/system_mode.py` - `set_system_mode()` with propagate_to_controllers
- `app/controller_modes.py` - `set_mode()`, `get_all_modes()`, CONTROLLERS list
- `app/main.py` - `/api/system_mode`, `/api/controllers/status`, controller mode endpoints

### Frontend
- `app/static/js/relays_v2.js` - `setSystemMode()`, `refreshAllControllerModes()`, `syncSystemModeFromControllers()`
- `app/static/js/sensors.js` - `refreshServerMode()`, `sensorsSetMode()`, mode buttons
- `app/static/js/circulation.js` - `syncCircModeFromBackend()`, `circSetMode()`, mode buttons
- `app/static/js/lights_v2.js` - `syncModeFromBackend()`, `setMode()`, mode buttons
- `app/static/js/schedule.js` - `syncScheduleModeFromBackend()`, `scheduleSetMode()`, mode buttons

## Debugging Steps

### Step 1: Verify Backend Endpoints
```bash
# Test system mode change
curl -X POST http://localhost:8080/api/system_mode -H "Content-Type: application/json" -d '{"mode":"manual"}'

# Verify propagation worked
curl http://localhost:8080/api/controllers/status | jq '.controllers | map_values(.mode)'

# Check individual endpoints
curl http://localhost:8080/api/sensors/mode
curl http://localhost:8080/api/controller/circulation/mode
curl http://localhost:8080/api/controller/lights/mode
curl http://localhost:8080/api/controller/schedule/mode  # Should 404
```

### Step 2: Add Console Logging
Add verbose logging to each sync function to see:
- When it's called
- What endpoint it fetches
- What response it gets
- What UI update it attempts
- Whether UI update succeeded

### Step 3: Test Button Updates Manually
In browser console:
```javascript
// Test sensors button update
document.getElementById('sensors-mode-manual').classList.add('active')
document.getElementById('sensors-mode-auto').classList.remove('active')

// Test circulation button update
document.getElementById('circ-mode-manual').classList.add('active')
document.getElementById('circ-mode-auto').classList.remove('active')

// Check if buttons exist
console.log('Sensors buttons:', {
  auto: document.getElementById('sensors-mode-auto'),
  manual: document.getElementById('sensors-mode-manual'),
  maint: document.getElementById('sensors-mode-maint')
})
```

### Step 4: Check Polling is Active
In browser console after hard refresh:
```javascript
// Should see these logs every 5 seconds:
// [Sensors] Synced mode from backend: auto
// [Circulation] Synced mode from backend: auto
// [Lights] Synced mode from backend: auto
// [Schedule] Synced mode from backend: auto

// Check if functions exist
console.log('Sync functions:', {
  sensors: typeof window.refreshServerMode,
  circ: typeof window.syncCircModeFromBackend,
  lights: typeof window.syncLightsModeFromBackend,
  schedule: typeof window.syncScheduleModeFromBackend,
  system: typeof window.syncSystemModeFromControllers
})
```

### Step 5: Test End-to-End Flow
1. Open browser console (F12)
2. Hard refresh (Ctrl+Shift+R)
3. Go to Overview tab
4. Click "Manual" button
5. Watch console logs - should see:
   - `[System] Refreshing all controller modes from backend...`
   - Multiple sync messages from controllers
   - `[System] All controller modes refreshed`
6. Switch to Sensors tab - buttons should show Manual active
7. Wait 5 seconds - should see `[Sensors] Synced mode from backend: manual`

## Proposed Fix Strategy

### Option A: Increase Polling Frequency
Change from 5s to 2s intervals for faster updates

### Option B: Add Event-Based Sync
Fire custom event when system mode changes:
```javascript
window.dispatchEvent(new CustomEvent('system-mode-changed', {detail: {mode: 'manual'}}))
```
Controllers listen and update immediately

### Option C: Direct Button Updates
After system mode change, directly update all visible controller buttons without waiting for backend sync

### Option D: Unified Mode State
Create a single source of truth in `relays_v2.js` that all controllers read from

## Success Criteria
1. Change system mode to Manual on Overview → All visible controller tabs update buttons within 1 second
2. Change system mode to Auto on Overview → All visible controller tabs update buttons within 1 second  
3. No page refresh required
4. Console shows clear sync progression
5. Works consistently across 10+ test cycles

## Current Commits Related to This Issue
- `1bb9b7f` - Fix: Add periodic mode polling for all controllers (5s interval)
- `61d333f` - Fix: Add system mode polling and enhanced debug logging
- `1e45ec2` - Fix: Add bidirectional mode synchronization
- `9ac6077` - Fix: Improve controller mode synchronization with proper async handling
- `493caa8` - Fix: UI controller tabs now refresh modes when system mode changes

## Next Steps for GitHub Copilot Agent
1. Review all console logs during mode change to identify where sync is failing
2. Verify all button IDs match between HTML and JavaScript
3. Test if manual button classList manipulation works (proves DOM access)
4. Add comprehensive logging to every sync function
5. Identify the exact point where mode data is fetched but UI doesn't update
6. Implement fix based on findings
7. Test thoroughly with user confirmation
