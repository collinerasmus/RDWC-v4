# HMI Console Diagnostics — Post-Rebuild

Date: 2025-12-03
Branch: copilot/hmi-rebuild-clean-slate

## Summary
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

## Required Fixes
1. Ensure all charts source data from `/api/trends` only; remove any direct table or sensor calls from JS.
2. Ensure all KPIs and status cards source from `/api/sensors` (no bypass of poller or diag endpoints).
3. Verify poller is writing fresh rows (ts age <60s) and `/api/sensors/status` returns online=true.
4. Do not change DB schemas or table names; use existing tables that held working history pre-rebuild.
5. Add robust empty-data handling in chart modules so UI remains functional while data catches up.

## Verification Checklist
- `/api/sensors/status` → online=true; `age_seconds` < 60
- `/api/sensors` → contains `ph`, `ec_mscm`, `temperature_c`, `ts`
- `/api/trends?hours=24` → non-empty arrays for ph/ec/temp
- Browser Console → no errors; Network → successful GETs to the above endpoints

## Rollback Criteria
If fixes cannot restore non-empty `/api/trends` and fresh `/api/sensors` within a short window, revert deployment to tag `v4.0-pre-hmi-rebuild` and re-apply HMI changes after data sourcing corrections.
