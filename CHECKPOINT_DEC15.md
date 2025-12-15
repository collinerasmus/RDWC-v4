# RDWC-v4 Checkpoint — December 15, 2025

## System Status Summary

### ✅ Operational State
- **API**: Healthy, all endpoints responsive (b74639c deployed)
- **Sensor Poller**: Active, 5–10s cadence, data flowing
- **Charts**: All initialized, 5s auto-refresh per chart type
- **Database**: Fresh state (rdwc.db reset/clean)
- **Relay System**: Responsive, event logging functional, no errors
- **Services**: rdwc + rdwc-sensors both active on Pi

### Forensics: This Morning's Dosing
- **Result**: Zero dose events in database (system fresh/clean state)
- **Implication**: Previous data purged on restart; safe to proceed with simulation
- **Status**: No parameter adjustments needed yet—system is pristine baseline

### Console Status (Latest Poll)
```
Sensors: all online, timestamps fresh (<60s old)
Temperature: 25.71–25.72 °C (stable)
pH: 5.947–5.951 (baseline, no dosing yet)
EC: 0.9516–0.952 mS/cm (baseline, no dosing yet)

Charts: all 1440 datapoints loaded (24h window)
Lights chart: rendering 2 datasets
Circulation chart: ready
Temperature chart: 152 cooler events

Services: rdwc + rdwc-sensors active
Intervals: cleared & healthy (no stacking detected)
```

### Code Consolidation Status
✅ **Completed in this session**:
- Removed duplicate chart logic (v2 controllers separated from chart files)
- Fixed interval stacking (clear before set)
- Added DB persistence + fallback (relay_events with in-memory merge)
- Hardened relay event reads (retry, cache, endpoint guard)
- Removed explicit `conn.close()` on pooled connections ("closed database" fix)
- Latest commit: `b74639c` (all changes deployed + service restarted)

✅ **Architecture Verified**:
- `relays_core.py`: centralized relay mutations, DB logging, no direct GPIO access
- `sensors_core.py`: cached reads, temperature compensation throttle (0.2°C or 60s)
- `dosing.py`: unified safety caps, event log schema
- Charts: unified base (`chart_base.js`) + domain-specific v2 charts
- Controllers: separate interval management, no chart coupling

### Database Tables Verified
- `readings` (sensor history)
- `dose_events` (new, clean state)
- `settings` (namespace keys persisted)
- `relay_events` (with retry/cache fallback)
- `system_state`, `alerts`, calibration logs

### Next Steps (Recommended)

#### Option A: Fast Simulation (Imbalanced Dosing)
1. Advance system clock (via controller or manual setting)
2. Trigger pH imbalanced dose via API (e.g., 5s pH_UP → pH_DOWN to create a delta)
3. Verify:
   - Dose caps enforced (daily, press, rate)
   - Safety guards (pH high/low, EC bounds)
   - Event logged with deltas + reason
   - No blocked dosing swallowed (endpoint returns full log)

#### Option B: Forensics + Tuning (Today's Real Data)
1. Inspect this morning's sensor drift (pH trend, EC trend)
2. Propose cap adjustments if needed (e.g., daily_dose_ml, press_cap_ml, ph_guard_range)
3. Simulate with tuned caps

### Recommendations for Fresh Chat Session
- Restart PC (as user planned) ✓
- Paste **[HANDOFF PROMPT BELOW]** into new chat
- System is clean and ready for next phase

---

## Handoff Prompt for New Chat

```
## RDWC-v4 Dosing Simulation — Phase 2

**Previous Session Checkpoint** (Dec 15, 2025, b74639c):
- System fully consolidated: charts, relay events, dosing schema, sensor poller
- Database fresh (dose_events table empty, ready for simulation)
- All charts stable, sensors online, relays responsive
- Removed interval stacking, eliminated "closed database" errors
- Deployed & verified on Pi; both services active

**Goal**: Simulate imbalanced dosing scenario to validate safety guards.

**Approach**:
1. Verify current settings/caps (dose limits, pH guard range, EC bounds)
2. Trigger controlled pH imbalance (e.g., pH_UP → pH_DOWN sequence)
3. Confirm:
   - Dose caps enforced (daily_dose, press_cap, rate_limit)
   - Safety blocks logged (pH_guard, EC_guard, stale sensor, ESTOP, etc.)
   - dose_events table captures deltas + reason + blocker
   - API returns full consistent event log (no 3-event drops)

**Success Criteria**:
- ✅ Dose blocked or capped per safety rule
- ✅ Event log shows reason + blocker
- ✅ Repeated API calls return stable count (no jitter)
- ✅ Chart KPIs refresh without lag or duplication

**Files to Monitor**:
- `app/dosing.py` (caps, guards)
- `app/dosing_math.py` (rate calc)
- `app/ph_control.py`, `app/ec_control.py` (controller logic)
- `/api/dose/logs` (event retrieval + endpoint guard)
- Charts: lights_chart.js, circulation_chart.js (persistence verify)

**Quick Verification Commands**:
- `GET /api/relays/status` → confirm estop, mode
- `GET /api/sensors` → confirm online, fresh ts
- `GET /api/dose/logs` → verify event count consistency
- `POST /api/dose/{pump}` → trigger test dose (optionally blocked)

Let's begin with settings snapshot, then simulate.
```
