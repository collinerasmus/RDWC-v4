# Lights Schedule Midnight Fix - Technical Summary

## Overview
This document provides a technical summary of the midnight boundary fix for the RDWC lights scheduler.

## The Bug

### Symptom
When lights schedule spans midnight (e.g., ON at 22:00, OFF at 10:00 next day), lights incorrectly turn OFF at 23:59 instead of staying ON until 10:00 the next day.

### Root Cause
In `app/scheduler.py`, the `_update_lights_schedule()` method had logic to handle midnight-spanning windows:

```python
# BEFORE (BROKEN)
if off_dt.date() > on_dt.date():
    # Truncate off_time to 23:59 for today
    self._current_lights_off_time = "23:59"  # BUG!
```

This caused:
1. **At 23:59**: Edge detection fired, turning lights OFF
2. **At 00:00**: Midnight reset called `_update_lights_schedule()` for new day
3. **New schedule**: ON at 22:00 today (hasn't happened yet), so lights stay OFF
4. **Result**: Lights OFF from 23:59 until 22:00 next day (14+ hours gap!)

### Why It Happened
The original design tried to "split" midnight-spanning windows into two parts:
- Part 1: Today's portion (ON → 23:59)
- Part 2: Tomorrow's portion (00:00 → OFF)

But there was no mechanism to handle "Part 2" - the continuation after midnight.

## The Fix

### Solution
Detect when we're currently in a window that started yesterday:

```python
# AFTER (FIXED)
if off_dt.date() > on_dt.date():
    # Window spans midnight
    if now.date() > on_dt.date() and now < off_dt:
        # We're after midnight but before actual off_time
        # This is yesterday's window continuation!
        yesterday = now.replace(...) - timedelta(days=1)
        yesterday_on_dt, yesterday_off_dt = lights_window(yesterday)
        
        # Set on_time to YESTERDAY (already happened, won't trigger)
        self._current_lights_on_time = yesterday_on_dt.strftime("%H:%M")
        # Set off_time to TODAY'S actual time (will trigger at correct time)
        self._current_lights_off_time = off_dt.strftime("%H:%M")
```

### How It Works

#### Scenario: Lights ON at 22:00, duration 12h (OFF at 10:00 next day)

**Timeline with Fix:**

**Day 1:**
- **20:00**: Schedule update detects we're before ON time
  - `on_time = "22:00"` (today)
  - `off_time = "10:00"` (tomorrow)
  - Window spans midnight detected

- **22:00:00**: Edge detection fires (h=22, m=0, s=0)
  - Lights turn ON ✅
  - Log: `{"kind": "lights_schedule_on", "time": "22:00", "changed": true}`

- **23:00-23:59**: No edge detection (only fires at s=0)
  - Lights stay ON ✅

**Day 2:**
- **00:00:00**: Midnight reset triggers
  - `_reset_daily_if_needed()` detects new day
  - Calls `_update_lights_schedule()`
  - **NOW THE FIX KICKS IN:**
    - Detects: `now.date() > on_dt.date()` (we're on Day 2)
    - Detects: `now < off_dt` (we're before 10:00)
    - **Conclusion**: We're in yesterday's window continuation!
  - Sets: `on_time = "22:00"` (yesterday - already happened)
  - Sets: `off_time = "10:00"` (today - will fire at 10:00)
  - Log: `{"kind": "lights_schedule_midnight_continuation", ...}`
  - **Lights stay ON** ✅

- **01:00-09:59**: No edge detection
  - Lights stay ON ✅

- **10:00:00**: Edge detection fires (h=10, m=0, s=0)
  - Lights turn OFF ✅
  - Log: `{"kind": "lights_schedule_off", "time": "10:00", "changed": true}`

### Key Insights

1. **Edge-Only Preserved**: Fix maintains pure edge-only behavior
   - No periodic checks to "catch up"
   - Only acts at exact HH:MM:00 times (when s == 0)
   - No continuous polling or state enforcement

2. **Midnight Reset Leverage**: Uses existing `_reset_daily_if_needed()`
   - Already runs at midnight boundary
   - Perfect hook to detect continuation state

3. **Historical Context**: Checks yesterday's schedule when needed
   - Only when: after midnight AND before off_time AND window spans midnight
   - Gets yesterday's window to set correct on_time (already passed)

4. **Minimal Change**: Surgical fix
   - Only modified `_update_lights_schedule()` method
   - No changes to edge detection logic
   - No new timers or threads
   - No database schema changes

## Edge Detection Review

The edge detection logic (unchanged by fix) works as follows:

```python
# In _tick() method (called every 1 second)
wday, h, m, s = _now_tuple()

if s == 0:  # Only at exact minute boundaries
    if h == on_h and m == on_m:
        # ON edge - fires once per minute
        set_lights(True, REASON_SCHEDULE_ON)
        
    elif h == off_h and m == off_m:
        # OFF edge - fires once per minute
        set_lights(False, REASON_SCHEDULE_OFF)
```

**Why s == 0?**
- Ensures edges fire at exact scheduled times (HH:MM:00)
- Prevents duplicate firings within the same minute
- Edge fires once, then s increments to 1..59, preventing re-fire

**Guard Logic (±5s):**
```python
else:  # s != 0
    if 1 <= s <= 5:
        # Re-assert state for 5 seconds after edge
        # Idempotent: won't cause issues if already correct
        if h == on_h and m == on_m:
            set_lights(True, "schedule_guard_on")
        elif h == off_h and m == off_m:
            set_lights(False, "schedule_guard_off")
```

Guards provide a 5-second "safety net" to ensure state is correct, but are optional and idempotent.

## Test Coverage

### Test File: `tests/test_scheduler_midnight.py`

1. **`test_midnight_spanning_window_basic`**
   - Tests 22:00 ON, 12h duration (10:00 OFF next day)
   - Verifies before and after midnight scenarios
   - Validates correct off_time (not truncated to 23:59)

2. **`test_midnight_at_exactly_midnight`**
   - Edge case: ON at 00:00
   - Duration 12h (OFF at 12:00 same day)
   - Ensures no midnight confusion when starting at midnight

3. **`test_no_midnight_crossing_same_day`**
   - Normal case: ON at 06:00, 16h duration (OFF at 22:00 same day)
   - Regression test: ensure fix doesn't break normal schedules

4. **`test_long_duration_crossing_midnight`**
   - Extended span: ON at 20:00, 16h duration (OFF at 12:00 next day)
   - Tests longer midnight crossing periods

5. **`test_midnight_reset_preserves_active_window`**
   - Simulates being at 02:00 AM (after midnight)
   - Schedule: 22:00-10:00 (started yesterday)
   - Validates continuation detection works

6. **`test_is_within_window_helper_midnight_wrap`**
   - Pure function test for `is_within_window()`
   - Tests midnight wrap logic: 22:00-10:00 window
   - Validates 23:00, 02:00 are IN, 10:00 is OUT

7. **`test_edge_detection_at_exact_times`**
   - Validates edge-only behavior
   - Ensures no periodic enforcement

## Performance Impact

**Before Fix:**
- 1 edge detection per second (checking s == 0)
- 1 midnight reset per day

**After Fix:**
- Same: 1 edge detection per second (no change)
- Same: 1 midnight reset per day
- +1 additional check at midnight reset: "Are we in continuation?"
  - O(1) time complexity
  - Only runs once per day
  - Negligible performance impact

**Memory:**
- No new persistent state
- Temporary variables only during `_update_lights_schedule()`
- ~100 bytes additional memory for datetime objects

## Backward Compatibility

✅ **Fully backward compatible**
- No configuration changes required
- No database migrations
- Works with existing schedules
- Same-day schedules unchanged (no regression)
- Midnight-spanning schedules now work correctly

## Future Enhancements (Not Included)

Potential future improvements (out of scope for this fix):
1. Support for multiple light zones with independent schedules
2. Seasonal schedule adjustments (longer days in summer)
3. Gradual dimming (sunrise/sunset simulation)
4. Schedule history/audit trail in database

These were intentionally excluded to maintain the minimal-change principle.

## Deployment Checklist

✅ Code changes minimal and surgical
✅ Tests comprehensive (7 tests, all passing)
✅ Security scan passed (0 vulnerabilities)
✅ Backward compatible (no config changes)
✅ Documentation complete (CHANGELOG, deployment guide)
✅ Rollback procedure documented
✅ Zero downtime deployment possible

## References

- **Code**: `app/scheduler.py` lines ~93-165
- **Tests**: `tests/test_scheduler_midnight.py`
- **Deployment**: `MIDNIGHT_FIX_DEPLOYMENT.md`
- **Changelog**: `CHANGELOG.md` v4.3.0
- **PR**: copilot/fix-midnight-schedule-logic branch

## Author Notes

This fix follows the project's core principles:
- **Edge-only scheduling**: No periodic catch-up loops
- **Minimal changes**: Surgical fix to one method
- **Comprehensive testing**: 7 tests covering all scenarios
- **Production-ready**: Security scanned, documented, tested

The fix elegantly leverages the existing midnight reset mechanism to detect window continuation, requiring no new timers, threads, or periodic checks.
