# Nutrient Pump Calibration & Connection Protocol

**Status:** Ready for hardware connection  
**Date:** 2025-11-07  
**System State:** Water-only preview mode, EC interval 300s, Schedule seeded with 12-week EHG defaults

---

## Pre-Flight Checklist

✅ Schedule backend operational (nutrient_schedule table seeded)  
✅ EC controller safety guards verified (min interval, daily cap, stale sensor)  
✅ Rapid Test helper verified (10s ↔ 300s flip functional)  
✅ All relays safe-off; E-STOP inactive  
✅ Sensor poller active; EC ≈ 0.31 mS/cm (water baseline)  
✅ Timeline UI shows "WE ARE HERE" on Week 4 Veg  

---

## Hardware Mapping Confirmation

| Pump  | BCM GPIO | Relay Position | Nutrient Bottle | Status       |
|-------|----------|----------------|-----------------|--------------|
| Grow  | 6        | dosing_grow    | EHG Grow        | Not connected|
| Micro | 13       | dosing_micro   | EHG Micro       | Not connected|
| Bloom | 19       | dosing_bloom   | EHG Bloom       | Not connected|
| pH Up | 26       | dosing_ph_up   | pH Up           | Not connected|

**Note:** pH Up remains disconnected until EC calibration complete.

---

## Step 1: Physical Connection

### 1.1 Prepare Waste Collection
- [ ] Place a **500 ml graduated beaker** or measuring cup labeled "WASTE" near the reservoir
- [ ] Have paper towels ready for spill cleanup
- [ ] Ensure good lighting for reading volume markings

### 1.2 Connect Dosing Lines
- [ ] Insert **Grow pump** inlet into EHG Grow bottle
- [ ] Insert **Micro pump** inlet into EHG Micro bottle  
- [ ] Insert **Bloom pump** inlet into EHG Bloom bottle
- [ ] Route all three **outlets into the WASTE beaker** (not reservoir)
- [ ] Secure lines with tape or clips to prevent movement during priming

### 1.3 Verify Circulation
- [ ] Main pump ON (circulation active)
- [ ] Chiller pump state per current mode
- [ ] Water level stable in reservoir

---

## Step 2: Prime Dosing Lines

**Goal:** Remove all air bubbles from tubing before calibration measurements.

### 2.1 Enable Rapid Test Mode
1. Open browser → navigate to **EC tab**
2. Expand **Manual** sub-tab
3. Enable **Rapid Test Mode** (10s interval)
4. Verify interval display shows **10s** in EC card header

### 2.2 Prime Each Line
For **each pump** (Grow, Micro, Bloom):

1. Click the **0.4s** quick pulse button
2. Watch the outlet in the waste beaker
3. Repeat 0.4s pulses until:
   - Liquid flows continuously (no sputtering)
   - No visible air bubbles in tubing
   - Outlet stream is steady
4. Record approximate priming volume used (ml)

**Expected:** 3-5 pulses per line, ~2-4 ml total priming waste per pump.

### 2.3 Safety Verification
- [ ] No spills or leaks
- [ ] All three lines primed and bubble-free
- [ ] Waste beaker contents < 15 ml total
- [ ] Pumps respond instantly to button presses

---

## Step 3: Calibration Measurement

**Goal:** Measure ml/sec for each pump with ±5% accuracy.

