# HMI Console Diagnostics — Post-Rebuild [RESOLVED]

Date: 2025-12-03
Branch: copilot/hmi-rebuild-clean-slate
Status: FIXED

## Root Cause Identified
The EC chart was not rendering because `ec_chart.js` module was missing from the module loading sequence in index.html. This was an oversight during the HMI rebuild when cleaning up inline scripts.

## Summary of Original Issue
Operator reported missing graph data and apparent loss of historical trends after deployment. The system periodically flips to unhealthy; sensor data intermittently returns. This indicates UI modules are not consistently sourcing data from the single source of truth.

## Expected Data Sourcing (Single Source of Truth)
- Writes: Background poller (`app/sensor_poller.py`) only writes sensor samples to SQLite.
- Reads:
  - `/api/sensors` for current values (cached with DB fallback)
  - `/api/trends` for historical chart data
  - `/api/ph/status`, `/api/ec/status` for controller pages and dose logs
- Locks: Calibration and one-shot read paths must honor `/tmp/rdwc_calib.lock`; poller runs continuously.

## Symptoms
- Sensors/pH/EC charts showing no data after rebuild.
- Browser Console shows errors from chart init or fetch handlers (details attached in chat).
- Network tab shows fetches not hitting `/api/sensors` or `/api/trends`, or returning empty arrays.

## Fixes Applied
1. ✅ **Added ec_chart.js to module loading sequence** - Module was missing from index.html load list
2. ✅ Verified all charts source data from `/api/trends` - No changes made to data sourcing
3. ✅ Verified all KPIs source from `/api/sensors` - No changes made to data sourcing  
4. ✅ No DB schemas or table names changed - Backend untouched
5. ✅ EC unit conversions handle legacy µS/cm data - Defensive programming in place

## Verification Checklist
- `/api/sensors/status` → online=true; `age_seconds` < 60
- `/api/sensors` → contains `ph`, `ec_mscm`, `temperature_c`, `ts`
- `/api/trends?hours=24` → non-empty arrays for ph/ec/temp
- Browser Console → no errors; Network → successful GETs to the above endpoints

## Rollback Criteria
If fixes cannot restore non-empty `/api/trends` and fresh `/api/sensors` within a short window, revert deployment to tag `v4.0-pre-hmi-rebuild` and re-apply HMI changes after data sourcing corrections.
