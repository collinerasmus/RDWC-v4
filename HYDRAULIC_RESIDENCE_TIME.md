# Hydraulic Residence Time (HRT) & Adaptive Dosing Strategy

## System Architecture (RDWC)
```
┌──────────────────────────────────────────────────────────────┐
│  RESERVOIR (100L)                                             │
│  ├─ Dosing injection point (pH/EC)                           │
│  └─ Sensor probe location                                     │
└────┬──────────────────────────────────────────┬──────────────┘
     │                                          │
     ▼ Chiller Loop (5 LPM)                    ▼ Main Circulation (20 LPM)
┌─────────┐                                ┌─────────────┐
│ CHILLER │◄──────────────────────────────►│  GROW POTS  │
│  Pump   │   Single level, gravity return │  (4x pots)  │
└─────────┘                                └──────┬──────┘
     │                                            │
     └──────────── Both return to reservoir ─────┘
```

## Fluid Dynamics Analysis

### 1. **Dose Injection → Reservoir Mixing** (Phase 1: Local Mixing)
- **Injection**: Dose enters reservoir at fixed point
- **Chiller circulation**: 5 LPM × 60s = 300L/hr → reservoir turns over 3x/hr
- **Initial mixing time**: ~20-30 seconds (turbulent chiller return creates local mixing)
- **Observable**: First sensor response spike (partial mixing)

### 2. **Reservoir → System Distribution** (Phase 2: System Circulation)
- **Main pump flow**: 20 LPM (1200 L/hr)
- **Total system volume**: ~100L reservoir + ~20L in pots/lines = 120L total
- **Theoretical HRT**: 120L ÷ 20 LPM = **6 minutes** per complete turnover
- **Observable**: Secondary response as first-pass water returns from pots

### 3. **Complete Equilibration** (Phase 3: Stabilization)
- **Full mixing**: 2-3 complete turnovers = **12-18 minutes**
- **Recommendation**: Wait **2× HRT = 12 minutes** minimum between dose cycles
- **Conservative default**: **15 minutes** (900s) for stable control

## Current Implementation Review

### Existing Settings (app/ph_control.py, app/ec_control.py)
```python
# Current default: 300s (5 minutes)
min_interval = _settings_get_int("dosing.ph_min_interval_s", 300)
min_interval = _settings_get_int("dosing.ec_min_interval_s", 300)
```

**PROBLEM**: 5 minutes < theoretical HRT (6 min), may cause:
- Premature second dose before first fully distributed
- Overshoot/oscillation
- Inaccurate adaptive learning

## Recommended Implementation

### Phase 1: Commissioning Values (Conservative)
```python
# Settings to apply during commissioning
"dosing.ph_min_interval_s": "900"     # 15 min = 2.5× HRT (safe)
"dosing.ec_min_interval_s": "900"     # 15 min = 2.5× HRT (safe)
```

### Phase 2: HRT Calibration Procedure (NEW FEATURE)
Add to `tools/commission.ps1` or new `tools/calibrate_hrt.ps1`:

```powershell
# Measure actual HRT empirically
# 1. Apply known dose of pH Up (e.g., 5ml)
# 2. Record sensor values every 30s for 20 minutes
# 3. Identify:
#    - t1: First response (local mixing complete)
#    - t2: Peak response (first system turnover)
#    - t3: Stabilization (equilibrium reached)
# 4. Set min_interval_s = 2 × t3
```

**Expected observations**:
- t1 ≈ 30-60s (initial spike from chiller mixing)
- t2 ≈ 6-8 min (first pot return)
- t3 ≈ 12-15 min (equilibrium)

### Phase 3: Adaptive Learning Enhancements

#### A. Pulse Dosing Strategy
```python
# In ph_control.py auto_dose_ph_down/up()
# Replace single large dose with pulse series:

def _calculate_pulse_dose(target_delta, max_pulse_ml=2.0):
    """
    Break dose into smaller pulses to observe intermediate responses.
    Max 2ml per pulse allows finer control and response tracking.
    """
    total_needed = estimate_dose_ml(target_delta)  # existing logic
    num_pulses = max(1, int(np.ceil(total_needed / max_pulse_ml)))
    pulse_ml = total_needed / num_pulses
    return {
        "pulse_ml": pulse_ml,
        "num_pulses": num_pulses,
        "total_ml": total_needed,
        "interval_s": 900  # HRT-based spacing
    }
```

