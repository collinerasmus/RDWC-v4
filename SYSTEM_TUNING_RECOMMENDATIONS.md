# System Tuning Recommendations – December 18, 2025

## Executive Summary
System has been operating for 24+ hours with mixed results:
- **pH Control**: One aggressive dose (+0.316 pH) exceeded target band significantly
- **EC Control**: Functioning correctly; "dashes" in UI are expected (observation window active)
- **Recommendations**: Tighten safety parameters, implement true micro-dosing, optimize observation windows

---

## 1. pH CONTROL ANALYSIS

### Current State
- **Learned Rate**: 5.465 ml/pH unit (system thinks it needs 5.465ml to raise pH by 1.0)
- **Target Band**: 5.95 - 6.05 (0.1 pH range)
- **Problem Dose**: 0.602ml dose at 18:07 caused +0.316 pH change (from 5.916 → 6.232)
  - Expected change: ~0.11 pH (0.602ml ÷ 5.465 ml/pH)
  - Actual change: **+0.316 pH** (2.9× larger than predicted)
  - **Overshot target by 0.182 pH**

### Root Cause
1. **Learned rate is inaccurate** (5.465 ml/pH is too conservative)
2. **Safety factor of 1.0** provides no cushion for prediction errors
3. **Minimum dose of 0.1ml** is too large for 100L with current chemistry

### Recommended pH Parameters

#### Immediate Changes (Apply via HMI):
```
targets.ph_low: 5.95 (keep)
targets.ph_high: 6.05 (keep)
targets.ph_band: 0.05 (tighten - currently 0.1)

dosing.ph_up_initial_ml: 0.05 (reduce from 0.1)
dosing.ph_up_step_min_ml: 0.03 (reduce from 0.05)
dosing.ph_up_step_max_ml: 0.5 (tighten from 10.0)
dosing.ph_up_safety_factor: 0.5 (reduce from 1.0)
dosing.ph_stabilization_window_s: 300 (increase from 180)
dosing.ph_stabilization_delta_threshold: 0.03 (tighten from 0.05)
dosing.ph_min_interval_s: 300 (reduce from 600 for micro-dosing)
dosing.observe_s_after_dose: 25200 (keep - 7 hours for learner)
dosing.observe_s_after_retry: 300 (increase from 60)
```

#### Explanation:
- **Initial dose 0.05ml**: Start with 50% smaller doses
- **Safety factor 0.5**: Use only 50% of predicted dose to prevent overshoot
- **Tighter stabilization**: Wait 5min with max 0.03 pH drift before dosing
- **Shorter interval (300s)**: Allow micro-corrections every 5min instead of 10min
- **Longer retry wait (300s)**: After a dose, wait longer before re-assessing

---

## 2. EC CONTROL ANALYSIS

### Current State
- **Learned Rate**: ~500 ml/mS·cm (from status data)
- **Target Band**: 1.15 - 1.25 mS/cm (0.1 range)
- **Recent Doses**: 30ml doses (20ml Grow + 10ml Micro for Week 3 schedule)
- **Observation Window**: 600 seconds (10 minutes)

### "Dash" Issue – NOT A BUG
The latest dose showing dashes (ec_after: null) is **expected behavior**:
- Dose executed at 18:07:35
- Post-EC reading scheduled at 18:17:35 (600s later)
- You checked before observation completed
- **No fix needed** – this is intentional design

### Current EC Parameters
```
Current:
- ec_step_ml_min: 5ml
- ec_step_ml_max: 30ml
- ec_safety_factor: 0.6
- ec_min_interval_s: 900s (15 minutes)
- ec_observe_s_after_dose: 600s (10 minutes)
```

### EC Micro-Dosing Research for 100L System

#### Theory:
- **1ml nutrient** in 100L = **0.01% concentration change**
- **Typical EC change**: 0.5-2.0ml nutrient can raise EC by ~0.01-0.02 mS/cm (depends on formula strength)
- **Minimum meaningful dose**: 1-2ml (below this, measurement noise dominates)
- **Micro-dose sweet spot**: 3-7ml every 5-10 minutes

