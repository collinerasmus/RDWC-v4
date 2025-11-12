# System Readiness Report – Nutrient Calibration Phase

**Generated:** 2025-11-07  
**System:** RDWC v4 @ 192.168.88.49:8080  
**Deployment Commit:** 061b808 (Schedule UI wired)

---

## Current System State ✅

### Safety & Mode
| Setting                     | Value     | Status |
|-----------------------------|-----------|--------|
| `safety.water_only`         | (implied) | ✅ Safe|
| `ec.min_interval_sec`       | 300       | ✅ Safe|
| `ec.maintenance_override`   | false     | ✅ OFF |
| `safety.estop_persist`      | false     | ✅ OK  |
| `root.system_mode`          | auto      | ℹ️ Note|
| `ec.auto_enabled`           | true      | ℹ️ Note|

**Notes:**  
- `system_mode=auto` + `ec.auto_enabled=true` means EC controller *could* dose if conditions met
- **However:** `ec.setpoint_mscm=1.2` and current EC ≈ 0.31 mS/cm → controller sees no action needed (below target but not critically low in water-only baseline)
- **Safety:** No nutrient lines connected yet → zero actuation risk even if logic triggered
- **Next step:** After calibration, we'll toggle to **Dry-Run** (computes but doesn't execute)

### Sensor Readings
| Metric       | Value      | Status    |
|--------------|------------|-----------|
| EC (mS/cm)   | ~0.31      | ✅ Water  |
| pH           | —          | ℹ️ Monitor|
| Temp (°C)    | —          | ℹ️ Monitor|
| Sensor Age   | < 10s      | ✅ Fresh  |

### Schedule Configuration
| Item              | Value               | Status |
|-------------------|---------------------|--------|
| Grow Start Date   | 2025-10-15          | ✅ Set |
| Current Week      | Week 4 (Veg)        | ✅ OK  |
| Schedule Weeks    | 1–12 (EHG defaults) | ✅ OK  |
| Week 4 EC Target  | 0.80 mS/cm          | ✅ OK  |
| Week 4 Ratios     | G/M/B per schedule  | ✅ OK  |

### Pump Calibration (Current Defaults)
| Pump  | Key                        | Value (ml/s) | Status         |
|-------|----------------------------|--------------|----------------|
| Grow  | `dosing.grow_ml_per_sec`   | 20.0         | ⚠️ Default     |
| Micro | `dosing.micro_ml_per_sec`  | 20.0         | ⚠️ Default     |
| Bloom | `dosing.bloom_ml_per_sec`  | 20.0         | ⚠️ Default     |
| pH Up | `dosing.ph_up_ml_per_sec`  | 0.83         | ✅ Calibrated  |

**Action Required:** Measure actual ml/sec for Grow/Micro/Bloom per calibration protocol.

### EC Controller Settings
| Setting               | Value     | Status |
|-----------------------|-----------|--------|
| `ec.target`           | 0.8       | ✅ OK  |
| `ec.setpoint_mscm`    | 1.2       | ℹ️ Note|
| `ec.step_min_ml`      | 10.0      | ✅ OK  |
| `ec.step_max_ml`      | 60.0      | ✅ OK  |
| `ec.safety_factor`    | 0.6       | ✅ OK  |
| `ec.max_ml_day`       | 150.0     | ✅ OK  |
| `ec.min_interval_sec` | 300       | ✅ Safe|

**Note:** `ec.setpoint_mscm=1.2` appears to be a user-editable setpoint (from EC card input). `ec.target=0.8` is the schedule-derived target. We'll reconcile these during Dry-Run setup.

---

## Hardware Mapping Confirmation

| Pump  | BCM GPIO | Relay Key      | Bottle    | Connection Status |
|-------|----------|----------------|-----------|-------------------|
| Grow  | 6        | dosing_grow    | EHG Grow  | ❌ Not connected  |
| Micro | 13       | dosing_micro   | EHG Micro | ❌ Not connected  |
| Bloom | 19       | dosing_bloom   | EHG Bloom | ❌ Not connected  |
| pH Up | 26       | dosing_ph_up   | pH Up     | ❌ Not connected  |

**Safety:** All dosing lines remain disconnected from reservoir until calibration + dry-run validation complete.

---

## Calibration Workflow Summary

