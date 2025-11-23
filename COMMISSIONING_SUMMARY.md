# Commissioning Summary - What You Have Now

## 📋 Overview

You now have a **complete commissioning infrastructure** to test your RDWC-v4 system from start to finish.

## 🎯 What Changed

### New Files Added

1. **tools/commission_system.py** (452 lines)
   - Unified orchestrator that runs all commissioning phases
   - Interactive prompts guide you through each step
   - Auto mode available for testing/CI
   - Generates comprehensive JSON reports

2. **START_HERE.md** (170 lines)
   - Your entry point - answers "where do I start?"
   - Quick commands to get going
   - Troubleshooting common issues
   - Clear explanation of what gets tested

3. **COMMISSIONING_QUICKSTART.md** (340 lines)
   - Detailed step-by-step instructions for each phase
   - Physical actions required (probe placement, etc.)
   - Expected outputs for each test
   - Time estimates per phase
   - Troubleshooting tips

### Existing Tools You Have

All of these existed before and are now integrated into the orchestrator:

- **tools/commission_sensors.py** - I²C sensor validation
- **tools/commission_relays.py** - E-STOP and safety tests
- **tools/commission_ph.py** - pH 3-point calibration
- **tools/commission_ec.py** - EC calibration
- **tools/commission_pumps.py** - Pump flow rate calibration
- **tools/commissioning_readiness.py** - Overall readiness snapshot

## 🚀 How to Use

### On Your Raspberry Pi

```bash
# 1. SSH to your Pi
ssh pi@192.168.88.49

# 2. Go to the project directory
cd /home/pi/RDWC-v4

# 3. Activate Python virtual environment
source venv/bin/activate

# 4. Update to latest code
git pull origin main

# 5. Start commissioning!
python tools/commission_system.py
```

### What the Script Does

**Step 1**: Checks prerequisites
- ✓ API service reachable?
- ✓ E-STOP disabled?
- ✓ Sensor poller running?

**Step 2**: Shows you all commissioning phases
- Sensor Health (required)
- Relay Safety (required)
- pH Calibration (optional)
- EC Calibration (optional)
- Pump Calibration (optional)

**Step 3**: Runs each phase
- Executes automated tests
- Saves reports to `commissioning_reports/`
- Shows pass/fail results
- Provides recommendations

**Step 4**: Generates final report
- Summary of all phases
- Overall success/failure status
- Final system snapshot
- Timestamped for archiving

## 📊 What Gets Tested

### Phase 1: Sensors (Required)
- I²C device exists
- All 3 sensors detected (pH, EC, RTD)
- Sensor poller service running
- Data is fresh (<60 seconds old)
- Health state is green
- Temperature compensation working

**Exit codes**:
- 0 = All good
- 1 = I²C device missing
- 2 = Sensors offline/stale
- 3 = Service not running

### Phase 2: Relays (Required)
- E-STOP activates and deactivates
- E-STOP blocks all relay operations
- All relays turn OFF when E-STOP active
- Manual/auto mode transitions work
- Protected relays (lights/chiller) enforce reasons
- Cooldown timers prevent rapid on/off cycles

**Exit codes**:
- 0 = All safety checks pass
- 1 = E-STOP failure
- 2 = Cooldown violation
- 3 = Protected relay bypass

### Phase 3: pH Calibration (Optional)
- Read current pH value
- Wait for stability (±0.02 pH)
- Apply 3-point calibration (4.01, 7.00, 10.00)
- Verify all calibration flags set
- Check reservoir accuracy

**Requires**: pH buffers and manual probe placement

### Phase 4: EC Calibration (Optional)
- Set probe K-value (typically 1.0)
- Clear existing calibration
- Apply 1-point calibration (1413 µS/cm)
- Verify calibration accepted
- Check reservoir reading

**Requires**: EC calibration solution

### Phase 5: Pump Calibration (Optional)
- Discover available pumps
- Prime each pump (remove air)
- Run pump for timed duration
- Measure dispensed volume
- Calculate and save flow rate (ml/sec)
- Verify safety guards active

**Requires**: Graduated cylinders for measuring

## 🎛️ Command Options

### Run Everything (Interactive)
```bash
python tools/commission_system.py
```
Prompts you before each phase.

### Run Specific Phases Only
```bash
python tools/commission_system.py --phase sensors --phase relays
```
Only runs required phases.

### Skip Certain Phases
```bash
python tools/commission_system.py --skip-phase pumps
```
Runs all except pumps.

### Auto Mode (No Prompts)
```bash
python tools/commission_system.py --auto
```
For testing/CI - doesn't wait for user input.

