# Mode System Refactoring Status

## Objective
Replace fragmented mode systems (unified_mode.py + per-controller auto_enabled + hold states) with clean single source of truth: global + per-controller auto-enable flags.

## Architecture

### OLD (Fragmented):
1. **unified_mode.py**: MODE_AUTO/MODE_MANUAL/MODE_MAINTENANCE (system-wide)
2. **Per-controller settings**: ph.auto_enabled, ec.auto_enabled, chiller.auto_enabled
3. **Hold states**: controller.{name}.held (pause mechanism)

### NEW (Clean):
```python
# app/auto_control.py - Single Source of Truth

controls.global_auto = true/false     # Master switch
controls.ph_auto = true/false         # pH-specific
controls.ec_auto = true/false         # EC-specific
controls.chiller_auto = true/false    # Chiller-specific

should_automate("ph") = global_auto AND ph_auto
```

## Backend Changes

### ✅ COMPLETED

1. **Created auto_control.py** (app/auto_control.py)
   - `is_global_auto_enabled()` / `set_global_auto_enabled(enabled)`
   - `is_controller_auto_enabled(controller)` / `set_controller_auto_enabled(controller, enabled)`
   - `should_automate(controller)` - Returns True only if global AND controller both enabled
   - `get_auto_status()` - Returns complete state
   - `migrate_from_legacy()` - Ports old settings (unified_mode, ph.auto_enabled, etc.)
   - `initialize_db()` - Sets safe defaults (all false)

2. **Updated main.py endpoints** (app/main.py)
   - `GET /api/auto/status` - Get global + per-controller auto status
   - `POST /api/auto/global` - Set global automation master switch
     ```json
     {"enabled": true}
     ```
   - `POST /api/auto/{controller}` - Set controller-specific auto-enable
     ```json
     {"enabled": false}
     ```

3. **Added migration startup hook** (app/main.py)
   - `@app.on_event("startup")` calls `migrate_from_legacy()`
   - One-time migration from old systems

4. **Updated pH controller** (app/ph_control.py line ~380)
   - Replaced `ph.auto_enabled` check with `should_automate("ph")`
   - Changed holding_reason="held" to holding_reason="auto_disabled"

### ⏳ PENDING Backend

1. **Update EC controller** (app/ec_control.py)
   - Replace `ec.auto_enabled` checks with `should_automate("ec")`
   - Update status endpoint to return auto state

2. **Update chiller controller** (app/chiller_control.py)
   - Replace `chiller.auto_enabled` checks with `should_automate("chiller")`
   - Update status endpoint

3. **Deprecate old mode endpoints** (app/main.py)
   - Keep for backward compatibility but mark deprecated:
     - `/api/controller/modes`
     - `/api/controller/{name}/mode`
     - `/api/controller/{name}/hold`

4. **Remove MODE constants** (optional cleanup)
   - unified_mode.py MODE_AUTO/MANUAL/MAINTENANCE
   - After confirming no dependencies

## Frontend Changes

### ⏳ PENDING Frontend

1. **Replace header mode buttons** (app/static/index.html lines 676-679)
   
   **OLD**:
   ```html
   <button id="system-mode-auto">Auto</button>
   <button id="system-mode-manual">Manual</button>
   <button id="system-mode-maint">Maintenance</button>
   ```
   
   **NEW**:
   ```html
   <button id="global-auto-btn" class="btn-chip" title="Global Auto Enable">
     🌐 Auto: <span id="global-auto-state">OFF</span>
   </button>
   ```

