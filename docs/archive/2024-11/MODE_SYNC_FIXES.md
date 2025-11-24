# Controller Mode Synchronization Fixes

## Issues Fixed

### 1. System Mode Not Propagating to Controllers ✅
**Problem:** Changing system mode (auto/manual/maintenance) did not update individual controller modes.

**Root Cause:** `set_system_mode()` only updated the `system_mode` setting in the database but didn't propagate changes to individual controllers (`ph`, `ec`, `chiller`, `lights`, `circulation`).

**Fix:**
- Updated `app/system_mode.py::set_system_mode()` to propagate mode changes to all controllers
- Added `propagate_to_controllers` parameter (defaults to `True`)
- Imports `controller_modes.set_mode()` and iterates over all controllers

**Files Modified:**
- `app/system_mode.py`

### 2. Maintenance Mode Not Supported by System Mode ✅
**Problem:** UI had "Maintenance" buttons for system mode, but backend only accepted "auto" and "manual".

**Root Cause:** `system_mode.py` only defined `MODE_AUTO` and `MODE_MANUAL` constants.

**Fix:**
- Added `MODE_MAINTENANCE = "maintenance"` constant
- Added `VALID_MODES = {MODE_AUTO, MODE_MANUAL, MODE_MAINTENANCE}` set
- Updated validation logic to use `VALID_MODES`
- Updated API endpoints to accept maintenance mode
- Updated fast mode setter to propagate maintenance mode

**Files Modified:**
- `app/system_mode.py`
- `app/main.py` (endpoints: `/api/system_mode`, `/api/system_mode/fast`)

### 3. Tests Not Accepting Maintenance Mode ✅
**Problem:** Tests hardcoded to only expect "auto" or "manual" modes.

**Fix:**
- Updated `test_controllers_status_api.py` to accept "maintenance" in system_mode assertion
- Updated `test_relays_status_api.py` to accept "maintenance" in mode assertion

**Files Modified:**
- `tests/test_controllers_status_api.py`
- `tests/test_relays_status_api.py`

## Verification Tests Performed

### 1. System Mode Propagation Test
```powershell
# Set to AUTO
POST /api/system_mode {"mode":"auto"}
→ All controllers: ph=auto, ec=auto, chiller=auto, lights=auto, circulation=auto ✅

# Set to MANUAL
POST /api/system_mode {"mode":"manual"}
→ All controllers: ph=manual, ec=manual, chiller=manual, lights=manual, circulation=manual ✅

# Set to MAINTENANCE
POST /api/system_mode {"mode":"maintenance"}
→ All controllers: ph=maintenance, ec=maintenance, chiller=maintenance, lights=maintenance, circulation=maintenance ✅
```

### 2. Individual Controller Override Test
```powershell
# System mode: maintenance
# Set pH to manual
POST /api/controller/ph/mode {"mode":"manual"}
→ pH: manual, Others: maintenance ✅
```

### 3. Consolidated Status API Test
```powershell
GET /api/controllers/status
→ Returns system_mode, all controller modes, estop, maintenance_override ✅
```

### 4. Full Test Suite
```bash
pytest -q
→ 154 passed in 21.19s ✅
```

## Controller Mode Functions Verified

All UI mode setter functions are properly implemented and call the correct API endpoints:

- ✅ `window.systemSetMode` → `/api/system_mode`
- ✅ `window.scheduleSetMode` → `/api/controller/lights/mode` (schedule is lights controller)
- ✅ `window.envSetMode` → `/api/controller/chiller/mode`
- ✅ `window.lightsSetMode` → `/api/controller/lights/mode`
- ✅ `window.circSetMode` → `/api/controller/circulation/mode`
- ✅ `window.sensorsSetMode` → `/api/sensors/mode`

## Architecture Notes

### Mode Hierarchy
1. **System Mode** (top-level): `auto`, `manual`, `maintenance`
   - Propagates to all controllers when changed
   - Stored in `settings.system_mode`

2. **Controller Modes** (individual): `auto`, `manual`, `maintenance`
   - Can be overridden individually
   - Stored in `settings.controller.{name}.mode`
   - Controllers: `ph`, `ec`, `chiller`, `lights`, `circulation`

### Mode Propagation Flow
```
User clicks system mode button (auto/manual/maintenance)
  ↓
UI calls /api/system_mode
  ↓
Backend: set_system_mode(mode, propagate_to_controllers=True)
  ↓
1. Updates settings.system_mode
2. Iterates over CONTROLLERS
3. Calls controller_modes.set_mode(controller, mode) for each
  ↓
All controllers now match system mode
  ↓
UI refreshes via /api/controllers/status (consolidated endpoint)
```

### Individual Controller Override
```
User clicks controller-specific mode button (e.g., pH manual)
  ↓
UI calls /api/controller/ph/mode
  ↓
Backend: set_mode('ph', 'manual')
  ↓
Only pH controller changes; others remain at system mode
```

## Testing Commands

### Quick Manual Test
```powershell
# Start server
& .\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080

# Test mode propagation
$base = "http://127.0.0.1:8080"
Invoke-RestMethod "$base/api/system_mode" -Method POST -Body '{"mode":"auto"}' -ContentType 'application/json'
Invoke-RestMethod "$base/api/controllers/status" | ConvertTo-Json -Depth 6
```

### Run Full Test Suite
```powershell
& .\venv\Scripts\python.exe -m pytest -q
```

## UI Verification Checklist

- ✅ Overview page: System mode buttons (Auto/Manual/Maintenance) work and highlight correctly
- ✅ Overview page: Controller health chips update within 2-3 seconds
- ✅ pH tab: Mode buttons work; auto/manual/maintenance modes selectable
- ✅ EC tab: Mode buttons work; auto/manual/maintenance modes selectable
- ✅ Chiller tab: Mode buttons work (envSetMode); auto/manual/maintenance modes selectable
- ✅ Lights tab: Mode buttons work; auto/manual/maintenance modes selectable
- ✅ Circulation tab: Mode buttons work; auto/manual/maintenance modes selectable
- ✅ Consolidated status endpoint returns correct modes for all controllers
- ✅ Individual controller overrides work (e.g., pH manual while system is auto)

## Next Steps

1. ✅ **COMPLETED** - Test on local development server
2. **TODO** - Deploy to Raspberry Pi and verify on hardware
3. **TODO** - Manual UI walkthrough on Pi to verify all buttons work
4. **TODO** - Update PR #63 with these fixes
5. **TODO** - Consider adding system mode history/audit log

## Deployment to Pi

```powershell
# From Windows to Pi
.\deploy\deploy_controllers.ps1 -Host <pi-hostname-or-ip>

# Or manually via SSH
ssh pi@<hostname>
cd ~/RDWC-v4
git pull origin copilot/xenial-lizard
sudo systemctl restart rdwc
```

---

**Status:** All controller mode synchronization issues resolved. System mode now properly propagates to all controllers. Individual controller overrides work as expected. All 154 tests passing.
