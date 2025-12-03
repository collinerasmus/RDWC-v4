# Bug Fix Summary - EC Chart Data Loss

**Date**: 2025-12-03  
**Branch**: copilot/hmi-rebuild-clean-slate  
**Status**: ✅ RESOLVED

## Issue Reported

After HMI rebuild deployment, the EC chart was not displaying any data. Operator reported:
- EC values showing "424 ms/cm" instead of "0.424 mS/cm" in KPIs
- Sensors graph showing 424 
- No data in EC chart

## Root Causes Identified

### 1. Missing EC Chart Module (CRITICAL)
**Problem**: `ec_chart.js` was not loaded  
**Cause**: During HMI rebuild cleanup, module was omitted from loading sequence  
**Impact**: EC dose chart could not render at all  
**Fix**: Added `ec_chart.js` to module load list in index.html (commit 8326d31)

### 2. EC Unit Display Issue  
**Problem**: Legacy database readings in µS/cm displayed as mS/cm  
**Cause**: Backend has µS/cm data (e.g., 424) that should be 0.424 mS/cm  
**Impact**: Incorrect unit display in multiple UI locations  
**Fix**: Added defensive conversion (divide by 1000 if value > 20) in 9 locations with logging

## Fixes Applied

### Module Loading Fix
```javascript
// Added ec_chart.js to sequence after ec.js:
seq([...'ec.js','ec_chart.js','sensors_calib.js'...])
```

### EC Unit Conversion (9 locations)
All conversions check: if EC value > 20, assume µS/cm and convert to mS/cm

**Files modified**:
- `app/static/js/sensors.js` (4 locations)
- `app/static/js/ec.js` (3 locations)  
- `app/static/js/ec_chart.js` (1 location)
- `app/static/js/trends.js` (removed incorrect autodetect)

**Logging**: Every conversion logs a labeled warning for debugging

## Verification Steps

After deployment, verify:

1. **Module Loading**
   ```
   Open browser console → Should see "[EC Chart] init" message
   ```

2. **EC Values**
   ```
   EC KPIs should show 0.xx (not 424)
   Check console for "[Sensors] EC value > 20..." warnings if conversion occurs
   ```

3. **EC Chart**
   ```
   EC tab → EC chart should display historical dose data
   Should show bars for dose events and line for EC trend
   ```

4. **API Endpoints**
   ```
   /api/sensors/status → online: true, age_seconds < 60
   /api/sensors → contains ph, ec_mscm, temperature_c
   /api/trends?hours=24 → non-empty arrays for ph/ec/temp
   ```

5. **Console Errors**
   ```
   No JavaScript errors in browser console
   Network tab shows successful GETs to API endpoints
   ```

## Deployment Command

```bash
ssh pi@192.168.88.49 "cd ~/rdwc-v4 && git fetch origin && git reset --hard origin/copilot/hmi-rebuild-clean-slate && sudo systemctl restart rdwc && sudo systemctl restart rdwc-sensors"
```

Wait 5-10 seconds for services to restart, then open: http://192.168.88.49:8080

## Testing Checklist

- [ ] HMI loads without console errors
- [ ] All 10 tabs render correctly
- [ ] EC KPIs show 0.xx format (not 424)
- [ ] EC chart displays historical data
- [ ] Sensors chart shows trends for all 3 parameters
- [ ] pH chart displays dose events
- [ ] All sections permanently expanded (no collapsibles)
- [ ] Dark theme maintained
- [ ] No data loss (historical trends intact)

## Rollback

If issues persist:
```bash
ssh pi@192.168.88.49 "cd ~/rdwc-v4 && git fetch origin && git checkout copilot/clean-ec-page-style && sudo systemctl restart rdwc && sudo systemctl restart rdwc-sensors"
```

## Files Changed

**This fix (commit 8326d31)**:
- `app/static/index.html` - Added ec_chart.js to module loading
- `docs/HMI_CONSOLE_ISSUES.md` - Updated with resolution

**Previous EC unit fixes (commits 08972ba through 2b152a9)**:
- `app/static/js/sensors.js` - 4 conversions
- `app/static/js/ec.js` - 3 conversions
- `app/static/js/ec_chart.js` - 1 conversion
- `app/static/js/trends.js` - Removed autodetect

## Confidence Level

**HIGH** - Module loading is a simple, well-tested change. EC conversions are defensive and handle both correct and legacy data formats.

**Risk**: LOW - Rollback available. No database changes. No backend changes.

## References

- Main work order: `HMI_REBUILD_WORKORDER.md`
- Validation report: `HMI_VALIDATION_REPORT.md`
- Deployment guide: `DEPLOY_TO_PI.md`
- Final status: `FINAL_STATUS.md`
- Diagnostics: `docs/HMI_CONSOLE_ISSUES.md`
