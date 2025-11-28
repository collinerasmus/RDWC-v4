# URGENT: Deep Scan Required - Auto-Enable System Issues

## Problem Summary

The unified auto-enable system on branch `copilot/review-auto-enable-system` (commit 91c1e94) has critical issues:

1. **POST endpoints timeout/hang** - All POST requests to `/api/auto/*` endpoints timeout after 3+ seconds
2. **Old mode system still present** - UI still shows old mode selection buttons
3. **Possible incomplete refactoring** - System may still have old mode logic active

## Current Deployment State

**Branch**: `copilot/review-auto-enable-system`  
**Commit**: `91c1e94` - "fix: resolve POST endpoint timeout by removing unnecessary commits"  
**Service**: Running on Pi (192.168.88.49:8080)  
**Status**: GET endpoints work, POST endpoints hang

## Critical Issues Found

### Issue 1: POST Endpoints Execute But Didn't Send Response (RESOLVED)

**Original Discovery**: POST endpoints executed successfully (database changes confirmed) but HTTP responses were never sent back to the client, causing timeouts.

**Root Cause (Confirmed)**: `RequestAuditMiddleware` (lines 265–307 in updated `app/main.py`, commit `92b1cb4`) was consuming the request body with `await request.body()` and attempting to restore it via `request._body = body_bytes` (private attribute). FastAPI's downstream body parsing then saw an already-consumed stream, leading to stalled response handling. This suppressed POST logging and caused client timeouts despite successful handler execution.

**Fix Implemented**: Commit `92b1cb4` removed body reading entirely from the middleware. Middleware now logs method/path/client only for write methods without touching the body. No manual mutation of `request._body` remains.

**Validated After Fix**:
```bash
curl -X POST http://localhost:8080/api/auto/global -H 'Content-Type: application/json' -d '{"enabled": false}'
# Response (≈84ms): {"ok":true,"global_auto":false,...}
```
Headers show `HTTP/1.1 200 OK`, content-length present, and POST now appears in journald logs.

**Current Commit**: `92b1cb4 fix: remove body reading from RequestAuditMiddleware that blocked POST`

**Residual Actions Needed**:
1. Add regression test to ensure middleware never consumes body (search for `request.body()` in audit middleware).
2. Evaluate whether any other custom middleware reads bodies.
3. Add monitoring counter for POST latency to catch future regressions (>250ms alert).

**Status**: RESOLVED – proceed with database cleanup and UI refactor.

### Issue 2: Old Mode System Still in UI

**User Report**: "there is still old mode selection in the systems on on the ui"

**What this means**:
- The UI (app/static/index.html) still shows old mode buttons
- Users see: Auto/Manual/Maintenance mode buttons in header
- These should have been replaced with:
  - Global auto toggle button
  - Per-controller auto toggle buttons in each tab

**Expected UI State** (from MODE_REFACTOR_STATUS.md):
```html
<!-- SHOULD BE (but isn't): -->
<button id="global-auto-btn">🌐 Auto: <span>OFF</span></button>

<!-- Per-controller in tabs: -->
<button id="ph-auto-btn">pH Auto: <span>OFF</span></button>
<button id="ec-auto-btn">EC Auto: <span>OFF</span></button>
```

**Current UI State** (likely still has):
```html
<!-- OLD (should be removed): -->
<button id="system-mode-auto">Auto</button>
<button id="system-mode-manual">Manual</button>
<button id="system-mode-maint">Maintenance</button>
```

**Files to investigate**:
- `app/static/index.html` lines 670-680 (header mode buttons)
- `app/static/js/system.js` (systemSetMode() function)
- `app/static/js/ph.js` (pH tab controls)
- `app/static/js/ec.js` (EC tab controls)

### Issue 3: Old Mode System IS Still Active (CONFIRMED)

**CONFIRMED**: Database contains BOTH old and new settings systems, causing conflicting state.

**Database Evidence**:
```
chiller.auto_enabled|1                    ← OLD scattered setting
controller.chiller.mode|auto              ← OLD relay mode system  
controls.chiller_auto|true                ← NEW unified setting
controls.global_auto|false                ← NEW global switch
ec.auto_enabled|true                      ← OLD scattered setting
ph.auto_enabled|true                      ← OLD scattered setting
```