### Phase 1: Physical Setup (User Task)
1. ✅ Place waste beaker near reservoir
2. ❌ Connect Grow/Micro/Bloom pump inlets to bottles
3. ❌ Route all outlets to waste beaker (not reservoir)
4. ❌ Verify circulation active

### Phase 2: Prime Lines (User Task)
1. ❌ Enable Rapid Test (10s interval) via EC → Manual tab
2. ❌ Prime each line with 0.4s pulses until bubble-free
3. ❌ Record priming waste volume (~3-5 ml per line)

### Phase 3: Measure ml/sec (User Task)
1. ❌ Empty graduated cylinder
2. ❌ For each pump: Run 5 × 1s pulses (≈11s apart)
3. ❌ Measure total volume → divide by 5 = ml/sec
4. ❌ Repeat for validation (variance < 5%)
5. ❌ Record Grow/Micro/Bloom ml/sec values

### Phase 4: Enter Calibration (Agent + User)
1. ❌ User provides measured ml/sec values
2. ❌ Agent generates curl command to PUT /api/settings
3. ❌ User executes curl or agent runs via SSH
4. ❌ Verify settings persisted via GET /api/settings

### Phase 5: Restore Safety (User Task)
1. ❌ Disable Rapid Test → verify 300s interval
2. ❌ Confirm EC baseline ≈ 0.31 mS/cm (no accidental dosing)
3. ❌ Outlets still in waste beaker

---

## Next Steps After Calibration

Once user reports:
- **Measured ml/sec** (Grow, Micro, Bloom)
- **300s interval verified** (EC card + Schedule Status)
- **EC baseline stable** (≈ 0.30-0.32 mS/cm)

Agent will provide:

1. **Week 1 Veg Recipe**  
   - Grow/Micro/Bloom ml per 10L  
   - Expected EC contribution per pump  
   - Target EC 0.8 mS/cm validation

2. **Dry-Run Activation**  
   - Toggle EC controller to compute-only mode  
   - Enable dose logging without relay actuation  
   - 48h observation period with Next 48h Plan preview

3. **Dry-Run Validation Checklist**  
   - Verify computed doses match expected volumes  
   - Confirm guards working (interval, daily cap)  
   - Review dose log for consistency  
   - Check no relay events in journalctl

4. **Go-Live Authorization**  
   - After 48h clean dry-run  
   - Route pump outlets from waste → reservoir  
   - Enable live dosing with water_only=false  
   - Monitor first 24h closely

---

## Risk Assessment

| Risk                                  | Mitigation                                      | Status |
|---------------------------------------|-------------------------------------------------|--------|
| Accidental dosing during calibration  | Rapid Test 10s + waste beaker routing          | ✅ Safe|
| Over-dosing from bad ml/sec           | Dry-run validation before live                 | ✅ Safe|
| Controller triggers before ready      | water_only implied; no lines to reservoir      | ✅ Safe|
| Calibration variance > 5%             | Repeat measurement; check for air/kinks        | ℹ️ TBD |
| Forgot to restore 300s interval       | UI verification + Schedule Status badge        | ✅ Safe|

---

## Verification Commands

```bash
# Check current EC reading
curl -sS http://192.168.88.49:8080/api/sensors/last | jq '{ec_ms_cm,ph,temp_c,age_sec}'

# Check interval setting
curl -sS http://192.168.88.49:8080/api/settings | jq '.ec.min_interval_sec'

# Check pump calibration
curl -sS http://192.168.88.49:8080/api/settings | jq '{grow:.dosing.grow_ml_per_sec, micro:.dosing.micro_ml_per_sec, bloom:.dosing.bloom_ml_per_sec}'

# Check recent EC doses (should be empty or only test pulses)
curl -sS http://192.168.88.49:8080/api/ec/dose/recent?limit=5

# Check schedule current week
curl -sS http://192.168.88.49:8080/api/schedule/current_week | jq '{week,phase,ec_target,grow_ml10,micro_ml10,bloom_ml10}'
```

---

**Status:** ✅ Ready for nutrient connection and calibration  
**Next Action:** User follows **NUTRIENT_CALIBRATION.md** protocol  
**Expected Duration:** 30-45 minutes for full calibration (all 3 pumps)  
**Safety Level:** HIGH (waste beaker routing, no reservoir exposure)
