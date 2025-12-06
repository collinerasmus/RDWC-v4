# EC Calibration Fix Summary - K=0.1 Probe Support

## Overview
This document summarizes the changes made to fix EC probe calibration for K=0.1 conductivity probes based on the Atlas Scientific EZO EC datasheet (pages 40-65).

## Problem Statement
The user reported that the EC calibration process was incorrect for their K=0.1 probe:
- Missing dry calibration step (required for K=0.1 probes)
- Wrong calibration values (needed 84/1413 µS/cm for their K=0.1 calibration solutions)
- No guidance for probe-specific calibration
- UI didn't show proper sequence or which steps were completed

## Solution

### Key Changes

#### 1. Added Dry Calibration
- **New Function**: `calibrate_ec_dry()` in `sensor_controller.py`
- **New Endpoint**: `POST /api/ec/cal/dry`
- **UI Button**: Added "Calibrate Dry" button in Sensors tab
- **Required**: First step for K=0.1 probes according to Atlas Scientific datasheet

#### 2. Dynamic Calibration Values
Updated calibration functions to auto-select values based on current K factor:

| K Value | Low Point (µS/cm) | High Point (µS/cm) | Use Case |
|---------|-------------------|-------------------|----------|
| 0.1 | 84 | 1,413 | Low conductivity (0.5-50 µS/cm) - Hydroponics |
| 1.0 | 1,413 | 12,880 | Standard range (5-200,000 µS/cm) |
| 10.0 | 12,880 | 80,000 | High conductivity (100-1M µS/cm) |

This ensures backward compatibility - existing K=1.0 and K=10.0 users are unaffected.

#### 3. Enhanced UI
- **Step-by-step wizard** with numbered steps (1: Dry, 2: Low, 3: High)
- **Visual indicators** (✓) showing which calibration points are completed
- **Warning banner** explaining the calibration sequence
- **K=0.1 default** in dropdown with range information
- **Auto-refresh** of calibration status on load

#### 4. Enhanced Status Parsing
The calibration status endpoint now returns detailed information:
```json
{
  "ok": true,
  "k": 0.1,
  "cal": "dry+two-point",
  "dry": true,
  "low": true,
  "high": true,
  "cal_response": "?CAL,3",
  "note": "K factor is source of truth from settings"
}
```

### Files Changed

#### Backend
- **app/sensor_controller.py**
  - Added `calibrate_ec_dry()` function
  - Updated `calibrate_ec_low()` with dynamic defaults
  - Updated `calibrate_ec_high()` with dynamic defaults
  - Enhanced `get_ec_calibration_status()` to parse dry/low/high

- **app/main.py**
  - Added `/api/ec/cal/dry` endpoint
  - Updated endpoint documentation

#### Frontend
- **app/static/index.html**
  - Added calibration wizard UI
  - Added dry calibration button
  - Added step indicators
  - Updated K factor dropdown with ranges
  - Added warning banner

- **app/static/js/ec.js**
  - Added `ecCalDry()` function
  - Updated calibration prompts
  - Added auto-refresh
  - Fixed float comparison (Math.abs tolerance)
  - Enhanced header chips

#### Testing
- **tests/test_ec_calibration_k01.py**
  - 10 comprehensive unit tests
  - Tests dry/low/high calibration
  - Tests dynamic defaults
  - Tests K value persistence
  - Tests calibration status parsing
  - All tests passing ✅

#### Documentation
- **docs/EC_CALIBRATION_K01_GUIDE.md**
  - Complete calibration guide
  - Covers all K values (0.1, 1.0, 10.0)
  - Troubleshooting section
  - API reference
  - Maintenance schedule

#### Tools
- **tools/test_ec_calibration.py**
  - Interactive testing script
  - Can test endpoints without physical probe
  - Guides through full calibration sequence

## Usage

### Via UI (Recommended)
1. Navigate to **Sensors** tab
2. Open **EC Probe Calibration** section
3. Verify K value shows **0.1** (green indicator)
4. Follow the step-by-step wizard:
   - **Step 1 (Dry)**: Remove probe, air dry 30s, click "Calibrate Dry"
   - **Step 2 (Low)**: Place in 84 µS/cm solution, wait 30s, click "Calibrate Low"
   - **Step 3 (High)**: Place in 1,413 µS/cm solution, wait 30s, click "Calibrate High"
5. Verify all steps show **✓** indicator

### Via Testing Tool
```bash
# Test without physical probe (checks endpoints)
python tools/test_ec_calibration.py --skip-physical

# Interactive calibration with physical probe
python tools/test_ec_calibration.py
```