**API Status Shows**:
```json
{
  "global_auto": false,
  "controllers": {
    "chiller": {"auto_enabled": true, "will_automate": false}
  }
}
```
(Correctly calculates will_automate=false due to global_auto=false)

**BUT Relay System Reports**:
```json
{"mode": "auto", "estop": false}
```

**Frontend Shows**:
- OLD mode buttons still present (lines 676-679): Auto, Manual, Maintenance
- OLD systemSetMode() function still active
- NO new auto toggle buttons in header

**Problems**:
1. Old relay mode system (`/api/relays/mode`) operational
2. Old scattered settings not migrated/removed
3. Controllers may check BOTH old and new settings
4. UI only shows old controls, not new unified controls
5. Chiller appears "in auto" on frontend but backend shows conflicting state

**Files to verify**:
- `app/unified_mode.py` - Check if MODE_AUTO/MANUAL/MAINTENANCE still used
- `app/scheduler.py` - May check system mode for lights
- `app/relays_core.py` - May check mode before relay operations
- `app/chiller_control.py` - May use old `chiller.auto_enabled` instead of `should_automate("chiller")`
- `app/ph_control.py`, `app/ec_control.py` - May use scattered settings
- All controller files for scattered auto_enabled checks

## Required Deep Scan Tasks

### Task 1: Fix POST Response Transmission Failure

**Priority**: CRITICAL

**Investigate**:
1. Add logging to POST endpoints to prove they execute (logger.info at start/middle/end)
2. Why do POST requests not appear in uvicorn logs?
3. Does `get_auto_status()` call in return statement block response?
4. Test async endpoint version
5. Check FastAPI middleware configuration
6. Investigate uvicorn `timeout-keep-alive=5` canceling response
7. Check if response JSON serialization fails silently
4. Are there any locks/mutexes that only affect writes?
5. Check if uvicorn worker configuration causes issues

**Proposed Fixes**:
1. Add comprehensive endpoint logging
2. Remove `get_auto_status()` from return statement temporarily
3. Convert to async endpoints
4. Increase uvicorn timeout-keep-alive
5. Check middleware stack

**Test After Fix**:
```python
# Add debug logging to app/main.py POST endpoints:
@app.post("/api/auto/global")
def api_auto_global_set(body: dict = Body(...)):
    logger.info(f"[AUTO] POST /api/auto/global START: {body}")
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return {"error": "enabled must be boolean"}, 400
    logger.info(f"[AUTO] Calling set_global_auto_enabled({enabled})")
    ok = set_global_auto_enabled(enabled)
    logger.info(f"[AUTO] set_global_auto_enabled returned: {ok}")
    response = {"ok": ok, "global_auto": enabled}
    logger.info(f"[AUTO] Returning response: {response}")
    return response

# Also add to app/auto_control.py _set_setting():
def _set_setting(key: str, value: str) -> bool:
    logger.info(f"START _set_setting: {key}={value}")
    _ensure_db()
    logger.info("After _ensure_db()")
    try:
        from app.db_pool import get_conn
        logger.info("Imported get_conn")
        conn = get_conn()  # <-- Does it hang here?
        logger.info(f"Got connection: {conn}")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        logger.info("Executed INSERT")
        return True
    except Exception as e:
        logger.error(f"Failed to set {key}: {e}")
        return False
```

### Task 2: Clean Database - Remove Old Settings

**Priority**: HIGH

**Required**: Migrate/remove old scattered settings to prevent conflicting state.

**Old settings to DELETE from database**:
```sql
-- Remove old scattered auto settings
DELETE FROM settings WHERE key = 'ph.auto_enabled';
DELETE FROM settings WHERE key = 'ec.auto_enabled';
DELETE FROM settings WHERE key = 'chiller.auto_enabled';

-- Remove old relay mode system settings
DELETE FROM settings WHERE key LIKE 'controller.%.mode';
DELETE FROM settings WHERE key LIKE 'controller.%.held';

-- Verify only new settings remain
SELECT key, value FROM settings WHERE key LIKE '%auto%' ORDER BY key;
-- Should show ONLY:
-- controls.chiller_auto
-- controls.ec_auto  
-- controls.global_auto
-- controls.ph_auto
```

**Code to check/remove**:
1. Search for `ph.auto_enabled`, `ec.auto_enabled` reads in controllers
2. Remove `get_system_mode()`, `set_system_mode()` functions
3. Remove `is_held()`, `set_hold()` functions if still present
4. Update all controllers to ONLY use `should_automate(controller_name)`