#### Recommended EC Parameters (Micro-Dosing Mode):

```
dosing.ec_step_ml_min: 3 (reduce from 5)
dosing.ec_step_ml_max: 10 (reduce from 30)
dosing.ec_safety_factor: 0.7 (increase from 0.6 for smaller errors)
dosing.ec_min_interval_s: 600 (reduce from 900 - allow 10min intervals)
dosing.ec_observe_s_after_dose: 300 (reduce from 600 - faster feedback)
dosing.ec_max_ml_day: 100 (keep - daily safety cap)
targets.ec_tolerance: 0.05 (keep - tight deadband)
```

#### Rationale:
- **3-10ml range**: Small enough to avoid overshoot, large enough to measure
- **10min intervals**: Fast enough for responsive control, slow enough for mixing
- **5min observation**: Nutrients dissolve quickly; no need to wait 10min
- **Higher safety factor (0.7)**: Smaller doses = less risk, can be more aggressive

---

## 3. MICRO-DOSING STRATEGY COMPARISON

### Option A: Conservative (Recommended for Initial Flower Test)
```
pH:
- Initial: 0.05ml
- Interval: 300s (5min)
- Safety: 0.5× predicted
- Max single: 0.5ml

EC:
- Step range: 3-10ml
- Interval: 600s (10min)
- Safety: 0.7× predicted
- Observe: 300s
```
**Effect**: 2-4 micro-corrections per hour, very gentle, minimal overshoot risk

### Option B: Aggressive (Once System Learns Rates)
```
pH:
- Initial: 0.03ml
- Interval: 180s (3min)
- Safety: 0.6× predicted
- Max single: 0.3ml

EC:
- Step range: 2-7ml
- Interval: 300s (5min)
- Safety: 0.8× predicted
- Observe: 180s
```
**Effect**: 4-8 micro-corrections per hour, ultra-responsive, requires accurate learned rates

**Recommendation**: Start with Option A. After 48 hours with no overshoots, consider Option B.

---

## 4. FLOWER CYCLE TEST PLAN

### Objective
Validate Week 4-12 nutrient ratios under bloom schedule (12/12 light cycle).

### Setup Checklist
1. **Change grow start date** to set system to Week 4 (Transition):
   - Current: `2025-11-24` (Week 3: Veg 7/7/7)
   - New: `2025-11-10` (Week 4: Transition 20/10/0)
   
2. **Apply conservative micro-dosing parameters** (Option A above)

3. **Switch light schedule** to 12/12 (if not already):
   - `general.lights_on_time`: 06:00
   - `general.lights_duration_hours`: 12

4. **Verify pump calibration** hasn't drifted:
   ```
   dosing.grow_ml_per_sec: 1.020
   dosing.micro_ml_per_sec: 1.020
   dosing.bloom_ml_per_sec: 1.020
   ```

### Expected Behavior
- **Week 4**: 20ml Grow, 10ml Micro, 0ml Bloom per 10L = 200/100/0 for 100L full tank dose
- **Week 8** (Peak Bloom): 0/10/20 ratio = 0/100/200 for 100L
- **Doses should split correctly** across 3 pumps based on schedule ratios
- **First dose after change**: Verify UI shows correct pump breakdown

### Monitoring Points
- [ ] First EC dose after grow_start_date change shows 20:10:0 ratio
- [ ] pH stays within 5.95-6.05 with no overshoots >0.15 pH
- [ ] EC doses are 3-10ml (not 30ml) per event
- [ ] Dose intervals are consistent (pH ~5min, EC ~10min)
- [ ] No guard blocks except interval guard (expected behavior)

### Test Duration
- **Minimum**: 48 hours (capture ~60-80 dose events)
- **Ideal**: 7 days (covers Week 4 → Week 5 transition)

---

## 5. SINGLE SOURCE OF TRUTH – CURRENT STATE