2. **Add per-controller auto toggles to each tab**
   
   **pH Tab** (after KPIs, before pump controls):
   ```html
   <div class="control-section">
     <h3>Automation</h3>
     <button id="ph-auto-btn" class="btn-secondary">
       pH Auto: <span id="ph-auto-state">OFF</span>
     </button>
   </div>
   ```
   
   **EC Tab**:
   ```html
   <button id="ec-auto-btn" class="btn-secondary">
     EC Auto: <span id="ec-auto-state">OFF</span>
   </button>
   ```
   
   **Chiller Tab** (if exists):
   ```html
   <button id="chiller-auto-btn" class="btn-secondary">
     Chiller Auto: <span id="chiller-auto-state">OFF</span>
   </button>
   ```

3. **Create new auto status polling** (app/static/js/system.js or inline)
   
   ```javascript
   // Poll /api/auto/status every 2s
   function updateAutoStatus() {
     fetch('/api/auto/status')
       .then(r => r.json())
       .then(data => {
         // Update global button
         const globalBtn = document.getElementById('global-auto-btn');
         const globalState = document.getElementById('global-auto-state');
         if (globalBtn && globalState) {
           globalState.textContent = data.global_auto ? 'ON' : 'OFF';
           globalBtn.classList.toggle('active', data.global_auto);
         }
         
         // Update per-controller buttons
         ['ph', 'ec', 'chiller'].forEach(ctrl => {
           const btn = document.getElementById(`${ctrl}-auto-btn`);
           const state = document.getElementById(`${ctrl}-auto-state`);
           if (btn && state) {
             const enabled = data.controllers[ctrl];
             state.textContent = enabled ? 'ON' : 'OFF';
             btn.classList.toggle('active', enabled);
           }
         });
       });
   }
   
   // Toggle global auto
   document.getElementById('global-auto-btn').addEventListener('click', () => {
     fetch('/api/auto/status').then(r => r.json()).then(data => {
       const newState = !data.global_auto;
       fetch('/api/auto/global', {
         method: 'POST',
         headers: {'Content-Type': 'application/json'},
         body: JSON.stringify({enabled: newState})
       }).then(() => updateAutoStatus());
     });
   });
   
   // Toggle controller auto (example for pH)
   document.getElementById('ph-auto-btn').addEventListener('click', () => {
     fetch('/api/auto/status').then(r => r.json()).then(data => {
       const newState = !data.controllers.ph;
       fetch('/api/auto/ph', {
         method: 'POST',
         headers: {'Content-Type': 'application/json'},
         body: JSON.stringify({enabled: newState})
       }).then(() => updateAutoStatus());
     });
   });
   ```

4. **Remove old mode UI logic**
   - system.js systemSetMode() function
   - Mode banner content divs (system-auto-content, etc.)
   - Mode sync logic in header initialization

## Testing Checklist

### Backend Tests
- [ ] `/api/auto/status` returns correct structure
- [ ] `/api/auto/global` POST toggles global_auto
- [ ] `/api/auto/ph` POST toggles ph_auto
- [ ] `should_automate("ph")` returns false when global_auto=false
- [ ] `should_automate("ph")` returns false when ph_auto=false
- [ ] `should_automate("ph")` returns true when both enabled
- [ ] Migration successfully ports ph.auto_enabled → ph_auto
- [ ] pH controller respects new auto state
- [ ] pH status endpoint shows auto_disabled when disabled

### Frontend Tests
- [ ] Global auto button shows ON/OFF state
- [ ] Global auto button toggles on click
- [ ] pH auto button shows ON/OFF state
- [ ] pH auto button toggles on click
- [ ] pH auto disabled when global auto OFF (visual indication)
- [ ] Dosing buttons still work when auto disabled (manual mode)
- [ ] Guards still enforced in manual mode
- [ ] Status KPI shows "Auto: Disabled" when off

### Integration Tests
- [ ] Restart service → settings preserved
- [ ] Set global OFF → all controllers stop
- [ ] Set global ON + pH ON → pH automates
- [ ] Set global ON + pH OFF → pH doesn't automate
- [ ] EC and chiller independent control

## Deployment Steps

