# RDWC-v4 Commissioning Quick Start

**Goal**: Guide you through commissioning your RDWC system step-by-step, starting from scratch.

**Time Required**: ~45-60 minutes for complete commissioning (or less if skipping optional phases)

---

## Where to Start? Right Here! 🚀

You have two options for commissioning:

### Option 1: Automated Commissioning (Recommended)
Run the unified commissioning orchestrator that guides you through all phases:

```bash
cd /home/pi/RDWC-v4
source venv/bin/activate
python tools/commission_system.py
```

This will:
- Check prerequisites (API, E-STOP, sensor poller)
- Guide you through each commissioning phase
- Run automated tests and validations
- Generate comprehensive reports in `commissioning_reports/`

**What it tests**:
1. ✅ **Sensors** - I²C communication, freshness, health
2. ✅ **Relays** - E-STOP, mode transitions, cooldowns, protected relays
3. 📊 **pH Calibration** - 3-point calibration (optional, requires buffers)
4. 📊 **EC Calibration** - 1-point calibration (optional, requires solution)
5. 💧 **Dosing Pumps** - Calibrate flow rates (optional, requires measuring)

### Option 2: Manual Phase-by-Phase
Run individual commissioning scripts as needed:

```bash
# 1. Check sensor health (REQUIRED)
python tools/commission_sensors.py

# 2. Test relay safety systems (REQUIRED)
python tools/commission_relays.py

# 3. Calibrate pH (optional - only if you have pH buffers)
python tools/commission_ph.py

# 4. Calibrate EC (optional - only if you have calibration solution)
python tools/commission_ec.py

# 5. Calibrate dosing pumps (optional - only if ready to hook up nutrients)
python tools/commission_pumps.py
```

---

## Phase-by-Phase Guide

### Phase 1: Sensor Validation (5 minutes) ⚡ REQUIRED

**What it checks**:
- I²C device `/dev/i2c-1` exists
- Atlas EZO sensors detected at correct addresses (pH 0x63, EC 0x64, RTD 0x66)
- Sensor poller service running
- Fresh data (<60 seconds old)
- Temperature compensation working

**Run**:
```bash
python tools/commission_sensors.py
```

**Expected Output**:
- All sensors found at correct addresses ✓
- Data is fresh ✓
- Health state: green ✓

**Troubleshooting**:
- If I²C device missing: `sudo raspi-config` → Interface Options → I2C → Enable
- If sensors not detected: Check wiring and power
- If stale data: `sudo systemctl restart rdwc-sensors.service`

---

### Phase 2: Relay Safety (10 minutes) ⚡ REQUIRED

**What it tests**:
- E-STOP activation/deactivation
- E-STOP blocks relay operations
- Manual/auto mode transitions
- Protected relays (lights, chiller) reject invalid reasons
- Cooldown enforcement (prevents rapid on/off cycles)

**Run**:
```bash
python tools/commission_relays.py
```

**Expected Output**:
- E-STOP toggle works ✓
- All relays turn OFF when E-STOP active ✓
- Relay operations blocked during E-STOP ✓
- Mode transitions successful ✓
- Cooldown enforced ✓

**What You'll See**:
The script will automatically toggle E-STOP and test various safety mechanisms. Watch the output for green SUCCESS messages.

---

### Phase 3: pH Calibration (10 minutes) - OPTIONAL

**Prerequisites**:
- pH 4.01, 7.00, and 10.00 buffer solutions (fresh, not expired)
- Clean, hydrated pH probe
- `CALIB_ENABLE=1` set in `.env` file

**Physical Actions Required**:
1. Place probe in pH 7.00 buffer → wait for stability → run calibration
2. Rinse → place in pH 4.01 buffer → wait → run calibration
3. Rinse → place in pH 10.00 buffer → wait → run calibration
4. Rinse → return probe to reservoir

**Run**:
```bash
python tools/commission_ph.py
```

**Expected Output**:
- All 3 calibration points accepted (mid, low, high) ✓
- Stable readings in buffers (±0.02 pH) ✓
- Final reservoir reading reasonable ✓

**Auto Mode** (for testing without physical buffers):
```bash
python tools/commission_ph.py --auto-advance --skip-reservoir
```

---

### Phase 4: EC Calibration (5 minutes) - OPTIONAL

**Prerequisites**:
- EC 1413 µS/cm calibration solution (fresh)
- Clean EC probe
- Probe K-value known (typically K=1.0)

**Physical Actions Required**:
1. Set K-value (usually 1.0)
2. Place probe in 1413 solution → wait → run calibration
3. Rinse → return probe to reservoir

**Run**:
```bash
python tools/commission_ec.py
```

**Expected Output**:
- K-value set correctly ✓
- Low-point calibration accepted ✓
- Reservoir reading reasonable ✓

**Auto Mode** (for testing):
```bash
python tools/commission_ec.py --auto-advance --skip-accuracy
```

