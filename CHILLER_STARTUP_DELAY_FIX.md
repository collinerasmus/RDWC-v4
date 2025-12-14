# Chiller Startup Delay - Root Cause & Fix

## Root Cause Identified

The chiller was not activating despite all conditions being correct:
- Water temperature: 24.3°C (above 19.7°C threshold)
- Pumps: Both ON
- Interlock: OK
- Auto control: Enabled

**The Issue**: `relays_core.py` has a **5-minute startup delay** (`_CHILLER_STARTUP_DELAY_S = 300`) that blocks the chiller from turning ON during the first 300 seconds after service start. This is intentional compressor protection to prevent rapid cycling during deployments/restarts.

### Code Location
File: `app/relays_core.py`, lines 395-400:
```python
if name == "chiller_power" and desired_on and not force:
    time_since_startup = now - _startup_time
    if time_since_startup < _CHILLER_STARTUP_DELAY_S:
        remaining = int(_CHILLER_STARTUP_DELAY_S - time_since_startup)
        return {"changed": False, "reason": "startup_delay", ...}
```

## Why This Wasn't Obvious

1. **Silent Blocking**: The relay system returns `{"changed": False, "reason": "startup_delay"}` but `set_temperature_relay()` was returning `False` without logging the actual blocking reason
2. **Missing Force Parameter**: Manual override calls (`/api/temperature/force`) couldn't bypass the startup delay because they didn't use the `force=True` flag
3. **Automatic Control**: The background control loop also blocked by startup delay (correct behavior - don't want compressor cycling right after restart)

## Solution Applied

### 1. Enhanced Logging (commit ab2e9b1)
Added detailed logging to `set_temperature_relay()` to explain all blocking conditions:
- Pump interlock checks
- Cooldown periods
- Minimum runtime active

### 2. Force Parameter Support (commit fd43dd9)
- Added `force: bool = False` parameter to `set_temperature_relay()`
- Updated `force_temperature_state()` to pass `force=True`
- This allows manual overrides to bypass startup delay immediately

```python
def set_temperature_relay(desired_on: bool, reason: str = '', force: bool = False) -> bool:
    # Cooldown checks now skip if force=True
    if desired_on and _temperature_state['last_off_time'] and not force:
        # Check cooldown...
    
    relay_set('chiller_power', desired_on, reason=reason, actor='temperature-ctl', force=force)
```

## Behavior After Fix

### Automatic Control (Background Loop)
- Still blocked by 5-minute startup delay ✅ (protects compressor)
- After 5 minutes, activates automatically when temp exceeds threshold
- Logs indicate "startup_delay" reason if force is not used

### Manual Override
- Immediately activates chiller regardless of startup delay
- `/api/temperature/force` endpoint now works immediately after restart
- Useful for testing and emergency operation

## Testing

### Before Fix
```
POST /api/temperature/force {"on": true}
Response: {"success": false, "reason": "Manual override"}
```
Chiller stayed OFF because relay_set returned "startup_delay"

### After Fix  
```
POST /api/temperature/force {"on": true}
Response: {"success": true, ...}
```
Chiller turns ON immediately (force=True bypasses startup delay)

## Design Rationale

The 5-minute startup delay is **intentional** for these reasons:
1. **Compressor Protection**: Prevents rapid on/off cycling during service restarts
2. **Thermal Stabilization**: Gives water temperature time to stabilize after service restart
3. **Integration Safety**: Ensures sensors and calibration are ready before chiller activates

The fix maintains this protection for automatic control while allowing manual overrides for testing/emergency use.

## Configuration

To adjust the startup delay protection, modify in `app/relays_core.py`:
```python
_CHILLER_STARTUP_DELAY_S = 300  # Change this value (seconds)
```

For development/testing, set to 0 or low value. For production, 300 seconds (5 minutes) is recommended.