#### B. Response Curve Tracking
```python
# New table: dose_response_tracking
CREATE TABLE IF NOT EXISTS dose_response_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dose_event_id INTEGER,  -- FK to dose_events
    elapsed_s INTEGER,      -- Seconds since dose
    ph_value REAL,
    ec_value REAL,
    temp_c REAL,
    phase TEXT,  -- 'local_mixing', 'circulation', 'equilibrium'
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### C. Adaptive Min Interval
```python
def _compute_adaptive_interval(recent_doses_df):
    """
    Analyze last 10 dose cycles to determine optimal interval.
    Look for stabilization time (when std_dev < threshold).
    """
    # Group by dose_event_id, find time to <3% variance
    for event_id in recent_doses_df['dose_event_id'].unique():
        responses = fetch_responses_for_event(event_id)
        stable_time = find_stabilization_point(responses, variance_threshold=0.03)
        if stable_time:
            recommended_intervals.append(stable_time * 2)  # 2× safety factor
    
    # Return median of last 10 successful intervals
    return np.median(recommended_intervals) if recommended_intervals else 900
```

## Implementation Checklist

### Immediate (Before Nutrient Hookup)
- [ ] **Update default min_interval to 900s** in both pH/EC controllers
- [ ] Add setting to UI: "Dose Interval (min)" with explanation
- [ ] Document HRT concept in commissioning guide

### Post-Commissioning (Week 1)
- [ ] **Run HRT calibration procedure** with dye or known dose
- [ ] Measure actual t1, t2, t3 empirically
- [ ] Adjust `min_interval_s` based on measured t3

### Advanced (Future Enhancement)
- [ ] Implement `dose_response_tracking` table
- [ ] Add `/api/ph/dose_response?event_id=<id>` endpoint
- [ ] Build adaptive interval calculation
- [ ] Add UI chart showing dose response curves
- [ ] Implement multi-pulse dosing strategy

## Safety Considerations

### Pulse Dosing Risks
- **Pro**: Finer control, better learning
- **Con**: More relay cycles (wear), more DB writes
- **Mitigation**: Limit to max 3 pulses per cycle, enforce cooldown between pulses

### Overshoot Prevention
```python
# In auto mode, if approaching target:
if abs(current_ph - target_ph) < 0.1:  # Within 0.1 of target
    max_dose_ml = max_dose_ml * 0.5  # Halve dose size (gentle approach)
```

### Emergency Abort
```python
# If response is 3× faster than expected (bad math or leak):
if time_to_response < (expected_hrt / 3):
    trigger_alert("FAST_RESPONSE_DETECTED")
    disable_auto_mode()
```

## Recommended Settings for 100L Reservoir

```json
{
  "general.reservoir_liters": "100",
  "dosing.ph_min_interval_s": "900",
  "dosing.ec_min_interval_s": "900",
  "dosing.ph_pulse_max_ml": "2.0",
  "dosing.ec_pulse_max_ml": "5.0",
  "dosing.enable_adaptive_interval": "false",  // Enable after HRT calibration
  "targets.ph_low": "5.8",
  "targets.ph_high": "6.2",
  "targets.ec_low_mscm": "1.2",
  "targets.ec_high_mscm": "1.8"
}
```

## Validation Tests (Post-Implementation)

### Test 1: Single Dose Response
1. Apply 2ml pH Up manually
2. Record sensor values every 30s for 20 minutes
3. Verify response curve matches HRT model

### Test 2: Auto Mode Stability
1. Enable pH auto mode with target 6.0
2. Monitor for 4 hours
3. Verify no oscillation (overshoot/undershoot cycles)

### Test 3: Interval Compliance
1. Check dose_events table for time gaps
2. Verify all gaps >= min_interval_s
3. Confirm no premature doses

## References
- **Hydraulic Residence Time**: τ = V/Q (volume ÷ flow rate)
- **Plug Flow Reactor**: Ideal for tracer studies
- **PID Tuning**: Dead time = HRT, integral time = 2-3× HRT
- **Mixing Number**: Dimensionless, Re > 4000 for turbulent (achieved with chiller)

---
**Version**: 1.0  
**Date**: 2025-11-09  
**Author**: System commissioning analysis  
**Status**: Ready for implementation review
