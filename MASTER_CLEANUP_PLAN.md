# RDWC-v4 MASTER CLEANUP PLAN

## Status: Phase 1 COMPLETE ✅

---

## Problem Summary

You had the "too many chefs in the kitchen" syndrome - multiple AI assistants created duplicate systems that fought each other:

1. **4 Mode Systems** competing for control
2. **Multiple Polling Systems** causing browser instability
3. **Duplicate Documentation** creating confusion
4. **Relay Buttons** not wired up properly
5. **No Cache Busting** causing stale code to run

---

## Phase 1: MODE SYSTEM UNIFICATION ✅ COMPLETE

### What Was Done:
- ✅ Created comprehensive `unified_mode.py` as single source of truth
- ✅ Updated ALL Python files to import from `unified_mode`
- ✅ Added backward compatibility for legacy code
- ✅ Fixed controller mode checks in pH/EC
- ✅ Mapped "manual"→"hold" for legacy code compatibility

### Files Modified:
```
app/unified_mode.py          - THE ONLY mode system
app/main.py                  - All imports updated
app/ph_control.py            - Uses unified_mode
app/ec_control.py            - Uses unified_mode
app/chiller_control.py       - Uses unified_mode
app/relays_core.py           - Uses unified_mode
app/scheduler.py             - Uses unified_mode
app/sensor_poller.py         - Uses unified_mode
app/sensors_core.py          - Uses unified_mode
```

### To Remove After Testing:
```
app/controller_modes.py      - OBSOLETE
app/system_mode.py           - OBSOLETE
app/sensors_mode.py          - OBSOLETE
```

### Deploy Instructions:
**See: `URGENT_RUN_THIS_FIRST.md`**

---

## Phase 2: BROWSER STABILITY (Next)

### Problem:
Browser cycles through states: Initializing → Live → Ready → Live
Camera drops in/out

### Root Cause:
Multiple polling systems running:
- `polling_manager.js` (coordinated)
- Legacy `setInterval()` loops in individual JS files
- Overlapping fetch requests

### Solution:
1. Audit all JS files for `setInterval()`
2. Remove legacy polling loops
3. Ensure ONLY `polling_manager.js` runs intervals
4. Add proper WebSocket reconnection backoff
5. Fix SSE endpoint state machine

### Files to Fix:
```
app/static/js/ph.js
app/static/js/ec.js
app/static/js/chiller.js
app/static/js/circulation.js
app/static/js/lights_v2.js
app/static/js/sensors.js
app/static/js/overview.js
```

---

## Phase 3: RELAY BUTTONS (Next)

### Problem:
GPIO relay buttons in System tab don't work

### Root Cause:
- Button handlers not wired up
- Missing event listeners
- No POST requests to `/api/relays/{name}/set`

### Solution:
1. Add button event listeners in `system.js`
2. Wire buttons to relay endpoints
3. Handle response and update UI
4. Test in all modes

### Files to Fix:
```
app/static/js/system.js      - Add button handlers
app/static/index.html        - Verify button IDs
```

---

## Phase 4: CACHE BUSTING

### Problem:
Browser serves stale JS even after updates
Hard refresh doesn't load new code

### Root Cause:
- JS files have no version query parameters
- CSS has `?v=10` but JS missing
- No build commit in file URLs

### Solution:
1. Add `?v=${BUILD_COMMIT}` to all JS imports in HTML
2. Generate BUILD_COMMIT from git hash
3. Update on every deployment
4. Add proper cache headers

### Files to Fix:
```
app/static/index.html        - Add cache busters to <script> tags
deploy_pi.sh                 - Generate build version
```

---

## Phase 5: DOCUMENTATION CLEANUP

### Problem:
30+ markdown files with conflicting/duplicate info

### Docs to Keep (Updated):
```
README.md                    - Main entry point
START_HERE.md               - Quick start guide
SYSTEM_ARCHITECTURE.md      - Technical overview
QUICK_REFERENCE.md          - API endpoints
CONTRIBUTING.md             - Development guide
```

### Docs to Archive:
```
CLEANUP_AND_FIX_PLAN.md      - Superseded by this
SYSTEM_AUDIT_FINDINGS.md     - Superseded by CRITICAL_FINDINGS
URGENT_FIX_CHECKLIST.md      - Completed
COMMISSIONING_*.md           - Multiple versions (consolidate)
MODE_*.md                    - Mode issues fixed
```

### Create New:
```
COMMISSIONING_GUIDE.md       - Single source of truth for commissioning
TROUBLESHOOTING.md           - Common issues and fixes
```

---

## Phase 6: FINAL VALIDATION

### Checklist:
- [ ] Mode changes propagate to all controllers
- [ ] Browser connection is stable
- [ ] Camera feed doesn't drop
- [ ] Relay buttons work in System tab
- [ ] Hard refresh loads new code
- [ ] pH controller responds to mode
- [ ] EC controller responds to mode
- [ ] Dosing pumps calibrate correctly
- [ ] Schedule runs correctly
- [ ] E-STOP works as expected

---

## Current Status

### ✅ COMPLETED:
- Phase 1: Mode System Unification

### 🚀 READY TO DEPLOY:
- Follow instructions in `URGENT_RUN_THIS_FIRST.md`
- Test on Pi
- Verify mode propagation
- Remove old files after confirmation

### 📋 TODO NEXT:
- Phase 2: Browser Stability
- Phase 3: Relay Buttons  
- Phase 4: Cache Busting
- Phase 5: Documentation Cleanup

---

## How to Proceed

1. **NOW**: Deploy Phase 1 (Mode System) to Pi
2. **Test**: Verify mode changes work
3. **Confirm**: Tell me "Phase 1 working" or describe any issues
4. **Then**: I'll help with Phase 2 (Browser Stability)

---

**One system. One mode source. One truth.**
