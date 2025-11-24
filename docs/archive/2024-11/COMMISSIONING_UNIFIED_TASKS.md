# RDWC-v4 Unified Commissioning Task List

Single source of truth for remaining commissioning + verification work. All prior scattered docs (COMMISSIONING_RUNBOOK.md, PI_COMMISSIONING_CHECKLIST.md, FINAL_VERIFICATION.md, docs/COMMISSIONING_AUTOMATION.md, assorted PR task lists) converge here. Keep changes minimal; update THIS file only for task state.

## Guiding Principles
- Safety first (E-STOP, interlocks, dosing guards) must remain green before functional tests.
- Edge-only scheduling (lights) – no periodic catch-up loops.
- No duplicate UI controls (single global E-STOP; mode buttons only on System tab).
- All sensors fresh (<60s) and stable before dosing or calibration steps.
- Persistence: settings writes reflected in SQLite and retrievable via API.

## Acceptance Criteria Snapshot
| Area | Criteria |
|------|----------|
| Relays / Interlocks | Chiller only runs with main + chiller pumps; auto-remediation active; estop=false unless toggled intentionally |
| Sensors | `/api/sensors` online=true; `ts` age <60s; temp compensation throttled as designed |
| pH | Stable read within target range OR calibration buffer ±0.05 during calibration |
| EC | Low (1413) calibration accepted; status shows completed step |
| Dosing Pumps | Each calibrated rate >0 ml/s; safety blocks enforced (caps, guards) |
| Lights Schedule | Exactly two edges per day; no phantom 00:00 edge on spanning windows |
| Hysteresis (Chiller) | Updated hysteresis value persists across API reads & restart |
| Relay POST | `/relay/set` responds <2s; no timeout errors |
| Documentation | Unified; no conflicting commissioning instructions |
| Reports | Commissioning summary JSON generated & archived |

## Task Categories
1. Baseline Validation
2. Persistence & Configuration
3. Scheduling & Edge Logic
4. Performance / Latency
5. Safety & Interlocks
6. Calibration & Dosing
7. Documentation Consolidation
8. Final Verification & 24h Soak Prep

## Detailed Tasks
### 1. Baseline Validation
- [ ] Fetch full `/api/chiller/status` (raw) – confirm `interlock_ok`, `interlock_details` present.
- [ ] Snapshot: `/api/relays/status`, `/api/controllers/status`, `/api/estop`, `/api/version`.
- [ ] Run targeted pytest suites: `tests/test_chiller_interlock.py`, `tests/test_scheduler_midnight.py`.

### 2. Persistence & Configuration
- [ ] Reproduce hysteresis update (POST new value) – verify DB key in `settings` table.
- [ ] Patch hysteresis persistence if key mismatch (minimal diff). 
- [ ] Confirm settings sync after service restart.

### 3. Scheduling & Edge Logic
- [ ] Inspect lights schedule across midnight (current config) – list planned edges next 48h.
- [ ] Verify no 00:00 phantom OFF when ON spans midnight.
- [ ] Confirm only edge triggers cause relay changes (audit logs / tests).

### 4. Performance / Latency
- [ ] Measure 5 sequential `/relay/set` calls; record mean/95th percentile latency.
- [ ] If >2s or error: inspect `RequestAuditMiddleware` body consumption.
- [ ] Patch or open tracking item (only if non-trivial) – include root cause summary.

### 5. Safety & Interlocks
- [ ] Force main pump OFF while chiller running – confirm auto-shutdown behavior.
- [ ] AUTO mode: enable main pump; verify chiller pump auto-start remediation.
- [ ] Violation simulation: manually toggle chiller pump OFF (if possible) – ensure remediation.

### 6. Calibration & Dosing
- [ ] pH read stabilization test – confirm lock usage and stable value.
- [ ] EC low calibration (if not already) – verify status endpoint.
- [ ] Dosing pumps prime/run/commit – log rates >0; safety guard checks present.

### 7. Documentation Consolidation
- [ ] Mark superseded commissioning docs: add header pointing to this file.
- [ ] Remove duplicate task lists from PR descriptions (reference this file instead).
- [ ] Update `AS_BUILT_DOCUMENTATION_INDEX.md` to link only to unified tasks.

### 8. Final Verification & 24h Soak Prep
- [ ] Generate commissioning report JSON + summary.
- [ ] Begin 24h soak: monitor sensor freshness, interlock state, dosing inactivity (unless testing dosing).
- [ ] End-of-soak snapshot JSON (same fields as baseline + anomalies).

## Status Update (2025-11-23)
✅ **All Prior PRs Closed** - Work merged to main
- PR #72 (UI cleanup & interlock) – CLOSED, superseded  
- PR #75 (midnight schedule fix) – CLOSED, merged via PR #77
- PR #77 (WIP rollout) – COMPLETED & MERGED (interlock status, midnight tests, relay timeout investigation)

**Current Main Branch:** 6d2412a
- Interlock status API working (`interlock_ok`, `interlock_details`)
- Midnight schedule tests passing (7/7)
- Chiller input focus fix deployed
- All 16 new tests passing

**You are working with this agent** - No separate GA session open.

## Unified Command Reference
```powershell
# Baseline snapshot
$base='http://192.168.88.49:8080'
Invoke-RestMethod "$base/api/version"
Invoke-RestMethod "$base/api/estop"
Invoke-RestMethod "$base/api/relays/status"
Invoke-RestMethod "$base/api/chiller/status"

# Tests
pytest tests/test_chiller_interlock.py -q
pytest tests/test_scheduler_midnight.py -q

# Hysteresis update (example; adjust value)
Invoke-RestMethod -Method POST -Uri "$base/api/chiller/hysteresis" -Body (@{value=1.5} | ConvertTo-Json) -ContentType 'application/json'
Invoke-RestMethod "$base/api/chiller/status" | Select-Object hysteresis

# Relay latency sample
Measure-Command { Invoke-RestMethod -Method POST -Uri "$base/relay/set" -Body (@{relay='main_pump'; on=$true} | ConvertTo-Json) -ContentType 'application/json' }
```

## Change Control
- Only update this file for task additions/completions.
- Keep diffs minimal; remove tasks only when completed or superseded.

## Next Immediate Actions
1. Confirm chiller status fields.
2. Run targeted tests.
3. Reproduce hysteresis persistence.

---
Updated: 2025-11-23
