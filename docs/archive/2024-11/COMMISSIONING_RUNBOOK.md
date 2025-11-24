# RDWC-v4 Commissioning Runbook
**Date**: 2025-11-09  
**System**: Raspberry Pi @ 192.168.88.49  
**Goal**: Complete calibration to enable nutrient hookup

---

## Prerequisites (COMPLETED ✓)
- [x] Estop OFF
- [x] Sensor poller running (poll #100+)
- [x] Relays functional
- [x] CALIB_ENABLE=1 set
- [x] HRT-aware dosing deployed (15min intervals)

---

## Physical Calibration Steps

### STEP 1: pH Calibration (3-point)

#### 1A. pH Mid-Point (7.0 buffer)
**Physical Action**:
1. Remove pH probe from reservoir
2. Rinse probe with distilled water
3. Place probe in **pH 7.0 buffer solution**
4. Wait 2 minutes for stabilization

**PowerShell Command**:
```powershell
ssh pi@192.168.88.49 "curl -s -X POST http://localhost:8080/calib/ph/mid"
```

**Expected Response**:
```json
{"ok": true, "note": "Cal applied", ...}
```

**Verification**:
```powershell
ssh pi@192.168.88.49 "curl -s http://localhost:8080/calib/ph/status"
```
Should show `"points": ["mid"]`

---

#### 1B. pH Low-Point (4.0 buffer)
**Physical Action**:
1. Rinse probe with distilled water
2. Place probe in **pH 4.0 buffer solution**
3. Wait 2 minutes for stabilization

**PowerShell Command**:
```powershell
ssh pi@192.168.88.49 "curl -s -X POST http://localhost:8080/calib/ph/low"
```

**Expected Response**:
```json
{"ok": true, "note": "Cal applied", ...}
```

**Verification**:
```powershell
ssh pi@192.168.88.49 "curl -s http://localhost:8080/calib/ph/status"
```
Should show `"points": ["mid", "low"]`

---

#### 1C. pH High-Point (10.0 buffer)
**Physical Action**:
1. Rinse probe with distilled water
2. Place probe in **pH 10.0 buffer solution**
3. Wait 2 minutes for stabilization

**PowerShell Command**:
```powershell
ssh pi@192.168.88.49 "curl -s -X POST http://localhost:8080/calib/ph/high"
```

**Expected Response**:
```json
{"ok": true, "note": "Cal applied", ...}
```

**Final Verification**:
```powershell
ssh pi@192.168.88.49 "curl -s http://localhost:8080/calib/ph/status"
```
Should show `"points": ["mid", "low", "high"]` or `"ok": true`

**Return probe to reservoir after completion**

---

### STEP 2: EC Calibration (1-point)

#### 2A. Clear Existing Calibration
**PowerShell Command**:
```powershell
ssh pi@192.168.88.49 "curl -s -X POST http://localhost:8080/api/ec/cal/clear"
```

#### 2B. EC Low-Point (1413 µS/cm)
**Physical Action**:
1. Remove EC probe from reservoir
2. Rinse probe with distilled water
3. Place probe in **1413 µS/cm calibration solution** (DO NOT use dry calibration!)
4. Wait 2 minutes for stabilization

**PowerShell Command**:
```powershell
ssh pi@192.168.88.49 "curl -s -X POST http://localhost:8080/api/ec/cal/low -H 'Content-Type: application/json' -d '{\"us_cm\":1413}'"
```

**Expected Response**:
```json
{"message": "EC low calibration accepted", ...}
```

**Verification**:
```powershell
ssh pi@192.168.88.49 "curl -s http://localhost:8080/api/ec/cal/status"
```
Should show `"low": true` or similar acceptance flag

**Return probe to reservoir after completion**

---

### STEP 3: Dosing Pump Calibration

#### 3A. pH Up Pump
**Physical Action**:
1. Place **pH Up** pump tube outlet into **graduated measuring cylinder**
2. Note starting volume (should be 0ml)

**Prime Pump** (0.5s test):
```powershell
ssh pi@192.168.88.49 "curl -s -X POST 'http://localhost:8080/calib/dose/prime?pump=ph_up&seconds=0.5'"
```
Wait 2 seconds.

**Calibration Run** (5 seconds):
```powershell
ssh pi@192.168.88.49 "curl -s -X POST 'http://localhost:8080/calib/dose/run?pump=ph_up&seconds=5'"
```

**Physical Action**:
1. Wait for pump to stop
2. Read volume in cylinder (e.g., 12.5 ml)
3. Record this value

**Commit Rate**:
```powershell
# Replace 12.5 with YOUR measured value
ssh pi@192.168.88.49 "curl -s -X POST 'http://localhost:8080/calib/dose/commit?pump=ph_up&seconds=5&measured_ml=12.5'"
```

**Verification**:
```powershell
ssh pi@192.168.88.49 "curl -s http://localhost:8080/calib/dose/pumps"
```
Should show `"ph_up": {"ml_per_sec": 2.5, ...}` (your measured rate)

---

#### 3B. pH Down Pump
**Repeat Step 3A** with:
- `pump=ph_down`
- Fresh measuring cylinder
- Record your measured ml
- Commit with your measured value

---

#### 3C. Nutrient A Pump (Grow)
**Repeat Step 3A** with:
- `pump=nutrient_a` (or check `/calib/dose/pumps` for actual pump name)
- Fresh measuring cylinder
- Record your measured ml
- Commit with your measured value

---

#### 3D. Nutrient B Pump (Micro)
**Repeat Step 3A** with:
- `pump=nutrient_b`
- Fresh measuring cylinder
- Record your measured ml
- Commit with your measured value

---

### STEP 4: Configure System Settings

**Set Reservoir Volume and Targets**:
```powershell
$settings = @{
    "general.reservoir_liters" = "100"
    "targets.ph_low" = "5.8"
    "targets.ph_high" = "6.2"
    "targets.ec_low_mscm" = "1.2"
    "targets.ec_high_mscm" = "1.8"
    "dosing.ph_min_interval_s" = "900"
    "dosing.ec_min_interval_s" = "900"
}
$body = $settings | ConvertTo-Json
ssh pi@192.168.88.49 "curl -s -X POST http://localhost:8080/api/settings/import -H 'Content-Type: application/json' -d '$body'"
```

**Verification**:
```powershell
ssh pi@192.168.88.49 "curl -s http://localhost:8080/settings"
```
Check that all values are saved correctly.

---

### STEP 5: Safety Systems Verification

#### 5A. Test E-STOP
```powershell
# Enable estop
ssh pi@192.168.88.49 "curl -s -X POST http://localhost:8080/api/relays/estop/toggle"

# Verify estop blocks dosing
ssh pi@192.168.88.49 "curl -s http://localhost:8080/api/ph/status"
# Should show "blocked": true or guards.estop: true

# Disable estop
ssh pi@192.168.88.49 "curl -s -X POST http://localhost:8080/api/relays/estop/toggle"
```

#### 5B. Test Daily Cap (simulated)
```powershell
# Check current daily totals
ssh pi@192.168.88.49 "curl -s http://localhost:8080/api/ph/status"
# Note "today_total_ml" - should be 0 or low

# Caps are enforced automatically; verify cap settings exist:
ssh pi@192.168.88.49 "curl -s http://localhost:8080/settings | grep -i 'max_ml_per_day'"
```

#### 5C. Test Stale Sensor Block
```powershell
# Stop sensor poller temporarily
ssh pi@192.168.88.49 "sudo systemctl stop rdwc-sensors.service"
sleep 120  # Wait 2 minutes

# Check that dosing is blocked
ssh pi@192.168.88.49 "curl -s http://localhost:8080/api/ph/status"
# Should show "blocked": true, "guards": {"sensor_stale": true}

# Restart poller
ssh pi@192.168.88.49 "sudo systemctl start rdwc-sensors.service"
sleep 10  # Wait for first poll
```

---

### STEP 6: Final Acceptance Checklist

**Run Complete Status Check**:
```powershell
# pH calibration status
ssh pi@192.168.88.49 "curl -s http://localhost:8080/calib/ph/status"
# EXPECT: "ok": true, "points": ["mid","low","high"]

# EC calibration status
ssh pi@192.168.88.49 "curl -s http://localhost:8080/api/ec/cal/status"
# EXPECT: "low": true

# Pump rates
ssh pi@192.168.88.49 "curl -s http://localhost:8080/calib/dose/pumps"
# EXPECT: All pumps have ml_per_sec > 0

# System settings
ssh pi@192.168.88.49 "curl -s http://localhost:8080/settings | grep -E '(reservoir|ph_low|ph_high|ec_low|ec_high)'"
# EXPECT: All targets configured

# Sensor health
ssh pi@192.168.88.49 "curl -s http://localhost:8080/api/sensors"
# EXPECT: "online": true, temp/pH/EC have values

# Progress
ssh pi@192.168.88.49 "curl -s http://localhost:8080/api/progress"
# EXPECT: percent close to 100%, all components true
```

---

## Post-Commissioning: Enable Auto Modes

**After verifying all calibrations are good**, you can enable automatic dosing:

### Enable pH Auto Mode
```powershell
ssh pi@192.168.88.49 "curl -s -X POST 'http://localhost:8080/api/ph/auto_mode?enable=true'"
```

### Enable EC Auto Mode
```powershell
ssh pi@192.168.88.49 "curl -s -X POST 'http://localhost:8080/api/ec/auto_mode?enable=true'"
```

### Verify Auto Modes Active
```powershell
ssh pi@192.168.88.49 "curl -s http://localhost:8080/api/ph/status"
ssh pi@192.168.88.49 "curl -s http://localhost:8080/api/ec/status"
```
Should show `"auto_mode_enabled": true` in both

---

## Acceptance Criteria (NUTRIENT-READY)

✅ **pH Calibration**: 3-point cal accepted (mid/low/high)  
✅ **EC Calibration**: 1-point cal accepted (low @ 1413)  
✅ **Pump Rates**: All 4 pumps have ml_per_sec > 0  
✅ **Settings**: Reservoir 100L, pH 5.8-6.2, EC 1.2-1.8  
✅ **Safety**: Estop blocks, daily caps set, stale blocks  
✅ **Sensors**: Online, fresh readings (<60s age)  
✅ **Progress**: 95-100%, all components green  

**When all above are ✅, system is READY for nutrient hookup.**

---

## Troubleshooting

### pH Calibration Won't Accept
- Ensure probe is fully submerged in buffer
- Wait full 2 minutes for stabilization
- Try `/calib/ph/read_stable?timeout_s=30` to verify stable reading
- If still failing, check `CALIB_ENABLE=1` in .env

### EC Calibration Fails
- NEVER use dry calibration (not supported)
- Use fresh 1413 µS/cm solution (check expiry date)
- Ensure probe is clean (no residue)
- Temperature should be 20-25°C for accuracy

### Pump Outputs 0 ml
- Check tube connections (inlet in reservoir, outlet in cylinder)
- Verify relay is clicking (listen for mechanical sound)
- Check pump power (LED indicator if present)
- Ensure tubes aren't kinked or blocked

### Sensors Show "Stale"
- Check sensor poller: `sudo systemctl status rdwc-sensors.service`
- Verify I²C connection: `i2cdetect -y 1` (should show 0x63, 0x64, 0x66)
- Check lock status: `ls -la /tmp/rdwc_*.lock`

---

## Estimated Time
- **pH Calibration**: 10 minutes (3 buffers × 2min stabilization)
- **EC Calibration**: 5 minutes
- **Pump Calibration**: 15 minutes (4 pumps × 3min each)
- **Settings & Verification**: 5 minutes
- **Total**: ~35 minutes hands-on time

---

**After commissioning, monitor first 24 hours for:**
1. No oscillation (pH/EC bouncing up/down rapidly)
2. Auto modes respect 15-min interval (check dose logs)
3. Sensor readings stay stable (no dropouts)
4. Dosing stays within daily caps

**Then you're good to hook up nutrients and let it run!** 🌱