### 3.1 Setup
- [ ] Empty and dry the graduated cylinder
- [ ] Place cylinder on flat, stable surface
- [ ] Ensure outlet tube is secure inside cylinder (won't jump out)
- [ ] Have stopwatch or phone timer ready (optional; UI countdown visible)

### 3.2 Calibration Run (per pump)

**Protocol:**  
1. Click **1.0s** pulse button
2. Wait for countdown (≈11s with 10s interval)
3. Repeat **5 times total** (5 × 1s pulses)
4. Read total volume in cylinder to nearest 0.5 ml

**Example:**  
- 5 pulses × 1s each  
- Total volume measured: **126 ml**  
- **ml/sec = 126 / 5 = 25.2 ml/s**

### 3.3 Repeat for Validation
- [ ] Empty cylinder
- [ ] Repeat 5-pulse sequence
- [ ] Compare second measurement to first
- [ ] If difference > 5%, investigate (air, inconsistent flow, etc.)

### 3.4 Record Results

| Pump  | Run 1 (ml) | Run 2 (ml) | Average (ml) | ml/sec   | Variance |
|-------|------------|------------|--------------|----------|----------|
| Grow  | ____       | ____       | ____         | ______   | _____%   |
| Micro | ____       | ____       | ____         | ______   | _____%   |
| Bloom | ____       | ____       | ____         | ______   | _____%   |

**Acceptance Criteria:**  
- Variance between runs < 5%  
- ml/sec values in range 20–30 ml/s (typical for peristaltic pumps at this duty cycle)

---

## Step 4: Enter Calibration Values

### 4.1 Current Method (API Direct)
Since pump calibration UI fields are not yet in Settings → Calibration, use the API:

```bash
# Via SSH or local terminal
curl -X PUT http://192.168.88.49:8080/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "dosing.grow.ml_per_sec": 25.2,
    "dosing.micro.ml_per_sec": 24.8,
    "dosing.bloom.ml_per_sec": 25.5
  }'
```

**Replace values with your measured ml/sec from Step 3.**

### 4.2 Verify Settings Persisted
```bash
curl -sS http://192.168.88.49:8080/api/settings | grep -E "dosing\.(grow|micro|bloom)\.ml_per_sec"
```

Expected output:
```json
{"key": "dosing.grow.ml_per_sec", "value": "25.2"},
{"key": "dosing.micro.ml_per_sec", "value": "24.8"},
{"key": "dosing.bloom.ml_per_sec", "value": "25.5"}
```

---

## Step 5: Restore Safe Interval

### 5.1 Disable Rapid Test Mode
1. Return to **EC → Manual** tab
2. **Uncheck** Rapid Test Mode checkbox
3. Verify interval display shows **300s**

### 5.2 Confirm in Multiple Locations
- [ ] EC card header: `ec.min_interval_sec: 300`
- [ ] Schedule → Status & Safety card: `EC Interval: 300s`
- [ ] Settings table query (optional):
  ```bash
  curl -sS http://192.168.88.49:8080/api/settings | grep "ec.min_interval_sec"
  # Expected: {"key": "ec.min_interval_sec", "value": "300"}
  ```

---

## Step 6: Safety Post-Check

- [ ] All pump outlets **still in waste beaker** (not reservoir)
- [ ] No nutrient has entered main reservoir yet
- [ ] EC reading still ≈ 0.30–0.32 mS/cm (water baseline)
- [ ] safety.water_only = true in database
- [ ] E-STOP inactive; system mode Manual

---

## Next Phase: Week 1 Veg Recipe & Dry-Run

Once calibration complete, reply with:

1. **Measured ml/sec values** (Grow, Micro, Bloom)
2. **Interval verification** (300s shown in EC card + Schedule Status)
3. **EC baseline reading** (to confirm no accidental dosing)

Then I will provide:
- **Week 1 Veg EHG recipe** (ml/10L → EC target 0.8 mS/cm)
- **EC controller Dry-Run activation** (computes + logs doses without actuating)
- **48h validation checklist** before Live mode

---

## Troubleshooting

**Issue:** Pump doesn't respond to button press  
→ Check relay wiring (BCM GPIO vs physical pin)  
→ Verify E-STOP inactive, mode Manual  
→ Check browser console for errors  

**Issue:** Inconsistent flow rates (variance > 5%)  
→ Re-prime line completely  
→ Check for kinks or restrictions in tubing  
→ Verify bottle is not empty  

**Issue:** Can't restore 300s interval  
→ Refresh page and re-verify Rapid Test checkbox  
→ Manually PUT via API if UI fails  
→ Check browser console for settings.js errors  

**Issue:** Calibration values don't persist  
→ Verify settings.db is writable (not read-only)  
→ Check journalctl for PUT /api/settings errors  
→ Confirm settings keys match exactly (case-sensitive)

---

**Safety Reminder:**  
Nutrients remain in waste beaker until Dry-Run validation complete (24-48h). Do not route to reservoir until green-lit.
