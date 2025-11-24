# RDWC-v4 Current Status
**Last Updated:** 2025-11-24
**Maintained By:** Single AI Coordinator
**System Version:** See VERSION file

## What Works ✅

### Backend
- ✅ **Mode Switching:** System mode (auto/manual/maintenance) propagates correctly to all 5 controllers
- ✅ **API Endpoints:** All `/api/system_mode` and `/api/controllers/status` endpoints functional
- ✅ **Controller Modes:** ph, ec, chiller, lights, circulation all sync with system mode
- ✅ **Sensors Mode:** Separate sensor mode syncs with system mode
- ✅ **Database:** SQLite persistence working correctly
- ✅ **Relay Control:** relays_core.py provides safe relay operations
- ✅ **E-Stop:** Emergency stop functionality works and persists
- ✅ **Tests:** 154 tests passing

### Frontend  
- ✅ **Mode Buttons:** Visual indication of current mode
- ✅ **Relay Controls:** Toggle buttons for all relays
- ✅ **Sensor Display:** Real-time sensor readings
- ✅ **Commissioning UI:** Calibration interfaces for pH, EC, dosing pumps

## What Was Fixed Today 🔧

### Issue #1: UI Stability
**Problem:** UI seemed to "go offline" after a few minutes, multiple reloads on initial load

**Root Cause:** Aggressive polling causing backend stress
- Relays polling every 1 second
- E-stop every 2 seconds
- System mode every 3 seconds
- Multiple concurrent requests overwhelming backend

**Fix Applied:**
- Reduced relay polling: 1s → 3s
- Reduced E-stop polling: 2s → 5s  
- Reduced system mode polling: 3s → 5s
- Updated default APP_POLL settings: `{relays: 3000, sensors: 10000}`

### Issue #2: Mode Switch Race Condition
**Problem:** Mode button click might conflict with automatic polling

**Root Cause:** Polling refreshSystemMode() could interfere with manual setSystemMode()

**Fix Applied:**
- Added debouncing: track `lastModeChangeTimestamp`
- Skip polling for 5 seconds after manual mode change
- Prevents race condition between user action and automatic refresh

**Code Changes:**
```javascript
// Track manual mode changes
let lastModeChangeTimestamp = 0;

async function setSystemMode(mode) {
  lastModeChangeTimestamp = Date.now();  // Mark manual change
  // ... rest of code ...
}

async function refreshSystemMode() {
  // Skip if manual change was recent
  if (Date.now() - lastModeChangeTimestamp < 5000) return;
  // ... rest of code ...
}
```

## What's Next ⏭️

### Immediate (Today)
1. **Test UI Stability**
   - Open browser
   - Monitor for 15+ minutes
   - Verify no "offline" issues
   - Test mode switching 10 times

2. **Complete Commissioning**
   - Switch to manual mode
   - Calibrate dosing pumps
   - Prime pumps with nutrients
   - Switch back to auto
   - Verify automation starts

3. **Documentation Cleanup**
   - Consolidate commissioning docs
   - Archive old mode issue docs
   - Create master COMMISSIONING.md

### Short Term (This Week)
4. **Add Error Recovery**
   - Exponential backoff on failed requests
   - Circuit breaker pattern
   - "Reconnecting..." UI banner
   - Better error messages

5. **Optimize Requests**
   - Use consolidated `/api/controllers/status` more
   - Reduce individual controller polls
   - Add HTTP caching headers

6. **Complete Testing**
   - Full commissioning workflow end-to-end
   - 1+ hour stability test
   - Mode switching stress test (100 cycles)

### Medium Term (This Month)
7. **Code Quality**
   - Remove dead code
   - Add type hints
   - Improve logging
   - Documentation generation

## Known Issues ⚠️

### Minor Issues
- **Documentation Overload:** 10+ commissioning docs, 4+ mode issue docs - needs consolidation
- **Sensor Power Cycle:** Optional feature, works when `RDWC_SENSOR_POWER_PIN` configured
- **Legacy Mode Mapping:** controller_modes uses auto/hold with legacy mapping (manual→hold) - may cause confusion

### Not Issues
- ❌ **Mode switching doesn't work** - FALSE, backend works perfectly (tested and confirmed)
- ❌ **Backend is broken** - FALSE, all APIs responding correctly
- ❌ **Database corruption** - FALSE, SQLite working correctly

## Architecture Reference

### System Modes
- **System Mode:** Master mode in `settings.system_mode` (auto/manual/maintenance)
- **Controller Modes:** Individual modes for 5 controllers (ph, ec, lights, chiller, circulation)
- **Sensor Mode:** Separate mode for sensors in `settings.sensor_mode`
- **Propagation:** System mode changes cascade to all controllers via `system_mode.set_system_mode(propagate_to_controllers=True)`

### Polling Intervals (After Today's Fix)
- **Relays:** 3 seconds (was 1s)
- **E-Stop:** 5 seconds (was 2s)
- **System Mode:** 5 seconds (was 3s)
- **Sensors:** 10 seconds (configurable via APP_POLL.sensors)
- **Chiller:** 5 seconds
- **Global Health:** 10 seconds

### Key Files
- **Backend:**
  - `app/main.py` - FastAPI application, all endpoints
  - `app/system_mode.py` - System mode management
  - `app/controller_modes.py` - Individual controller modes
  - `app/relays_core.py` - Relay control with safety guards
  - `app/sensors_core.py` - Sensor reading with I²C stabilization

- **Frontend:**
  - `app/static/js/relays_v2.js` - Mode switching, relay controls
  - `app/static/js/sensors.js` - Sensor display and mode
  - `app/static/js/overview.js` - System overview dashboard
  - `app/static/js/ph.js` - pH control and calibration
  - `app/static/js/ec.js` - EC control and calibration

## Testing Commands

### Backend Mode Test
```powershell
# Set to manual
$body = @{mode = "manual"} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/system_mode" -Method POST -Body $body -ContentType "application/json"

# Check propagation
$status = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/controllers/status"
$status.system_mode  # Should be "manual"
$status.controllers | ForEach-Object { $_.PSObject.Properties | ForEach-Object { "$($_.Name): $($_.Value.mode)" } }

# Set to auto
$body = @{mode = "auto"} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/system_mode" -Method POST -Body $body -ContentType "application/json"
```

### Run Tests
```powershell
cd "c:\Users\USER-PC\OneDrive\Documents\GitHub\RDWC-v4"
& .\venv\Scripts\python.exe -m pytest -v
```

### Start Dev Server
```powershell
cd "c:\Users\USER-PC\OneDrive\Documents\GitHub\RDWC-v4"
& .\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
```

## Success Criteria for Commissioning

- [x] Backend mode switching works (CONFIRMED)
- [ ] UI stays stable for 15+ minutes
- [ ] Mode button clicks work 100% of time  
- [ ] Can switch system to manual
- [ ] Can calibrate dosing pumps in manual mode
- [ ] Can prime pumps with nutrients
- [ ] Can switch back to auto
- [ ] Automation starts and runs correctly
- [ ] No console errors
- [ ] No backend errors in logs

## Contact / Notes

This is a single-operator system now. All changes should go through this coordinated effort to avoid "too many chefs in the kitchen" syndrome that caused previous issues.

Changes today focused on:
1. Diagnosing and understanding actual behavior (backend works!)
2. Fixing UI stability through reduced polling
3. Preventing race conditions with debouncing
4. Documenting current state clearly

Next operator session should focus on testing these changes and completing commissioning workflow.
