# Hot Commissioning Runbook — RDWC v4

**Purpose**: Prove the system with real nutrients, validate EC rise, and establish baseline operation.

## Pre-Requisites
- ✓ Dry run audit passed (`python tools/system_audit.py`)
- ✓ All relays verified (ok_all=true)
- ✓ Service running and stable
- ✓ Pumps primed with water (air removed from tubing)

---

## Phase 1: Sensor Calibration (30 min)

### 1.1 Fill Reservoir
- Add **clean water** to reservoir (target: 20-25L)
- Start main circulation pump: 
  ```
  curl -X POST http://192.168.88.49:8080/api/relay/main_pump/toggle -H "Content-Type: application/json" -d '{"on":true}'
  ```
- Let circulate for 5 minutes

### 1.2 Calibrate pH Sensor
1. Open dashboard → Sensors tab
2. Prepare pH 7.0 calibration solution
3. Place pH probe in solution (wait 60s for stable reading)
4. Click "Calibrate pH Mid" (stores 7.0 reference)
5. Rinse probe, place in pH 4.0 solution
6. Click "Calibrate pH Low" (stores 4.0 reference)
7. Rinse probe, return to reservoir
8. Verify reading stabilizes at ~7.0 (tap water baseline)

### 1.3 Calibrate EC Sensor
1. Prepare EC 1.413 mS/cm calibration solution (1413 µS/cm)
2. Place EC probe in solution (wait 60s)
3. Click "Calibrate EC"
4. Rinse probe, return to reservoir
5. Verify reading shows <0.5 mS/cm (tap water baseline)

### 1.4 RTD (Temperature)
- No calibration needed (factory calibrated PT-1000)
- Verify reading is reasonable (18-25°C ambient)

---

## Phase 2: Pump Calibration (20 min)

### Goal: Establish mL/second flow rate for each pump

### 2.1 Micro Pump
1. Place pump inlet in **water** (not nutrients yet)
2. Place outlet in graduated cylinder
3. Run 5-second dose:
   ```
   curl -X POST http://192.168.88.49:8080/api/dose/micro \
     -H "Content-Type: application/json" \
     -d '{"seconds": 5, "reason": "calibration", "actor": "commissioning"}'
   ```
4. Measure volume collected (e.g., 8 mL)
5. Calculate flow rate: `8 mL / 5s = 1.6 mL/s`
6. Update settings → `dosing.micro_ml_per_sec` = 1.6
7. Repeat for accuracy (3 trials, average)

### 2.2 Grow Pump
- Repeat 2.1 for Grow pump
- Update `dosing.grow_ml_per_sec`

### 2.3 Bloom Pump
- Repeat 2.1 for Bloom pump
- Update `dosing.bloom_ml_per_sec`

### 2.4 pH Up Pump
- Repeat 2.1 for pH Up pump
- Update `dosing.ph_up_ml_per_sec`

**Save calibration results** in settings or `CALIBRATION_LOG.md`

---

## Phase 3: Baseline EC Test (15 min)

### Goal: Prove nutrient dosing raises EC measurably

### 3.1 Record Initial State
```bash
curl -s http://192.168.88.49:8080/sensors/read | jq '{ph, ec_ms_cm, temp_c}'
```
Example output:
```json
{
  "ph": 7.02,
  "ec_ms_cm": 0.35,
  "temp_c": 21.4
}
```
**Record baseline EC** (e.g., 0.35 mS/cm)

### 3.2 Add Small Nutrient Dose
Goal: Add ~1 mL of Micro nutrient (low risk test)

Using calibrated flow rate (e.g., 1.6 mL/s for 1 mL → 0.625s):
```bash
curl -X POST http://192.168.88.49:8080/api/dose/micro \
  -H "Content-Type: application/json" \
  -d '{"seconds": 0.625, "reason": "baseline_test", "actor": "commissioning"}'
```

### 3.3 Wait & Verify EC Rise
1. Wait 60 seconds for mixing
2. Read sensors again:
   ```bash
   curl -s http://192.168.88.49:8080/sensors/read | jq '{ph, ec_ms_cm, temp_c}'
   ```
3. **Expected**: EC should rise by ~0.05-0.15 mS/cm
4. If EC unchanged: check pump tubing, sensor calibration, mixing

### 3.4 Record Result
```
Baseline EC:    0.35 mS/cm
Post-dose EC:   0.42 mS/cm  
Delta:          +0.07 mS/cm ✓
```

✓ **PASS**: System can dose and detect EC change  
✗ **FAIL**: Troubleshoot sensor or pump

---

## Phase 4: Operational Validation (30 min)

### 4.1 Chiller Auto Mode
1. Set temperature target (e.g., 20°C):
   ```bash
   curl -X POST http://192.168.88.49:8080/api/chiller/settings \
     -H "Content-Type: application/json" \
     -d '{"target_temp": 20.0, "hysteresis": 1.0}'
   ```
2. Enable auto mode:
   ```bash
   curl -X POST http://192.168.88.49:8080/api/chiller/auto/enable
   ```