### Task 3: Complete Frontend Refactoring

**Priority**: HIGH

**Required changes in app/static/index.html**:

1. **Remove old mode buttons** (lines ~676-679):
```html
<!-- DELETE THESE: -->
<button id="system-mode-auto" class="btn-chip">Auto</button>
<button id="system-mode-manual" class="btn-chip">Manual</button>
<button id="system-mode-maint" class="btn-chip">Maintenance</button>
```

2. **Add global auto toggle** (header):
```html
<!-- ADD THIS: -->
<button id="global-auto-btn" class="btn-chip" title="Global Auto Enable">
  🌐 Auto: <span id="global-auto-state">...</span>
</button>
```

3. **Add per-controller toggles** (each tab):
```html
<!-- In pH tab (after KPIs): -->
<div class="control-section">
  <h3>Automation</h3>
  <button id="ph-auto-btn" class="btn-secondary">
    pH Auto: <span id="ph-auto-state">...</span>
  </button>
</div>

<!-- In EC tab: -->
<button id="ec-auto-btn" class="btn-secondary">
  EC Auto: <span id="ec-auto-state">...</span>
</button>

<!-- In chiller tab (if exists): -->
<button id="chiller-auto-btn" class="btn-secondary">
  Chiller Auto: <span id="chiller-auto-state">...</span>
</button>
```

4. **Remove old mode sync logic**:
- Delete `systemSetMode()` function
- Delete mode banner divs: `system-auto-content`, `system-manual-content`, `system-maint-content`
- Delete mode sync in header initialization

5. **Add new auto status polling**:
```javascript
// Poll /api/auto/status every 2s
function updateAutoStatus() {
  fetch('/api/auto/status')
    .then(r => r.json())
    .then(data => {
      // Update global button
      document.getElementById('global-auto-state').textContent = 
        data.global_auto ? 'ON' : 'OFF';
      
      // Update per-controller buttons
      ['ph', 'ec', 'chiller'].forEach(ctrl => {
        const el = document.getElementById(`${ctrl}-auto-state`);
        if (el) el.textContent = data.controllers[ctrl].auto_enabled ? 'ON' : 'OFF';
      });
    });
}

setInterval(updateAutoStatus, 2000);

// Toggle handlers
document.getElementById('global-auto-btn').addEventListener('click', () => {
  // NOTE: POST currently hangs - needs fix first!
  fetch('/api/auto/global', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled: !currentGlobalState})
  });
});
```

### Task 3: Verify Backend Refactoring Complete

**Priority**: HIGH

**Check these files for old mode references**:

1. **app/unified_mode.py**:
   - Are MODE_AUTO/MANUAL/MAINTENANCE constants still used anywhere?
   - Is get_system_mode() still called?
   - Should this file be deprecated entirely?

2. **app/scheduler.py**:
   - Does it check system mode for lights control?
   - Should use should_automate("lights") if lights is a controller

3. **app/relays_core.py**:
   - Does it check mode before relay operations?
   - Verify no mode-based guards

4. **app/chiller_control.py**:
   - KNOWN: Not yet updated to use should_automate("chiller")
   - Still uses old chiller.auto_enabled checks
   - Must be updated like pH and EC were

5. **app/settings.py DEFAULTS**:
   - Remove: ph.auto_enabled, ec.auto_enabled, chiller.auto_enabled
   - Keep: controls.global_auto, controls.ph_auto, controls.ec_auto, controls.chiller_auto

### Task 4: Database Connection Pool Issue

**Priority**: CRITICAL

**Investigate app/db_pool.py**:
1. How many connections in the pool?
2. Is there a connection leak in POST handlers?
3. Does get_conn() have proper timeout?
4. Is isolation_level=None applied correctly?
5. Are connections properly returned to pool after POST?

**Check**:
```python
# In app/db_pool.py - verify this pattern:
def get_conn(readonly: bool = False):
    """Get pooled connection (autocommit mode)"""
    conn = _get_from_pool()
    # Ensure autocommit
    conn.isolation_level = None
    return conn
```

**Test directly**:
```bash
# On Pi, test if pool is exhausted:
lsof ~/RDWC-v4/data/rdwc.db | wc -l  # Count open FDs
# If > 20, pool may be exhausted
```

## Investigation Checklist

