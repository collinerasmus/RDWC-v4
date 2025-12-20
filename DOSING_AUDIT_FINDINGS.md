# RDWC pH Dosing System Audit — Settings & Logic Duplication

## Critical Issues Found

### 1. **out_of_band Guard Logic Is Backwards**
**Location:** `app/ph_control.py:403-433`
**Problem:** The guard triggers when pH **was recently** outside the band (e.g., < 6.1), blocking dosing for 300s even though pH needs to rise. This is inverted logic.
**Expected:** Should only block when pH recently **entered** the band (to allow stabilization after reaching setpoint).
**Impact:** Stops all auto-dosing when pH is below target.

### 2. **out_of_band Guard Not Checked in Auto Loop**
**Location:** `app/ph_control.py:1356-1420`
**Problem:** Auto loop checks estop, reservoir, safe_off, ec_baseline_low, ec_settle, daily_cap, interval—but **not** out_of_band. Yet `_compute_guards()` returns it, and it's shown in `/api/ph/status`.
**Impact:** Inconsistent guard enforcement; UI shows guard active but loop doesn't respect it (in this case, that's good because the logic is broken).

### 3. **Duplicate Target Fetching Logic (3+ places)**
**Locations:**
- `ph_control.py:408-409` in `_last_out_of_band_ts()`
- `ph_control.py:530-531` in `ph_status()` (with schedule fallback)
- `ph_control.py:1224-1256` in `_auto_loop()` (with schedule fallback)
- `ph_control.py:1294-1295` in retry logic

**Problem:** Same nutrient_schedule + settings fallback repeated 3 times; not extracted to helper.
**Impact:** Maintenance burden; inconsistency if one copy is updated.

### 4. **Duplicate Stabilization Settings**
**Locations:**
- `ph_control.py:427` uses `dosing.ph_stabilization_window_s` (default 180)
- `ph_control.py:572` uses `dosing.ph_stabilization_window_s` OR fallback `dosing.stabilize_wait_s` (default 180)
- `ph_control.py:669` same fallback pattern
**Problem:** Legacy `dosing.stabilize_wait_s` still referenced; canonical key is `dosing.ph_stabilization_window_s`.
**Impact:** Confusion; two keys for same setting.

### 5. **Duplicate EC Compensation Logic**
**Locations:**
- `ph_control.py:844-866` `_ec_compensated_ml_per_pH()` helper inside `_perform_dose`
- `ph_control.py:1402-1414` inline re-implementation in `_auto_loop`
**Problem:** Same formula coded twice; not DRY.
**Impact:** If tuning needed, must update both.

### 6. **Duplicate Max Estimated Change Setting**
**Locations:**
- `ph_control.py:569` uses `dosing.ph_max_predicted_delta_ph` OR fallback `safety.max_estimated_ph_change` (default 0.5)
- `ph_control.py:874` uses `safety.max_estimated_ph_change` only
**Problem:** Two keys for same guard; canonical unclear.
**Impact:** User sets one, system may read other.

### 7. **Hardcoded Defaults Everywhere**
**Examples:**
- `dosing.ph_up_ml_per_sec` default 25.0 in code vs 0.758 in settings.py
- `dosing.ph_min_interval_s` default 900 vs 120 in settings.py
- `targets.ph_low` 5.8 hardcoded in ~5 places

**Problem:** Defaults in `settings.py` not enforced at read time; code has its own fallbacks.
**Impact:** Settings changes don't take effect unless DB has value.

### 8. **Guard Check Duplication**
**Locations:**
- `_compute_guards()` computes all guards
- `_perform_dose()` re-checks maintenance_override and allow_force, selectively bypasses
- Auto loop manually checks each guard one-by-one
**Problem:** Guard evaluation logic not centralized.
**Impact:** Hard to audit which guards apply when.

### 9. **Holding Reason Derivation Issues**
**Location:** `ph_control.py:585-596` `_derive_holding_reason()`
**Problem:**
- Returns `out_of_band` if pH outside targets (correct)
- Returns `ph_stable` if inside (correct)
- But doesn't account for other guards (ec_settle, interval, etc.)
- Status endpoint line 557 adds `auto_disabled` and `cooldown` after the fact
**Impact:** Holding reason incomplete; doesn't reflect all blocks.

### 10. **Maintenance Override Bypass Incomplete**
**Location:** `ph_control.py:935-945`
**Problem:** Bypass allows skipping `interval` and `daily_cap`, but **not** `out_of_band`, `ec_settle`, or `ec_baseline_low`.
**Impact:** Even with override, auto loop may still be blocked by ec_settle or out_of_band.

---

## Recommendations

### Immediate Fixes (High Priority)
1. **FIX out_of_band logic:** Change condition to only block when pH recently **entered** the band from below (i.e., `ph >= low AND since_last_oob < stabilize_wait_s`).
2. **Remove out_of_band from guards:** Or clarify its purpose and enforce it in auto loop.
3. **Extract target resolution to helper:** `_get_ph_targets() -> dict` with schedule fallback.
4. **Consolidate EC compensation:** Move to module-level helper callable from both places.
5. **Single max estimated change key:** Choose `dosing.ph_max_predicted_delta_ph` as canonical; deprecate `safety.max_estimated_ph_change`.

### Medium-Term Refactors
6. **Settings layer enforcement:** Make `_settings_get_*` use `settings.py` defaults if DB is None.
7. **Guard evaluation unification:** `_should_dose(guards, override_flags) -> (bool, reason)` callable by both auto loop and manual dose.
8. **Holding reason completeness:** `_derive_holding_reason()` should check all active guards and return first blocker.

### Long-Term Improvements
9. **Frontend settings editor:** Reflect canonical keys only; hide legacy aliases.
10. **Audit EC control:** Likely has similar duplication patterns.
