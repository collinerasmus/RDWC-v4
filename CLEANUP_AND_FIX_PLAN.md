# MASTER CLEANUP AND FIX PLAN
**Date:** 2024-11-24  
**Priority:** CRITICAL - Multiple Systems Causing Chaos

## DIAGNOSIS: Multiple Duplicate Systems

### 1. STATUS INDICATOR - 3 COMPETING SYSTEMS ❌

**Systems Found:**
- `global_health.js` (line 106-149) - 6s polling loop
- `overview.js` - Status updates
- Camera inline code - Status pill updates

**Problem:** All three update status independently, race conditions
**Solution:** KEEP ONLY global_health.js, remove others

### 2. CAMERA MANAGEMENT - MULTIPLE MANAGERS ❌

**Systems Found:**
- Inline camera init (HTML line 2689-2852) - 170 lines!
- Camera watchdog - 3s polling
- Camera resize handlers - 4 different listeners
- overview.js also managing camera

**Problem:** Camera connects/disconnects causing flicker
**Solution:** Move ALL camera code to dedicated camera.js

### 3. INITIALIZATION - 25 DOMContentLoaded LISTENERS ❌

**Files with DOMContentLoaded:**
```
bop.js, chiller.js, circulation.js, controller_settings.js,
ec_chart.js, ec.js, error_reporter.js, global_health.js,
lights_v2.js, overview.js, ph_chart.js, ph.js, progress.js,
relays_v2.js, relays.js, schedule.js, sensors_calib.js,
sensors.js, settings.js, system.js, tabs.js, trends.js
+ 3 inline scripts in HTML
```

**Problem:** 25 systems all initializing simultaneously, race conditions
**Solution:** Create init_manager.js - single init orchestrator

### 4. POLLING LOOPS - 27 setInterval CALLS ❌

**Active Pollers:**
- global_health.js: 6s
- overview.js: 6s  
- ph.js: 6s
- ec.js: 6s
- chiller.js: 6s
- sensors.js: 6s
- circulation.js: 6s
- lights_v2.js: 6s
- relays_v2.js: 6s
- system.js: 5s
- schedule.js: 6s
- trends.js: auto-refresh
- Camera watchdog: 3s
- Progress monitor: varies
- ... + 13 more setTimeout loops

**Problem:** 27 uncoordinated polling loops, browser overload
**Solution:** Create polling_manager.js - single coordinated loop

### 5. FETCH CALLS - 179 FETCH REQUESTS ❌

**Problem:** No coordination, same endpoints hit multiple times simultaneously
**Solution:** Request deduplication in polling_manager

### 6. JAVASCRIPT FILES - 24 FILES ❌

**Current:**
```
bop.js (11KB), chiller.js (13KB), circulation.js (4KB),
controller_settings.js (16KB), ec_chart.js (15KB), ec.js (38KB),
error_reporter.js (4KB), global_health.js (8KB), lights_control.js (3KB),
lights_v2.js (6KB), overview.js (26KB), ph_chart.js (13KB),
ph.js (41KB), progress.js (6KB), range.js (3KB),
relays_v2.js (25KB), relays.js (5KB), schedule.js (23KB),
sensors_calib.js (7KB), sensors.js (25KB), settings.js (13KB),
system.js (6KB), tabs.js (2KB), trends.js (24KB)
TOTAL: ~350KB of JS
```

**Duplicates Found:**
- relays.js + relays_v2.js (old + new)
- lights_control.js + lights_v2.js (old + new)
- Multiple chart files doing similar things

**Solution:** Delete old files, consolidate

### 7. INLINE SCRIPTS IN HTML - 10 SCRIPTS ❌

**Problem:** 10 inline scripts (2,500+ lines) in HTML
**Solution:** Extract ALL to proper JS files

---

## CLEANUP SEQUENCE

### Phase 1: STOP THE BLEEDING (15 minutes)

