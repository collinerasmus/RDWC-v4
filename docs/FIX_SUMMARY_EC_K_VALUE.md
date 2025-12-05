# Fix Summary: EC Sensor K Value Persistence

## Issue Addressed
**User Report**: "wrong k value, should be 0.1" and "this is supposed to be 0.1, i tried to adjust and 'set k' but when i refreshed the k was back to 1.0."

## Root Cause
The EC sensor k value was being set directly on the device via I²C command but was not persisted to the database. This caused the k value to revert to the default (1.0) whenever:
- The sensor poller restarted
- The main application restarted  
- The sensor was power-cycled
- The system rebooted

## Solution Implemented

### 1. Database Persistence
Added `ec.k_value` setting to the database defaults in `app/settings.py`:
```python
"ec.k_value": "1.0",  # EC probe K factor (probe constant)
```

### 2. API Endpoint Updates

#### `/api/ec/k` (POST)
Modified to persist k value after setting on device:
```python
# Set on device
response = ec_dev.cmd(f"K,{k:.2f}", read_len=32, settle=0.3)

# Persist to database
upsert_settings({"ec.k_value": str(k)})
```

Added validation:
- Rejects negative or zero k values
- Warns (but allows) non-standard k values (not 0.1, 1.0, or 10.0)

#### `/api/ec/cal/status` (GET)
Modified to return k value from settings instead of querying device:
```python
settings = get_all_settings()
k_value = float(settings.get("ec.k_value", "1.0"))
return {"ok": True, "k": k_value, ...}
```

### 3. Automatic Restoration on Sensor Init
Modified `EZO.init_once()` in `app/ezo_i2c_stabilized.py` to restore k value from settings:
```python
if self.addr == EC_ADDR:
    settings = get_all_settings()
    k_value = float(settings.get("ec.k_value", "1.0"))
    self.cmd(f"K,{k_value:.2f}", read_len=0, settle=0.3)
```

This ensures the k value is automatically applied every time the sensor initializes.

### 4. Input Validation
Added validation at multiple levels:
- API endpoint validates positive values
- Initialization warns on non-standard values but proceeds
- Prevents invalid values from corrupting sensor behavior

### 5. Formatting Consistency
Standardized k value formatting to `.2f` (2 decimal places) across:
- API endpoint command
- Sensor initialization command
- Sufficient precision for standard values (0.1, 1.0, 10.0)

## Testing

### Test Suite: `tests/test_ec_k_value_persistence.py`
Created comprehensive test suite with 6 tests covering:

1. **test_k_value_in_settings_defaults**: Verifies default value exists in settings
2. **test_ec_set_k_persists_to_settings**: Tests persistence after setting
3. **test_ec_cal_status_returns_k_from_settings**: Verifies status endpoint returns from settings
4. **test_ezo_init_once_restores_k_value**: Tests automatic restoration on EC sensor init
5. **test_non_ec_sensor_does_not_restore_k_value**: Ensures pH/RTD sensors don't restore k value
6. **test_k_value_validation_warns_on_non_standard**: Tests validation warnings

All tests use pytest fixtures for maintainability.

**Test Results**: ✅ All 6 tests pass

### Security Check
**CodeQL Scan**: ✅ No security vulnerabilities found

## Files Modified

### Code Changes
- `app/settings.py` - Added default setting
- `app/main.py` - Updated API endpoints with persistence and validation
- `app/ezo_i2c_stabilized.py` - Added automatic restoration on init

### Tests
- `tests/test_ec_k_value_persistence.py` - Comprehensive test suite

### Documentation
- `docs/EC_K_VALUE_CALIBRATION.md` - Complete user guide
- `docs/FIX_SUMMARY_EC_K_VALUE.md` - This summary

## User Impact

### Before Fix
1. User sets k value to 0.1 via UI
2. k value works temporarily
3. After restart/refresh, k value reverts to 1.0
4. User must manually re-set k value after each restart

### After Fix
1. User sets k value to 0.1 via UI
2. k value is saved to database
3. After restart/refresh, k value is automatically restored to 0.1
4. No manual intervention required

## How to Use

### Setting K Value
1. Navigate to EC tab in UI
2. Click "Set K" button
3. Enter k value (e.g., 0.1)
4. Value is persisted and will survive restarts

### Verifying K Value
Check current k value via:
```bash
curl http://localhost:8080/api/ec/cal/status
```

### Standard K Values
- **K = 0.1**: Low conductivity (0.5 - 50 µS/cm)
- **K = 1.0**: Standard range (5 - 200,000 µS/cm) - Default
- **K = 10**: High conductivity (100 µS/cm - 1,000,000 µS/cm)

## Code Review Feedback Addressed

### Round 1
✅ Simplified EC sensor detection (address only, removed redundant name check)
✅ Improved k value precision from .1f to .2f for better accuracy

### Round 2
✅ Added input validation for k values
✅ Removed unused mock variables
✅ Refactored tests with pytest fixtures to reduce duplication

### Round 3
✅ Security scan passed with no vulnerabilities

## Related Issues
This fix addresses the core issue reported:
- User cannot persist EC k value setting
- K value resets to default after restart

## Follow-up Recommendations
1. Consider adding a UI indicator showing whether k value is standard or custom
2. Consider adding a "Reset to Standard" button for k value in UI
3. Monitor logs for non-standard k value warnings in production

## Conclusion
The EC sensor k value persistence issue has been fully resolved with:
- ✅ Complete persistence across restarts
- ✅ Automatic restoration on sensor initialization
- ✅ Input validation and warnings
- ✅ Comprehensive test coverage
- ✅ Security validation
- ✅ User documentation

The fix is minimal, surgical, and follows the repository's existing patterns for settings persistence.
