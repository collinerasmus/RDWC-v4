# Chiller Interlock System Documentation

## Overview
The chiller interlock system ensures safe operation of the Hailea HS-52A chiller by requiring proper circulation before allowing the chiller to activate.

## Core Safety Requirements
1. **Main Pump**: RDWC circulation must be active
2. **Chiller Pump**: Dedicated chiller water circulation must be active
3. **Both Required**: Chiller power can only engage when both pumps are running

## Current Implementation Status

### ✅ Implemented: Enforcement
**Location**: `app/chiller_control.py:226-238` in `set_chiller_relay()`

**Behavior**:
- Blocks chiller from turning ON if main_pump is OFF
- Blocks chiller from turning ON if chiller_pump is OFF
- Returns `False` with appropriate warning log
- Prevents hardware damage from running chiller without circulation

**Code**:
```python
if desired_on:
    relays = get_relay_status()
    main_pump_on = relays.get('main_pump', {}).get('state', False)
    chiller_pump_on = relays.get('chiller_pump', {}).get('state', False)
    
    if not main_pump_on:
        log.warning('[CHILLER] Blocked: Main pump is OFF (RDWC circulation required)')
        return False
    
    if not chiller_pump_on:
        log.warning('[CHILLER] Blocked: Chiller pump is OFF (water circulation required)')
        return False
```

**Test Coverage**: ✅ 9 tests in `tests/test_chiller_interlock.py`
- `test_set_chiller_relay_enforces_main_pump`
- `test_set_chiller_relay_enforces_chiller_pump`
- `test_set_chiller_relay_allows_with_both_pumps`
- Plus 6 more status reporting tests

### ❌ Not Implemented: Auto-Remediation
**Expected Behavior** (per problem statement):
- When main_pump turns ON in AUTO mode → automatically turn chiller_pump ON
- When circulation is lost mid-run → automatically shut down chiller

**Current Behavior**:
- Pumps operate independently
- No automatic coordination between main_pump and chiller_pump
- Chiller will stay blocked if pumps aren't manually coordinated
- If a pump turns OFF while chiller is running, chiller continues (unsafe)

**Implementation Gap**:
The system has **reactive enforcement** (prevents bad states from being entered) but lacks **proactive coordination** (automatically creates safe states) and **continuous monitoring** (detects and responds to state changes during operation).

## API Status Reporting

### ✅ Implemented: Interlock Status API
**Endpoint**: `GET /api/chiller/status`

**Response Fields**:
```json
{
  "interlock_ok": true,
  "interlock_details": {
    "main_pump_on": true,
    "chiller_pump_on": true,
    "chiller_running": false,
    "auto_enabled": true,
    "violations": null
  },
  // ... other chiller status fields
}
```

**Violations Detected**:
- `main_pump_off`: Chiller running without main pump
- `chiller_pump_off`: Chiller running without chiller pump
- `error_reading_status`: Exception during status check

**Test Coverage**: ✅ 6 tests
- `test_interlock_status_all_ok`
- `test_interlock_status_main_pump_violation`
- `test_interlock_status_chiller_pump_violation`
- `test_interlock_status_both_pumps_violation`
- `test_interlock_status_chiller_off_ok`
- `test_chiller_state_includes_interlock`

## Recommendations for Full Implementation

### 1. Add Proactive Coordination
**File**: `app/chiller_control.py` or new `app/circulation_coordinator.py`

**Logic**:
```python
def coordinate_pumps_for_chiller():
    """Ensure chiller_pump is ON when main_pump is ON in AUTO mode."""
    if get_mode('circulation') != 'auto':
        return
    
    relays = get_relay_status()
    main_on = relays.get('main_pump', {}).get('state', False)
    chiller_on = relays.get('chiller_pump', {}).get('state', False)
    
    # Auto-remediation: turn on chiller_pump when main_pump is on
    if main_on and not chiller_on:
        set_chiller_pump(True, reason='auto_coordination')
```

### 2. Add Continuous Monitoring
**Integration**: In `chiller_control.py:control_loop()` at line 372

**Logic**:
```python
def control_loop():
    while not _stop_control:
        try:
            # Check for interlock violations mid-operation
            status = get_interlock_status()
            if not status['interlock_ok'] and _chiller_state['is_running']:
                # Emergency shutdown
                set_chiller_relay(False, 'interlock_violation_detected')
                log.error(f"[CHILLER] Emergency shutdown: {status['interlock_details']['violations']}")
            
            # Existing control logic...
            should_run, reason = should_chiller_run()
            # ...
```

### 3. Add Configuration Options
**Settings**:
- `chiller.auto_coordinate_pumps`: Enable/disable auto-remediation (default: true)
- `chiller.monitor_interlock_continuous`: Enable/disable continuous monitoring (default: true)
- `chiller.shutdown_on_violation`: Auto-shutdown on violation (default: true)

## Current Safety Posture

### ✅ Strengths
1. Prevents chiller from starting without circulation
2. Clear status API for monitoring
3. Comprehensive test coverage (9 tests)
4. Violations detected and reported

### ⚠️ Gaps
1. **No automatic pump coordination**: User must manually ensure both pumps are on
2. **No mid-operation monitoring**: Pump failure during chiller operation not detected
3. **No automatic shutdown**: Chiller continues if pump stops mid-run
4. **No UI warnings**: Banner shows status but doesn't trigger alerts

### 🎯 Priority Improvements
1. **High**: Add continuous interlock monitoring to control loop
2. **High**: Add emergency shutdown on violation detection
3. **Medium**: Add auto-coordination in AUTO mode
4. **Low**: Add UI alerts/warnings for violations

## Testing Strategy

### Existing Tests (9 total)
All tests in `tests/test_chiller_interlock.py`:
- Enforcement at relay set time
- Status API correctness
- Violation detection
- Multiple violation scenarios

### Needed Tests (if auto-remediation added)
- Test auto-coordination when main_pump turns ON
- Test emergency shutdown when pump fails mid-run
- Test mode-based coordination (AUTO vs MANUAL)
- Test configuration option behavior

## Usage Examples

### Check Interlock Status (API)
```bash
curl -s http://192.168.88.49:8080/api/chiller/status | jq '.interlock_details'
```

### Expected Safe State
```json
{
  "interlock_ok": true,
  "interlock_details": {
    "main_pump_on": true,
    "chiller_pump_on": true,
    "chiller_running": false,
    "auto_enabled": true,
    "violations": null
  }
}
```

### Violation Example
```json
{
  "interlock_ok": false,
  "interlock_details": {
    "main_pump_on": false,
    "chiller_pump_on": true,
    "chiller_running": true,
    "auto_enabled": true,
    "violations": ["main_pump_off"]
  }
}
```

## Related Files
- `app/chiller_control.py`: Chiller controller and interlock enforcement
- `app/relays_core.py`: Relay control primitives
- `tests/test_chiller_interlock.py`: Interlock test suite
- `app/static/js/chiller.js`: UI status display

---
**Last Updated**: 2025-11-23  
**Status**: Enforcement implemented, auto-remediation not yet implemented  
**Test Coverage**: 9 tests passing