---

### Phase 5: Dosing Pump Calibration (15 minutes) - OPTIONAL

**Prerequisites**:
- Graduated cylinders or measuring cups
- All dosing pumps connected and primed
- Access to pump relay controls

**Physical Actions Required** (for each pump):
1. Place outlet tube in graduated cylinder
2. Prime pump (5 seconds) to remove air
3. Run pump for 30 seconds
4. Measure volume dispensed (e.g., 15.2 ml)
5. Commit measured volume to system

**Pumps to Calibrate**:
- `ph_up` - pH Up solution pump
- `ph_down` - pH Down solution pump
- `nutrient_a` - Grow nutrient pump
- `nutrient_b` - Micro nutrient pump

**Run**:
```bash
python tools/commission_pumps.py
```

**Expected Output**:
- All pumps have ml_per_sec > 0 ✓
- Safety guards active (caps, E-STOP blocks, etc.) ✓
- Dose logs working ✓

**Auto Mode** (for testing without physical measurement):
```bash
python tools/commission_pumps.py --skip-guards --auto-advance
```

---

## After Commissioning

### Check Overall Readiness
Run the readiness check to get a comprehensive snapshot:

```bash
python tools/commissioning_readiness.py --compact --require-sensors
```

This will output JSON showing the status of all subsystems.

### Generate Final Report
All commissioning scripts automatically save reports to JSON files. After running the unified orchestrator, check:

```
commissioning_reports/
  ├── commissioning_final_YYYYMMDD_HHMMSS.json
  ├── sensors_YYYYMMDD_HHMMSS.json
  ├── relays_YYYYMMDD_HHMMSS.json
  ├── ph_YYYYMMDD_HHMMSS.json
  ├── ec_YYYYMMDD_HHMMSS.json
  └── pumps_YYYYMMDD_HHMMSS.json
```

### Enable Auto Modes (When Ready)
After successful commissioning and testing:

```bash
# Enable pH auto-dosing
curl -X POST "http://localhost:8080/api/ph/auto_mode?enable=true"

# Enable EC auto-dosing
curl -X POST "http://localhost:8080/api/ec/auto_mode?enable=true"

# Verify
curl http://localhost:8080/api/ph/status
curl http://localhost:8080/api/ec/status
```

---

## Common Issues & Solutions

### "I²C device not found"
```bash
# Enable I²C
sudo raspi-config
# Interface Options → I2C → Enable
sudo reboot
```

### "Sensor poller not running"
```bash
# Start the sensor poller service
sudo systemctl start rdwc-sensors.service
sudo systemctl status rdwc-sensors.service
```

### "E-STOP is active"
```bash
# Toggle E-STOP via API
curl -X POST http://localhost:8080/api/relays/estop/toggle

# Or use the web UI System tab
```

### "Calibration lock exists"
```bash
# If calibration is stuck, remove lock (ensure poller not reading)
sudo rm /tmp/rdwc_calib.lock
```

### "Sensors show stale data"
```bash
# Check poller logs
journalctl -u rdwc-sensors.service -n 50

# Restart if needed
sudo systemctl restart rdwc-sensors.service
```

---

## What Gets Skipped (Per User Request)

✅ **Testing everything EXCEPT chiller hysteresis**

The chiller itself works fine, so we're not testing:
- Chiller hysteresis value updates
- Chiller temperature control logic
- Chiller state transitions

These can be addressed later when you're ready.

---

## Quick Reference Commands

```bash
# View API version
curl http://localhost:8080/api/version

# Check relay status
curl http://localhost:8080/api/relays/status

# Check sensor data
curl http://localhost:8080/api/sensors

# Check E-STOP status
curl http://localhost:8080/api/relays/status | jq '.estop'

# List all pumps
curl http://localhost:8080/calib/dose/pumps

# Check pH calibration status
curl http://localhost:8080/calib/ph/status

# Check EC calibration status
curl http://localhost:8080/api/ec/cal/status
```

---

## Next Steps After Commissioning

1. ✅ **Verify all phases passed** - Check final report
2. 📊 **Monitor for 24 hours** - Ensure stability
3. 💧 **Hook up nutrients** - Connect dosing pumps to nutrient containers
4. 🎯 **Set targets** - Configure pH/EC ranges via web UI
5. 🤖 **Enable auto modes** - Let the system manage itself
6. 📈 **Monitor trends** - Check sensor charts and dose logs

---

## Need Help?

- **Commissioning scripts**: See `tools/commission_*.py`
- **Detailed docs**: See `COMMISSIONING_RUNBOOK.md` and `PI_COMMISSIONING_CHECKLIST.md`
- **API reference**: See `SYSTEM_ARCHITECTURE.md`
- **Issues**: Check logs with `journalctl -u rdwc.service -n 100`

**Ready to start?** Run:
```bash
python tools/commission_system.py
```