### Dose Logging Architecture (Verified)
```
pH Doses:
  ✓ Write to: ph_dose_log (detailed history with post_ph)
  ✓ Write to: dose_events (unified UI totals)
  ✓ API reads: ph_dose_log
  ✓ Status: CORRECT

EC Doses:
  ✓ Write to: ec_dose_log (detailed history with post_ec)
  ✓ Write to: dose_events (unified UI totals)
  ✓ API reads: MERGED (ec_dose_log + dose_events)
  ✓ Status: CORRECT (as of commit 886fa11)
```

### No Duplicates, No Manual DB Scripts
- All dose writes go through controller endpoints
- All API reads use defined helper functions
- No raw SQL in UI code
- No manual DB manipulation required

---

## 6. ACTION PLAN (DO THIS NOW)

### Step 1: Apply Conservative Micro-Dosing Parameters (5 minutes)
Via HMI Settings page, update these 13 parameters:

**pH Section** (7 parameters):
```
targets.ph_band → 0.05
dosing.ph_up_initial_ml → 0.05
dosing.ph_up_step_min_ml → 0.03
dosing.ph_up_step_max_ml → 0.5
dosing.ph_up_safety_factor → 0.5
dosing.ph_stabilization_window_s → 300
dosing.ph_stabilization_delta_threshold → 0.03
dosing.ph_min_interval_s → 300
dosing.observe_s_after_retry → 300
```

**EC Section** (4 parameters):
```
dosing.ec_step_ml_min → 3
dosing.ec_step_ml_max → 10
dosing.ec_min_interval_s → 600
dosing.ec_observe_s_after_dose → 300
```

### Step 2: Switch to Week 4 Schedule (2 minutes)
```
general.grow_start_date → 2025-11-10
```
Expected result: Current week changes from 3 to 4, next dose uses 20/10/0 ratio.

### Step 3: Verify First Doses (15 minutes after change)
- Wait for next auto EC dose
- Check dose log shows: Grow ~20ml, Micro ~10ml, Bloom 0ml (scaled to actual need)
- Check pH dose is 0.03-0.05ml range

### Step 4: Monitor for 48 Hours
- Check every 12 hours for overshoots
- If pH exceeds 6.15 at any point, further reduce safety_factor to 0.4
- If EC overshoots by >0.1 mS/cm, reduce ec_safety_factor to 0.6

### Step 5: Document Results
After 48h, review:
- pH dose log: Count overshoots (target <5% of doses exceed band by >0.1)
- EC dose log: Count overshoots (target <5% exceed band by >0.05)
- System stability: Both parameters should stay in-band >90% of time

---

## 7. RISK ASSESSMENT

### Low Risk Changes ✅
- Reducing initial dose sizes (0.1 → 0.05ml pH, 5 → 3ml EC)
- Tightening stabilization thresholds
- Reducing safety factors

### Medium Risk Changes ⚠️
- Shortening pH interval from 600s → 300s (more frequent dosing)
- Shortening EC observation from 600s → 300s (faster feedback)
- **Mitigation**: Daily caps remain in place (50ml pH, 100ml EC)

### No Risk ✅
- Changing grow_start_date (only affects ratio calculation)
- Current architecture (verified single source of truth)

---

## APPENDIX A: Current Learned Rates

```
pH: 5.465 ml/pH (SUSPECT - caused overshoot)
EC: ~500 ml/mS·cm (REASONABLE)

After 48h with new parameters:
- pH learner will re-converge (expect 2-3 ml/pH with safety factor 0.5)
- EC learner will adjust for smaller doses (expect 400-600 ml/mS·cm)
```

---

## APPENDIX B: Quick Reference – What to Watch

**Good Dose (pH)**:
- 0.03-0.08ml volume
- +0.04 to +0.08 pH change
- Lands within 5.95-6.05 band

**Bad Dose (pH)**:
- >0.15ml volume
- >0.15 pH change
- Exceeds 6.10

**Good Dose (EC)**:
- 3-10ml total volume
- +0.02 to +0.05 mS/cm change
- Lands within 1.15-1.25 band

**Bad Dose (EC)**:
- >15ml volume (unless very low EC)
- >0.08 mS/cm change
- Exceeds 1.30

---

**End of Recommendations**  
Apply Option A parameters now, switch to Week 4, monitor for 48h, then reassess.