1. **Deploy backend changes**:
   ```powershell
   cd C:\Users\USER-PC\OneDrive\Documents\GitHub\RDWC-v4
   git add app/auto_control.py app/main.py app/ph_control.py
   git commit -m "feat: unified auto-enable system (backend)"
   git push
   
   # SSH to Pi
   ssh pi@rdwc.local
   cd ~/rdwc
   git pull
   sudo systemctl restart rdwc-api
   ```

2. **Test backend endpoints**:
   ```powershell
   # Check status
   curl http://rdwc.local:8080/api/auto/status
   
   # Toggle global
   curl -X POST http://rdwc.local:8080/api/auto/global `
     -H "Content-Type: application/json" `
     -d '{"enabled": true}'
   
   # Toggle pH
   curl -X POST http://rdwc.local:8080/api/auto/ph `
     -H "Content-Type: application/json" `
     -d '{"enabled": true}'
   ```

3. **Deploy frontend changes** (after creating):
   ```powershell
   git add app/static/index.html app/static/js/*.js
   git commit -m "feat: unified auto-enable system (frontend)"
   git push
   
   # No restart needed - static files served directly
   # Force refresh browser: Ctrl+Shift+R
   ```

## Migration Notes

**Existing settings will be automatically ported on first startup**:

```python
# app/auto_control.py migrate_from_legacy()

# unified_mode = auto → global_auto = true
# unified_mode = manual → global_auto = false
# unified_mode = maintenance → global_auto = false

# ph.auto_enabled = true → ph_auto = true
# ec.auto_enabled = true → ec_auto = true
# chiller.auto_enabled = true → chiller_auto = true

# controller.ph.held = true → ph_auto = false
# controller.ec.held = true → ec_auto = false
```

**Safe defaults**: All flags default to `false` for safety. User must explicitly enable automation after migration.

## User Benefits

1. **Clarity**: No more confusion between AUTO/MANUAL/MAINTENANCE modes
2. **Control**: Global master switch + individual controller control
3. **Simplicity**: "Auto enabled/disabled" instead of mode + hold + auto_enabled
4. **Flexibility**: Can disable one controller while others run
5. **Safety**: Defaults to disabled; guards always enforced

## Current State

- Backend: ✅ COMPLETE - All controllers use should_automate()
- Frontend: ✅ COMPLETE - Global auto toggle in header, per-controller status
- Migration: ✅ Ready (will run on next restart)
- Testing: ⏳ Pending - Tests need updating

## Completed Updates

### Backend
- ✅ pH controller: Uses `should_automate("ph")` (app/ph_control.py)
- ✅ EC controller: Uses `should_automate("ec")` (app/ec_control.py)
- ✅ Chiller controller: Uses `should_automate("chiller")` (app/chiller_control.py)
- ✅ Scheduler: Uses `is_global_auto_enabled()` for lights (app/scheduler.py)
- ✅ Sensor poller: Removed mode gating (app/sensor_poller.py)
- ✅ Sensors core: Removed mode override logic (app/sensors_core.py)

### API
- ✅ New endpoints working: `/api/auto/status`, `/api/auto/global`, `/api/auto/{controller}`
- ✅ Old endpoints deprecated: `/api/controller/modes`, `/api/controller/{name}/mode`, `/api/controller/hold/all`
- ✅ `/api/controllers/status` updated to use auto_control.py

### Frontend
- ✅ Global auto toggle button in header
- ✅ system.js uses /api/auto/* endpoints
- ✅ overview.js uses will_automate field for status display

### Settings
- ✅ Old auto_enabled settings marked as deprecated in DEFAULTS
- ✅ unified_mode.py marked as deprecated

## Deprecated Code (Kept for Backward Compatibility)
- app/unified_mode.py - Old mode constants and functions
- settings: ph.auto_enabled, ec.auto_enabled, chiller.auto_enabled
- API: /api/controller/* endpoints

## Next Steps
- Update test files to use new system
- Remove deprecated code after migration period