**Action 1:** Delete old duplicate files
```
DELETE: app/static/js/relays.js (old version)
DELETE: app/static/js/lights_control.js (old version)
```

**Action 2:** Create polling_manager.js (single loop)
```javascript
// ONE coordinated 6-second loop for ALL updates
// Deduplicates fetch requests
// Manages update priorities
```

**Action 3:** Update all JS files to use polling_manager
```javascript
// Instead of: setInterval(refresh, 6000);
// Use: window.pollingManager.register('ph', refresh, 6000);
```

### Phase 2: CONSOLIDATE STATUS (30 minutes)

**Action 1:** Keep global_health.js as ONLY status manager
**Action 2:** Remove status code from overview.js
**Action 3:** Remove status code from camera inline
**Action 4:** Remove status code from all other files

### Phase 3: FIX CAMERA (30 minutes)

**Action 1:** Extract ALL camera code to camera.js
**Action 2:** Remove inline camera code (170 lines)
**Action 3:** Single camera manager, no duplicates
**Action 4:** Use polling_manager for camera health

### Phase 4: FIX INITIALIZATION (30 minutes)

**Action 1:** Create init_manager.js
```javascript
// Single DOMContentLoaded
// Orchestrates load order:
// 1. Core (tabs, error reporter)
// 2. Health polling
// 3. Controllers (in dependency order)
// 4. Charts (lazy load)
```

**Action 2:** Remove DOMContentLoaded from all 22 JS files
**Action 3:** Each file exports init() function
**Action 4:** init_manager calls them in order

### Phase 5: EXTRACT INLINE SCRIPTS (1 hour)

**Action:** Move all 10 inline scripts to proper files:
- Header mode buttons → mode_control.js
- Camera code → camera.js (already done in Phase 3)
- Debug code → debug.js
- System info → system_info.js
- Version ping → version_check.js

### Phase 6: CLEANUP & TEST (1 hour)

**Action 1:** Remove all console.log (except errors)
**Action 2:** Minify JS files
**Action 3:** Add cache busting to all includes
**Action 4:** Test on HMI

---

## SUCCESS CRITERIA

✅ **Status indicator stable** - No flickering, stays "LIVE"  
✅ **Camera stable** - No disconnect/reconnect cycles  
✅ **Browser stable** - No reloading, stays online  
✅ **One polling loop** - 6s coordinated updates  
✅ **One init system** - Predictable load order  
✅ **All buttons work** - Mode, Hold, GPIO  

---

## FILES TO CREATE

1. `app/static/js/polling_manager.js` - NEW (Core system)
2. `app/static/js/init_manager.js` - NEW (Core system)
3. `app/static/js/camera.js` - NEW (Extract from HTML)
4. `app/static/js/mode_control.js` - NEW (Extract from HTML)
5. `app/static/js/debug.js` - NEW (Extract from HTML)

## FILES TO DELETE

1. `app/static/js/relays.js` - OLD (use relays_v2.js)
2. `app/static/js/lights_control.js` - OLD (use lights_v2.js)

## FILES TO UPDATE (All 22 remaining JS files)

- Remove setInterval, use polling_manager
- Remove DOMContentLoaded, export init()
- Remove status updates, use global_health.js
- Add proper error handling

---

## ESTIMATED TIME

- Phase 1 (Stop bleeding): 15 min ⚡ **START HERE**
- Phase 2 (Status): 30 min
- Phase 3 (Camera): 30 min
- Phase 4 (Init): 30 min
- Phase 5 (Inline): 1 hour
- Phase 6 (Test): 1 hour

**TOTAL: 3.5 hours** for complete cleanup

---

## IMMEDIATE NEXT STEPS

1. Delete old relay/lights files (2 min)
2. Create polling_manager.js (15 min)
3. Update global_health.js to use it (5 min)
4. Deploy & test status stability (5 min)
5. If stable, continue with camera fix
6. If still issues, debug polling_manager

**User:** We start Phase 1 now. Clear browser cache after deploy to test.