### Change Output Directory
```bash
python tools/commission_system.py --output-dir /path/to/reports
```

## 📝 Output Files

After running, you'll have:

```
commissioning_reports/
├── commissioning_final_20251123_161500.json    # Overall summary
├── sensors_20251123_161500.json                # Sensor phase results
├── relays_20251123_161500.json                 # Relay phase results
├── ph_20251123_161500.json                     # pH phase results (if run)
├── ec_20251123_161500.json                     # EC phase results (if run)
└── pumps_20251123_161500.json                  # Pump phase results (if run)
```

Each JSON file contains:
- Script name and version
- Configuration used
- Test results (pass/fail)
- Detailed data
- Errors encountered
- Recommendations

## 🔍 Viewing Reports

### Quick Summary
```bash
cat commissioning_reports/commissioning_final_*.json | jq '.summary'
```

### Check Sensor Results
```bash
cat commissioning_reports/sensors_*.json | jq '.results'
```

### See Recommendations
```bash
cat commissioning_reports/sensors_*.json | jq '.recommendations'
```

## ✅ Success Criteria

After successful commissioning, you should see:

**Sensors**:
- ✓ All 3 sensors detected
- ✓ Data age <60 seconds
- ✓ Health state: green
- ✓ Temperature compensation active

**Relays**:
- ✓ E-STOP functional
- ✓ Mode transitions work
- ✓ Cooldowns enforced
- ✓ Protected relays safeguarded

**pH** (if calibrated):
- ✓ All 3 flags: mid, low, high
- ✓ Stable readings in buffers
- ✓ Reservoir reading accurate

**EC** (if calibrated):
- ✓ K-value set
- ✓ Low-point calibration accepted
- ✓ Reservoir reading reasonable

**Pumps** (if calibrated):
- ✓ All pumps have ml_per_sec >0
- ✓ Safety guards active
- ✓ Dose logs working

## 🚨 Troubleshooting

### "API not reachable"
```bash
sudo systemctl status rdwc.service
sudo systemctl start rdwc.service
```

### "I²C device not found"
```bash
sudo raspi-config
# Interface Options → I2C → Enable
sudo reboot
```

### "Sensor poller not running"
```bash
sudo systemctl start rdwc-sensors.service
journalctl -u rdwc-sensors.service -n 50
```

### "E-STOP is active"
```bash
# Via API
curl -X POST http://localhost:8080/api/relays/estop/toggle

# Or use web UI: http://192.168.88.49:8080 → System tab
```

### Script crashes or hangs
```bash
# Check Python version (needs 3.9+)
python3 --version

# Reinstall dependencies
pip install -r requirements.txt

# Check logs
journalctl -u rdwc.service -n 100
```

## 📚 Related Documentation

- **START_HERE.md** - Quick start guide (read this first!)
- **COMMISSIONING_QUICKSTART.md** - Detailed phase instructions
- **COMMISSIONING_RUNBOOK.md** - Original manual runbook
- **PI_COMMISSIONING_CHECKLIST.md** - Hardware commissioning checklist
- **SYSTEM_ARCHITECTURE.md** - Technical architecture
- **QUICK_ANSWERS.md** - FAQ and common questions

## 🎓 What's Next?

After commissioning succeeds:

1. **Review Reports** - Check JSON files for any warnings
2. **Monitor 24 Hours** - Ensure system stability
3. **Hook Up Nutrients** - Connect dosing pumps to nutrient containers
4. **Configure Targets** - Set pH/EC ranges in web UI
5. **Enable Auto Modes** - Let the system manage itself
6. **Watch Trends** - Monitor sensor charts and dose logs

## 💡 Tips

- **Run required phases first** (sensors + relays) before optional ones
- **Save commissioning reports** - Archive them for later reference
- **Check web UI** after each phase to see state changes
- **Use auto mode** for testing scripts without hardware interaction
- **Rerun phases** if you make changes to calibration or configuration

## 📞 Getting Help

If commissioning fails:

1. Check the specific phase's JSON report for details
2. Review the recommendations section
3. Check system logs: `journalctl -u rdwc.service -n 100`
4. Verify hardware connections (sensors, relays, pumps)
5. Ensure all prerequisites are met (services running, E-STOP off)

## 🎉 You're Ready!

You now have everything needed to commission your RDWC system. Just run:

```bash
python tools/commission_system.py
```

And follow the prompts!

---

**Note**: Per your request, chiller hysteresis testing is **NOT** included in commissioning. The chiller works fine and hysteresis can be addressed separately later.