Run these checks and report findings:

### Backend Checks
- [ ] Search entire codebase for `MODE_AUTO`, `MODE_MANUAL`, `MODE_MAINTENANCE`
- [ ] Search for `get_system_mode()`, `set_system_mode()`
- [ ] Search for `ph.auto_enabled`, `ec.auto_enabled`, `chiller.auto_enabled` (scattered settings)
- [ ] Search for `controller.*.held` (old hold states)
- [ ] Verify all controllers use `should_automate(controller)`
- [ ] Check if chiller_control.py updated
- [ ] Verify settings.py DEFAULTS has new keys only

### Frontend Checks
- [ ] Check app/static/index.html for old mode buttons (system-mode-auto, etc.)
- [ ] Check for systemSetMode() function
- [ ] Check for mode banner divs
- [ ] Verify global auto toggle exists
- [ ] Verify per-controller auto toggles exist in tabs
- [ ] Check if mode sync logic removed

### API Checks
- [ ] Test GET /api/auto/status (should work)
- [ ] Test POST /api/auto/global with curl (currently hangs)
- [ ] Test POST /api/auto/ph with curl (currently hangs)
- [ ] Add debug logging to _set_setting() to find where it blocks
- [ ] Test direct Python call to set_global_auto_enabled() (known to work)
- [ ] Check if other POST endpoints hang (settings import, etc.)

### Database Checks
- [ ] Verify db_pool uses isolation_level=None
- [ ] Check connection pool size and available connections
- [ ] Test direct sqlite3 write (known to work)
- [ ] Check for database locks: `lsof ~/RDWC-v4/data/rdwc.db`
- [ ] Verify no lingering transactions

## Expected Deliverables

1. **Root cause of POST endpoint blocking**
   - Exact line/function where it hangs
   - Why it works for GET but not POST
   - Proposed fix with code changes

2. **Complete frontend update**
   - Remove ALL old mode UI elements
   - Add global + per-controller auto toggles
   - Working click handlers (once POST is fixed)
   - Updated polling to use /api/auto/status

3. **Verified backend refactoring**
   - Confirmation ALL old mode checks removed
   - Chiller controller updated
   - Settings defaults cleaned up
   - Only should_automate() used

4. **Working POST endpoints**
   - Test cases showing successful toggles
   - Response times < 200ms
   - No timeouts or hangs

## Testing Plan (After Fixes)

```bash
# 1. Test GET (should work now)
curl http://localhost:8080/api/auto/status

# 2. Test POST global disable (currently hangs - must fix)
curl -X POST http://localhost:8080/api/auto/global \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# 3. Verify status changed
curl http://localhost:8080/api/auto/status
# Should show: "global_auto": false, "will_automate": false for all

# 4. Test POST pH enable
curl -X POST http://localhost:8080/api/auto/ph \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# 5. Re-enable global
curl -X POST http://localhost:8080/api/auto/global \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# 6. Verify pH now automating
curl http://localhost:8080/api/auto/status
# Should show pH: "will_automate": true
```

## Success Criteria

- ✅ POST /api/auto/* endpoints respond in < 200ms
- ✅ All toggles work without timeout
- ✅ UI shows ONLY new auto toggles (no mode buttons)
- ✅ All controllers use should_automate()
- ✅ No MODE_AUTO/MANUAL/MAINTENANCE in active code
- ✅ Database writes work reliably
- ✅ Connection pool stable

## Current Branch Info

```bash
# Branch: copilot/review-auto-enable-system
# Commits:
91c1e94 fix: resolve POST endpoint timeout by removing unnecessary commits
3606dea fix: address code review feedback for consistent auto status display
5f11087 test: update mode API tests for unified auto-enable system
2d9bbac refactor: update frontend to use unified auto-enable system
147f18e refactor: update backend to use unified auto-enable system
```

**Note**: Commit 2d9bbac claims "refactor: update frontend to use unified auto-enable system" but user reports old mode buttons still present in UI. This commit may not have been fully applied or was incomplete.

## Immediate Actions Required

1. **FIX POST BLOCKING** - This is blocking all testing
2. **VERIFY FRONTEND CHANGES** - Confirm 2d9bbac actually updated UI
3. **COMPLETE REFACTORING** - Find any remaining old mode references
4. **TEST END-TO-END** - Verify entire system works

Start with POST blocking issue - everything else depends on this working.
