# RDWC-v4 System Cleanup and Fix Plan
**Date:** 2025-11-24
**Operator:** Single AI taking over full project coordination
**Goal:** Get commissioning working ASAP with stable UI

## Current Issues Identified

### 1. Mode Switching Not Working Properly
**Symptoms:**
- User clicks "Manual" button in header
- Button changes to show manual status
- System doesn't actually go into manual mode
- UI seems to go offline shortly after

**Root Cause Analysis:**
- **Dual mode systems causing confusion:**
  - `system_mode.py`: Uses `auto/manual/maintenance`
  - `controller_modes.py`: Uses `auto/hold` with legacy mapping
  - Legacy mapping: `manual→hold`, `maintenance→hold`
- **Race condition:** UI polls every 3s for system mode while also trying to set it
- **Propagation issue:** Mode must propagate from system→controllers→sensors

### 2. UI Instability (Goes Offline)
**Symptoms:**
- UI reloads multiple times on initial load
- UI goes offline after a few minutes
- Makes commissioning difficult

**Root Cause Analysis:**
- **Polling overload:** Too many concurrent intervals:
  - Relays: 1000ms (1 second)
  - E-stop: 2000ms
  - System mode: 3000ms
  - Sensors: 5000ms
  - Chiller: 5000ms
  - Global health: 10000ms
  - pH/EC: Variable
- **Backend stress:** All these requests hitting backend simultaneously
- **Error cascades:** One failed request triggers UI reload
- **Missing error recovery:** No graceful degradation when backend slow

### 3. Documentation Overload
**Current state:**
- 10+ commissioning-related documents
- 4+ mode synchronization issue/fix documents
- Shows history of "too many chefs in the kitchen"
- Hard to find current status

## Fix Plan

### Phase 1: Fix Mode Switching (CRITICAL)
**Priority: IMMEDIATE**

1. **Verify mode propagation chain:**
   - [ ] Test `POST /api/system_mode` endpoint directly
   - [ ] Confirm it calls `system_mode.set_system_mode(mode, propagate_to_controllers=True)`
   - [ ] Verify propagation to all 5 controllers (ph, ec, lights, chiller, circulation)
   - [ ] Verify propagation to sensors via `sensors_mode.set_sensor_mode()`

2. **Fix legacy mode mapping:**
   - [ ] Ensure `controller_modes.py` properly maps `manual→auto` (not hold)
   - [ ] Update `LEGACY_MODE_MAP` if needed
   - [ ] Test that UI "manual" button results in controller mode "auto" (system paused)

3. **Add error handling:**
   - [ ] Return clear error messages when mode change fails
   - [ ] Log all mode changes with full stack trace on error
   - [ ] Add validation at API boundary

4. **Reduce race conditions:**
   - [ ] Add 500ms debounce to mode button clicks
   - [ ] Don't poll system mode for 5 seconds after setting it
   - [ ] Use optimistic UI updates

### Phase 2: Fix UI Stability (CRITICAL)
**Priority: IMMEDIATE**

1. **Reduce polling frequency:**
   - [ ] Relays: 1000ms → 3000ms (3 seconds)
   - [ ] E-stop: 2000ms → 5000ms (5 seconds)
   - [ ] System mode: 3000ms → 5000ms (5 seconds)
   - [ ] Sensors: 5000ms → 10000ms (10 seconds)
   - [ ] Keep dosing/calibration at current rates (user-visible)

2. **Add error recovery:**
   - [ ] Wrap all fetch calls in try-catch
   - [ ] On error: log, show toast, continue (don't crash)
   - [ ] Implement exponential backoff on repeated failures
   - [ ] Add circuit breaker pattern for dead endpoints

3. **Optimize requests:**
   - [ ] Use consolidated endpoints where possible (`/api/controllers/status`)
   - [ ] Add HTTP caching headers for static data
   - [ ] Batch related requests
   - [ ] Add request deduplication

4. **Add heartbeat monitoring:**
   - [ ] Backend sends version/timestamp in responses
   - [ ] UI tracks last successful response time
   - [ ] Show "reconnecting..." banner if >30s without response
   - [ ] Don't reload page automatically

### Phase 3: Documentation Cleanup (HIGH)
**Priority: HIGH**

1. **Consolidate commissioning docs:**
   - [ ] Create master `COMMISSIONING_GUIDE.md`
   - [ ] Archive old docs to `docs/archive/commissioning/`
   - [ ] Keep only current checklist and guide

2. **Consolidate mode docs:**
   - [ ] Create master `SYSTEM_MODES.md` explaining architecture
   - [ ] Archive mode issue/fix docs to `docs/archive/mode_fixes/`
   - [ ] Document current state clearly

3. **Create single source of truth:**
   - [ ] `CURRENT_STATUS.md` - what works, what doesn't, what's next
   - [ ] Update `README.md` with current getting started guide
   - [ ] Remove conflicting info from old docs

4. **Clean up temporary files:**
   - [ ] Remove old commissioning reports (keep last 3)
   - [ ] Remove any `.tmp`, `.bak` files
   - [ ] Clean up `__pycache__` directories

### Phase 4: Testing & Validation (HIGH)
**Priority: HIGH**

1. **Mode switching test:**
   ```bash
   # Test auto→manual→auto cycle
   curl -X POST http://localhost:8080/api/system_mode -d '{"mode":"manual"}' -H "Content-Type: application/json"
   curl http://localhost:8080/api/controllers/status | jq '.system_mode, .controllers'
   
   curl -X POST http://localhost:8080/api/system_mode -d '{"mode":"auto"}' -H "Content-Type: application/json"
   curl http://localhost:8080/api/controllers/status | jq '.system_mode, .controllers'
   ```

2. **UI stability test:**
   - [ ] Open UI in browser
   - [ ] Monitor network tab for 10 minutes
   - [ ] Count failed requests
   - [ ] Verify no page reloads
   - [ ] Switch modes 10 times - should work every time

3. **Commissioning workflow test:**
   - [ ] Start with system in manual
   - [ ] Verify mode buttons work
   - [ ] Calibrate dosing pumps
   - [ ] Prime pumps
   - [ ] Switch to auto
   - [ ] Verify automation starts

### Phase 5: Code Quality (MEDIUM)
**Priority: MEDIUM - After commissioning works**

1. **Remove dead code:**
   - [ ] Find unused imports
   - [ ] Remove commented-out code blocks
   - [ ] Remove unused functions

2. **Add type hints:**
   - [ ] Add return types to all public functions
   - [ ] Add parameter types
   - [ ] Run mypy validation

3. **Improve logging:**
   - [ ] Consistent log levels
   - [ ] Add request IDs for tracing
   - [ ] Log mode changes at INFO level

## Implementation Order

1. **RIGHT NOW:** Fix mode switching
   - Verify propagation works
   - Fix any broken paths
   - Test with curl

2. **NEXT:** Reduce UI polling
   - Update all `setInterval` calls
   - Test UI stability for 10 minutes

3. **THEN:** Clean up documentation
   - Create master docs
   - Archive old docs
   - Update README

4. **FINALLY:** Validate commissioning workflow
   - Run through full commissioning
   - Document any issues
   - Fix and retest

## Success Criteria

- [ ] Mode button clicks work 100% of time
- [ ] UI stays online for 1+ hour without issues
- [ ] Can complete full commissioning without workarounds
- [ ] Documentation is clear and current
- [ ] Tests pass
- [ ] System ready for handover to auto control

## Notes

- Keep all changes minimal and surgical
- Test each change immediately
- Don't try to "improve" working code
- Focus on fixing broken functionality first
- Document all changes in git commits
