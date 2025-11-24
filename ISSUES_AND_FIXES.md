# RDWC-v4 Issues and Fixes
**Date:** 2025-11-24
**Status:** Active Investigation and Fixes

## Issue #1: Mode Switching Button Shows Changed But System Doesn't Respond

### User Report
- Click "Manual" button in page header
- Button visual changes to show "Manual" active
- System doesn't actually go into manual mode
- Controllers don't switch modes
- UI seems to go offline after

### Investigation Results

**Backend Testing:**
```powershell
# Test 1: Auto → Manual
POST /api/system_mode {"mode":"manual"}
Result: ✅ SUCCESS
- system_mode changed to "manual"
- All 5 controllers propagated correctly (ph, ec, chiller, lights, circulation)

# Test 2: Manual → Auto  
POST /api/system_mode {"mode":"auto"}
Result: ✅ SUCCESS
- system_mode changed to "auto"
- All 5 controllers propagated correctly

# Test 3: Consolidated status check
GET /api/controllers/status
Result: ✅ CORRECT
- Returns accurate system_mode
- All controller modes match
```

**Conclusion:** Backend mode switching works perfectly. Issue is NOT in backend.

### Root Cause Analysis

The problem is likely one of these frontend issues:

1. **Race condition:** 
   - User clicks button → `setSystemMode()` called
   - Before POST completes, `refreshSystemMode()` polls (every 3s)
   - Polling might interfere with state update

2. **Error cascade:**
   - One fetch fails → UI enters error state
   - Subsequent polls keep failing
   - User perceives as "offline"
   - No visual feedback of error

3. **Mode string mismatch:**
   - Backend expects: "auto", "manual", "maintenance"
   - Controller_modes uses: "auto", "hold" (with legacy mapping)
   - Some controller tabs might not understand "manual" vs "hold"

4. **Missing UI error recovery:**
   - No exponential backoff on failed requests
   - No circuit breaker
   - No "reconnecting..." banner
   - Silent failures

### Fix Plan

#### Fix 1: Add Request Debouncing
Prevent mode polling for 5 seconds after manual mode change:

```javascript
let lastModeChange = 0;

async function setSystemMode(mode) {
  lastModeChange = Date.now();
  // ... existing code ...
}

async function refreshSystemMode() {
  // Don't poll if we just changed mode
  if (Date.now() - lastModeChange < 5000) return;
  // ... existing code ...
}
```

#### Fix 2: Reduce Polling Frequency
Current aggressive polling causes backend stress:
- Relays: 1000ms → 3000ms
- E-stop: 2000ms → 5000ms  
- System mode: 3000ms → 5000ms

#### Fix 3: Add Error Recovery
```javascript
let consecutiveErrors = 0;
let currentBackoff = 0;

async function refreshWithBackoff(fn, name) {
  try {
    await fn();
    consecutiveErrors = 0;
    currentBackoff = 0;
  } catch (e) {
    consecutiveErrors++;
    currentBackoff = Math.min(30000, 1000 * Math.pow(2, consecutiveErrors));
    console.error(`[${name}] Failed (${consecutiveErrors} in a row), backing off ${currentBackoff}ms`, e);
    
    if (consecutiveErrors > 3) {
      showReconnectingBanner();
    }
  }
}
```

#### Fix 4: Improve Mode Synchronization
Ensure all controller tabs properly understand mode values:
- pH tab: uses "manual"
- EC tab: uses "manual"
- Sensors tab: uses "manual"
- Lights tab: uses "auto"
- Circulation tab: uses "auto"

Map consistently across all tabs.

## Issue #2: UI "Goes Offline" After Some Time

### User Report
- UI loads initially (sometimes after multiple reloads)
- Works for a few minutes
- Then "goes offline"
- Requires browser refresh to recover

### Investigation

**Possible Causes:**
1. Backend stops responding (server crash)
2. Too many concurrent requests (backend overload)
3. WebSocket connection dies (if used)
4. JavaScript error crashes polling loops
5. Memory leak causes browser tab to freeze
6. CORS or auth token expiry

**Testing Needed:**
- [ ] Check browser console for errors
- [ ] Check network tab during "offline" state
- [ ] Monitor backend logs during offline period
- [ ] Check if backend process is still running
- [ ] Test with reduced polling frequency

### Hypothesis: Polling Overload

