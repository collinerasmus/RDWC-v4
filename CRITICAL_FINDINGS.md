# CRITICAL SYSTEM ISSUES FOUND

## Date: 2025-11-24
## Status: URGENT - MULTIPLE CONFLICTING SYSTEMS

---

## ROOT CAUSE: FOUR CONFLICTING MODE SYSTEMS

The system has **4 DUPLICATE mode management systems** fighting each other:

### 1. `app/controller_modes.py`
- Modes: "auto", "hold"
- Used by: `ph_control.py`, `ec_control.py` 
- Storage: `controller.{name}.mode` in settings table

### 2. `app/system_mode.py`
- Modes: "auto", "manual", "maintenance"
- Used by: `/api/relays/status`, individual relay controls
- Storage: `system.mode` in settings table

### 3. `app/unified_mode.py` 
- Modes: "auto", "manual", "maintenance"
- Used by: `/api/mode/*` endpoints
- Storage: `system_mode` in settings table  
- **INTENDED to be the single source of truth but NOT ACTUALLY USED**

### 4. `app/sensors_mode.py`
- Separate sensor-only mode system
- Used by: `/api/sensors/mode` endpoint
- Storage: `sensors.mode` in settings table

### Impact:
- UI sets mode via `/api/relays/mode` → uses `system_mode.py`
- pH controller checks mode via `controller_modes.get_mode("ph")` → expects "auto" or "hold"
- When UI switches to "manual", pH controller still sees "auto" and keeps running
- Controllers don't respond to mode changes from UI
- Relay buttons don't work because mode guard logic is inconsistent

---

## ISSUE 2: WebSocket Connection Cycling

The UI shows:
- Initializing → Live → Ready → Live → Ready → Live (cycles)
- Camera drops in/out
- Connection instability

### Suspected Causes:
1. **Multiple polling systems running concurrently**:
   - `polling_manager.js` (coordinated system)
   - Legacy setInterval loops in individual JS files
   - `global_health.js` registering with polling manager
   - Overlapping fetch requests causing backend overload

2. **WebSocket readyState transitions**:
   - FastAPI SSE endpoint cycling
   - No proper reconnection backoff
   - Frontend not handling connection states properly

---

## ISSUE 3: Relay Buttons Not Working in System Tab

The GPIO relay buttons in the System tab don't work regardless of mode.

### Cause:
- `system.js` exists but relay button handlers not properly wired
- No `relays_v2.js` file to handle System tab buttons  
- Button click handlers missing or pointing to wrong endpoints

---

## ISSUE 4: Mode Change Not Propagating to Controllers

When clicking "MANUAL" in header:
1. UI sends POST to `/api/relays/mode` with `{mode: "manual"}`
2. This calls `system_mode.set_system_mode("manual")`
3. pH controller checks `controller_modes.get_mode("ph")`
4. `controller_modes.py` has its own database key: `controller.ph.mode`
5. **Mode change never reaches pH controller**

### Why "Hold" Button Works:
- The "Hold" button directly calls `/api/controllers/ph/mode` with `{mode: "hold"}`
- This writes to `controller.ph.mode` via `controller_modes.set_mode("ph", "hold")`
- pH controller sees mode change and actually pauses

---

## ISSUE 5: Browser Cache and Stale Assets

- Build commit in HTML: `43fa8ee`
- Version meta tag: `20251115ac`
- CSS has `?v=10` cache buster
- JS files have NO cache busters
- Browsers serving stale JS even after updates

---

## SOLUTION: UNIFIED CLEANUP PLAN

### Phase 1: Consolidate Mode System (URGENT)
1. Delete `controller_modes.py`, `system_mode.py`, `sensors_mode.py`
2. Keep ONLY `unified_mode.py` as single source of truth
3. Update ALL imports in:
   - `main.py`
   - `ph_control.py`
   - `ec_control.py`
   - `chiller_control.py`
   - Any other controllers
4. Standardize on modes: "auto", "manual", "maintenance"
5. Migrate existing database settings to unified keys

### Phase 2: Fix UI Polling System
1. Remove ALL legacy setInterval() calls from individual JS files
2. Ensure ONLY `polling_manager.js` runs intervals
3. Add proper WebSocket reconnection backoff
4. Fix SSE endpoint state machine

### Phase 3: Fix Relay Buttons
1. Create proper button handlers in `system.js` or new `relays_v2.js`
2. Wire up GPIO buttons to POST to `/api/relays/{name}/set`
3. Test manual relay control regardless of mode

### Phase 4: Cache Busting
1. Add build commit or timestamp to ALL JS/CSS file references
2. Update HTML to use `?v=${BUILD_COMMIT}` on all assets
3. Add proper cache headers to static file serving

### Phase 5: Documentation Cleanup
1. Archive outdated commissioning docs
2. Create single SOURCE OF TRUTH commissioning guide
3. Remove conflicting/duplicate guides

---

## FILES TO DELETE

```
app/controller_modes.py  # DUPLICATE
app/system_mode.py       # DUPLICATE
app/sensors_mode.py      # DUPLICATE (sensors follow system mode)
```

## FILES TO UPDATE

```
app/unified_mode.py      # Make this THE ONLY mode system
app/main.py              # Update all mode imports
app/ph_control.py        # Use unified_mode
app/ec_control.py        # Use unified_mode
app/chiller_control.py   # Use unified_mode
app/static/index.html    # Add cache busters to JS
app/static/js/*.js       # Remove legacy polling loops
```

---

## VERIFICATION CHECKLIST

After fixes:
- [ ] Only ONE Python file handles mode (unified_mode.py)
- [ ] All controllers check the SAME mode source
- [ ] UI mode buttons actually change controller behavior
- [ ] Relay buttons work in System tab
- [ ] Browser doesn't cycle through connection states
- [ ] Hard refresh (Ctrl+Shift+R) actually loads new code
- [ ] Camera feed is stable
- [ ] No more "too many chefs" syndrome

---

## PRIORITY: CRITICAL
## ESTIMATED FIX TIME: 2-4 hours
## RISK: Medium (requires coordinated changes across many files)
## IMPACT: HIGH - System currently non-functional for commissioning