3. Monitor status:
   ```bash
   curl -s http://192.168.88.49:8080/api/chiller/status | jq
   ```
4. If temp > 21°C, chiller should engage within 60s
5. Verify chiller_power relay turns ON when temp exceeds threshold

### 4.2 Lights Schedule
1. Set lights schedule (e.g., ON at 20:00 for 16h):
   ```bash
   curl -X PUT http://192.168.88.49:8080/settings \
     -H "Content-Type: application/json" \
     -d '{"lights.start_time": "20:00", "lights.duration_hours": 16}'
   ```
2. Verify schedule applied:
   ```bash
   curl -s http://192.168.88.49:8080/settings | jq '{lights}'
   ```
3. If current time is within schedule window, lights should be ON
4. Test manual override:
   ```bash
   curl -X POST http://192.168.88.49:8080/api/relay/lights/toggle \
     -H "Content-Type: application/json" \
     -d '{"on": false}'
   ```
5. Lights should turn OFF (override active)

### 4.3 E-Stop Test
1. Engage E-Stop:
   ```bash
   curl -X POST http://192.168.88.49:8080/api/estop \
     -H "Content-Type: application/json" \
     -d '{"active": true}'
   ```
2. Verify all relays forced OFF:
   ```bash
   curl -s http://192.168.88.49:8080/api/relays/status | jq '.relays[] | select(.is_on == true)'
   ```
   (Should return empty—all OFF)
3. Try to turn relay ON (should block):
   ```bash
   curl -X POST http://192.168.88.49:8080/api/relay/main_pump/toggle \
     -H "Content-Type: application/json" \
     -d '{"on": true}'
   ```
   (Should return error/block message)
4. Release E-Stop:
   ```bash
   curl -X POST http://192.168.88.49:8080/api/estop \
     -H "Content-Type: application/json" \
     -d '{"active": false}'
   ```

---

## Phase 5: Production Readiness Checklist

- [ ] Sensors calibrated and readings stable
- [ ] All pumps calibrated (mL/s recorded)
- [ ] EC rise test passed (+0.05 mS/cm minimum)
- [ ] Chiller auto mode engages/disengages correctly
- [ ] Lights schedule ON/OFF edges working
- [ ] E-Stop blocks all relay control
- [ ] Guard integrity check passes (ok_all=true, anomalies=0)
- [ ] No ERROR/Traceback lines in logs for 10 minutes
- [ ] Dashboard relay toggles responsive (<200ms latency)

---

## Production Operations

### Daily Monitoring
```bash
# Check sensor readings
curl -s http://192.168.88.49:8080/sensors/read | jq

# Check relay status
curl -s http://192.168.88.49:8080/api/relays/status | jq '.relays | to_entries[] | select(.value.is_on == true) | .key'

# Check guard anomalies
curl -s http://192.168.88.49:8080/api/relays/guard/status | jq '.anomalies.count'

# Check service health
curl -s http://192.168.88.49:8080/api/health | jq '.ok, .uptime_seconds'
```

### Manual Dosing (Example: 5 mL Micro)
```bash
# Calculate seconds (5 mL / 1.6 mL/s = 3.125s)
curl -X POST http://192.168.88.49:8080/api/dose/micro \
  -H "Content-Type: application/json" \
  -d '{"seconds": 3.125, "reason": "manual_adjust", "actor": "operator"}'
```

### Viewing Dose History
```bash
curl -s http://192.168.88.49:8080/api/dose/history?limit=20 | jq
```

### Emergency: Immediate All-Off
```bash
# Use E-Stop
curl -X POST http://192.168.88.49:8080/api/estop -H "Content-Type: application/json" -d '{"active": true}'

# Or restart service (triggers safe-off script)
ssh pi@192.168.88.49 'sudo systemctl restart rdwc.service'
```

---

## Troubleshooting

### EC not rising after dose
- Check pump tubing connections
- Verify pump inlet in nutrient solution
- Re-calibrate EC sensor
- Increase dose amount (try 2 mL)

### Sensor readings stale
- Check I2C bus: `sudo i2cdetect -y 1`
- Expected: 0x63 (pH), 0x64 (EC), 0x66 (RTD)
- Restart service if sensors not detected

### Relay not responding
- Check guard status: `/api/relays/guard/status`
- Check recent events: `/api/relays/guard/recent?limit=10`
- Look for `coerced: true` (hardware mismatch)
- Verify GPIO wiring: BCM pin assignments

### High anomaly count
- Check `/api/relays/guard/status` → `anomalies.anomalies`
- Common causes: loose wiring, power supply sag, EMI
- Fix hardware, then restart service to clear soft anomalies

---

## Success Criteria

System is **production-ready** when:
1. ✓ Dry run audit passes (all tests green)
2. ✓ Sensors calibrated and stable readings
3. ✓ EC rises measurably after nutrient dose
4. ✓ Chiller/lights automation working
5. ✓ No guard anomalies for 1 hour of operation
6. ✓ Manual relay control responsive (<200ms)
7. ✓ E-Stop verified (blocks all control)

**Proceed to normal grow cycle operations.**