### Via API
```bash
# Check K value
curl http://localhost:8080/api/ec/cal/status

# Set K value (if not 0.1)
curl -X POST http://localhost:8080/api/ec/k \
  -H "Content-Type: application/json" \
  -d '{"k": 0.1}'

# Dry calibration (probe in air, dry)
curl -X POST http://localhost:8080/api/ec/cal/dry

# Low calibration (auto-selects 84 µS/cm for K=0.1)
curl -X POST http://localhost:8080/api/ec/cal/low \
  -H "Content-Type: application/json" \
  -d '{}'

# High calibration (auto-selects 1413 µS/cm for K=0.1)
curl -X POST http://localhost:8080/api/ec/cal/high \
  -H "Content-Type: application/json" \
  -d '{}'

# Verify status
curl http://localhost:8080/api/ec/cal/status
```

## Validation

### Tests
- ✅ 10 unit tests, all passing
- ✅ Covers all calibration scenarios
- ✅ Tests dynamic defaults for all K values
- ✅ Tests K value persistence

### Security
- ✅ CodeQL scan: 0 vulnerabilities
- ✅ No security issues introduced
- ✅ Input validation maintained
- ✅ Calibration lock enforced

### Code Review
- ✅ All feedback addressed
- ✅ Float comparison fixed (tolerance-based)
- ✅ Dynamic defaults for backward compatibility
- ✅ Prompt messages shortened

## Backward Compatibility

The changes are **100% backward compatible**:
- **K=1.0 users**: Calibration auto-selects 1413/12880 µS/cm (unchanged behavior)
- **K=10.0 users**: Calibration auto-selects 12880/80000 µS/cm (new support)
- **Custom values**: Can still be passed via API `{"us_cm": value}`
- **API signatures**: No breaking changes
- **Existing workflows**: All continue to work

## What Changed vs. What Stayed the Same

### Changed ✅
- Added dry calibration step (new requirement for K=0.1)
- Default calibration values now dynamic based on K factor
- UI shows step-by-step wizard with indicators
- Calibration status parsing enhanced

### Stayed the Same ✅
- K value persistence (already implemented)
- Calibration lock mechanism
- API endpoint signatures
- Settings structure
- Database schema

## References

### Documentation
- **Complete Guide**: `docs/EC_CALIBRATION_K01_GUIDE.md`
- **This Summary**: `docs/EC_CALIBRATION_FIX_SUMMARY.md`
- **K Value Fix**: `docs/FIX_SUMMARY_EC_K_VALUE.md` (previous work)

### Datasheet
- **Atlas Scientific EZO EC Datasheet**: https://files.atlas-scientific.com/EC_EZO_Datasheet.pdf
  - Pages 40-64: I2C commands
  - Page 65: Calibration theory

### Code
- **Backend**: `app/sensor_controller.py`, `app/main.py`
- **Frontend**: `app/static/index.html`, `app/static/js/ec.js`
- **Tests**: `tests/test_ec_calibration_k01.py`
- **Tools**: `tools/test_ec_calibration.py`

## Troubleshooting

### K Value Shows 1.0 Instead of 0.1
**Solution**: Use UI dropdown or API to set K=0.1:
```bash
curl -X POST http://localhost:8080/api/ec/k \
  -H "Content-Type: application/json" \
  -d '{"k": 0.1}'
```

### Calibration Lock Error
**Issue**: "Calibration lock held by sensor poller"

**Solution**: 
1. Wait 5 seconds and try again
2. If persistent, remove lock: `rm /tmp/rdwc_calib.lock`

### Readings 10x Too High/Low
**Cause**: Wrong K value

**Solution**: 
1. Check physical probe label (should say K=0.1)
2. Verify K value in UI matches probe
3. Recalibrate with correct K value

### Dry Calibration Not Showing in Status
**Issue**: Status shows "one-point" or "two-point" but not "dry+two-point"

**Cause**: Dry calibration may have been skipped or probe response is in old format

**Solution**:
1. Perform dry calibration again
2. Check UI for ✓ indicator on dry step
3. Query status API to verify

## Next Steps

1. **Test the changes** on your system using the UI or testing tool
2. **Verify calibration** works correctly with your K=0.1 probe
3. **Check readings** are sensible (expected range: 0.5-3.0 mS/cm for hydroponics)
4. **Report any issues** if calibration doesn't work as expected

## Support

For questions or issues:
1. Check `docs/EC_CALIBRATION_K01_GUIDE.md` for detailed instructions
2. Run `python tools/test_ec_calibration.py --skip-physical` to test endpoints
3. Check calibration status via API: `curl http://localhost:8080/api/ec/cal/status`
4. Review troubleshooting section in the guide

## Change Log

### 2025-01-06
- ✅ Added dry calibration support
- ✅ Implemented dynamic defaults based on K value
- ✅ Enhanced UI with step-by-step wizard
- ✅ Added comprehensive testing and documentation
- ✅ Addressed code review feedback
- ✅ Passed security scan (0 vulnerabilities)
- ✅ All tests passing (10/10)

## Conclusion

The EC calibration process now properly supports K=0.1 probes while maintaining backward compatibility with K=1.0 and K=10.0 probes. The implementation follows the Atlas Scientific datasheet specifications and includes comprehensive testing and documentation.

**Status**: ✅ Complete and ready for use