Current polling intervals create burst traffic:
- Every second: Relays request (1KB)
- Every 2 seconds: E-stop request
- Every 3 seconds: System mode request  
- Every 5 seconds: Sensors request (can be large)
- Every 5 seconds: Chiller status
- Every 10 seconds: Global health

**Peak traffic:** Up to 10+ requests per second during alignment

This could:
- Overwhelm backend (especially on Pi)
- Cause request queueing
- Trigger timeouts
- Create cascading failures

### Fix: Reduce Polling Load

#### Phase 1: Immediate (Non-critical Updates)
```javascript
// Relays: 1s → 3s (still responsive)
setInterval(refreshRelays, 3000);

// E-stop: 2s → 5s (emergency, but not real-time)
setInterval(refreshEstop, 5000);

// System mode: 3s → 5s (rarely changes)
setInterval(refreshSystemMode, 5000);

// Sensors: 5s → 10s (slow-changing)
setInterval(refreshSensors, 10000);
```

#### Phase 2: Consolidate Requests
Use `/api/controllers/status` which returns everything in one call:
- System mode
- All controller modes
- E-stop status
- Controller health

Single request replaces 5+ individual requests.

#### Phase 3: Optimize Sensor Reads
- Use cached sensor data from DB (not live I²C)
- Backend should cache for 10s minimum
- UI polls cache, not hardware

## Issue #3: Too Much Documentation

### Current State
```
COMMISSIONING_RUNBOOK.md          (10KB)
COMMISSIONING_UNIFIED_TASKS.md    (6KB)
PI_COMMISSIONING_CHECKLIST.md     (13KB)
MODE_CONTROLLER_IMPLEMENTATION.md (9KB)
MODE_IMPLEMENTATION_SUMMARY.md    (9KB)
MODE_SYNC_FIXES.md                (6KB)
MODE_SYNC_ISSUE.md                (10KB)
+ 20+ other docs
```

### Problem
- Hard to find current info
- Conflicting information
- Shows history of multiple AIs
- No clear "source of truth"

### Fix: Documentation Consolidation

#### Create Master Documents

1. **COMMISSIONING.md** (single source)
   - Merge all commissioning docs
   - Step-by-step current process
   - Troubleshooting section
   - Archive old docs to `docs/archive/commissioning/`

2. **SYSTEM_MODES.md** (architecture)
   - How modes work
   - System mode vs controller modes
   - API endpoints
   - UI interaction patterns
   - Archive mode issue docs to `docs/archive/mode_fixes/`

3. **CURRENT_STATUS.md** (living document)
   - What works ✅
   - What's broken ❌
   - What's next ⏭️
   - Last updated timestamp

4. **README.md** (entry point)
   - Quick start
   - Link to detailed docs
   - Current version status

#### Archive Strategy
```
docs/
  archive/
    commissioning/
      - COMMISSIONING_RUNBOOK.md (dated)
      - COMMISSIONING_UNIFIED_TASKS.md (dated)
      - PI_COMMISSIONING_CHECKLIST.md (dated)
    mode_fixes/
      - MODE_CONTROLLER_IMPLEMENTATION.md (dated)
      - MODE_IMPLEMENTATION_SUMMARY.md (dated)
      - MODE_SYNC_FIXES.md (dated)
      - MODE_SYNC_ISSUE.md (dated)
  current/
    - COMMISSIONING.md (master, current)
    - SYSTEM_MODES.md (master, current)
    - API_REFERENCE.md (generated from code)
```

## Implementation Priority

### P0 - Critical (DO NOW)
1. ✅ Test backend mode switching - CONFIRMED WORKING
2. ⏳ Add frontend debouncing for mode changes
3. ⏳ Reduce polling frequency
4. ⏳ Test UI stability for 10+ minutes

### P1 - High (DO TODAY)
5. ⏳ Add error recovery and backoff
6. ⏳ Consolidate documentation
7. ⏳ Test full commissioning workflow

### P2 - Medium (DO THIS WEEK)
8. Optimize request consolidation
9. Add UI connection status indicator
10. Improve error messages

## Testing Checklist

- [ ] Mode switching works 10/10 times
- [ ] UI stays online for 1+ hour
- [ ] Can complete commissioning workflow
- [ ] No console errors during normal operation
- [ ] Backend logs show normal operation
- [ ] All tests pass
- [ ] Documentation is clear

## Next Steps

1. Apply frontend fixes to relays_v2.js
2. Test in browser for 15+ minutes
3. If stable, move to commissioning workflow test
4. Clean up documentation
5. Mark as ready for production use
