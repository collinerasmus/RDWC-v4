# 🚀 START HERE - RDWC-v4 System Commissioning

**Welcome!** You asked: *"Where do we start with the testing?"*

## The Answer: Start Right Here! 👇

### Quick Start (Recommended Path)

You have a **unified commissioning orchestrator** that will guide you through everything:

```bash
cd /home/pi/RDWC-v4
source venv/bin/activate
python tools/commission_system.py
```

That's it! The script will:
1. ✅ Check prerequisites (API, E-STOP, sensors)
2. 📋 Show you all commissioning phases
3. 🧪 Run automated tests for each phase
4. 📊 Generate detailed reports
5. ✓ Confirm what's working and what needs attention

---

## What Gets Tested?

### Phase 1: Sensors (5 min) - **REQUIRED**
- I²C communication with Atlas EZO sensors
- Sensor poller service health
- Data freshness (<60 seconds)
- Temperature compensation

### Phase 2: Relay Safety (10 min) - **REQUIRED**
- E-STOP functionality
- Mode transitions (manual/auto)
- Cooldown enforcement
- Protected relay guards

### Phase 3: pH Calibration (10 min) - *Optional*
- 3-point calibration (pH 4.01, 7.00, 10.00)
- Requires pH buffers and physical probe placement

### Phase 4: EC Calibration (5 min) - *Optional*
- K-value configuration
- 1-point calibration (1413 µS/cm)
- Requires calibration solution

### Phase 5: Dosing Pumps (15 min) - *Optional*
- Calibrate flow rates for all pumps
- Verify safety guards (caps, blocks)
- Requires graduated cylinders for measurement

---

## Not Testing (Per Your Request)

✅ **Skipping chiller hysteresis** - You mentioned the chiller works fine and we can resolve hysteresis later. The orchestrator doesn't test chiller-specific logic.

---

## Alternative: Manual Testing

If you want more control, run individual phase scripts:

```bash
# Required phases
python tools/commission_sensors.py      # Sensor health
python tools/commission_relays.py       # Safety systems

# Optional phases (only when ready)
python tools/commission_ph.py           # pH calibration
python tools/commission_ec.py           # EC calibration
python tools/commission_pumps.py        # Pump calibration
```

Each script:
- Runs independent tests
- Provides clear pass/fail output
- Saves a JSON report
- Gives you recommendations if anything fails

---

## What You'll Need

### For Required Phases (Sensors + Relays):
- ✓ Raspberry Pi connected and running
- ✓ API service running (`sudo systemctl status rdwc.service`)
- ✓ Sensor poller running (`sudo systemctl status rdwc-sensors.service`)
- ✓ E-STOP disabled (check web UI or API)

### For Optional Phases (only if commissioning those):
- pH buffers: 4.01, 7.00, 10.00 (fresh, not expired)
- EC calibration solution: 1413 µS/cm
- Graduated cylinders or measuring cups (for pump calibration)
- Distilled water (for rinsing probes)

---

## Expected Time

- **Minimum** (sensors + relays only): ~15 minutes
- **Full commissioning** (all phases): ~45-60 minutes
- **With automation**: Most waiting is for probe stabilization, actual test execution is fast

---

## What Happens After Testing?

After successful commissioning:

1. **Review Reports** - Check `commissioning_reports/` directory
2. **Check Web UI** - Open http://YOUR-PI-IP:8080 (e.g., http://192.168.88.49:8080) and verify:
   - Sensors tab shows fresh data
   - Relays tab shows correct states
   - pH/EC tabs show calibration status (if calibrated)
3. **Enable Auto Modes** (when ready):
   ```bash
   curl -X POST "http://localhost:8080/api/ph/auto_mode?enable=true"
   curl -X POST "http://localhost:8080/api/ec/auto_mode?enable=true"
   ```
4. **Monitor** - Watch for 24 hours to ensure stability

---

## Detailed Documentation

- **[COMMISSIONING_QUICKSTART.md](COMMISSIONING_QUICKSTART.md)** - Step-by-step guide with examples
- **[COMMISSIONING_RUNBOOK.md](COMMISSIONING_RUNBOOK.md)** - Detailed manual commands
- **[PI_COMMISSIONING_CHECKLIST.md](PI_COMMISSIONING_CHECKLIST.md)** - Full hardware checklist

---

## Troubleshooting

### Script won't run
```bash
# Make sure you're in the right directory
cd /home/pi/RDWC-v4

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt
```

### "API not reachable"
```bash
# Check if API is running
sudo systemctl status rdwc.service

# Start if needed
sudo systemctl start rdwc.service

# Check logs
journalctl -u rdwc.service -n 50
```

### "I²C device not found"
```bash
# Enable I²C interface
sudo raspi-config
# Interface Options → I2C → Enable
sudo reboot
```

### "Sensor poller not running"
```bash
# Start sensor poller
sudo systemctl start rdwc-sensors.service

# Check status
sudo systemctl status rdwc-sensors.service
```

---

## Need More Help?

- Check the **[QUICK_ANSWERS.md](QUICK_ANSWERS.md)** for common questions
- Review **[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)** for technical details
- See individual script help: `python tools/commission_sensors.py --help`

---

## Ready? Let's Go! 🎯

```bash
python tools/commission_system.py
```

The script will guide you through everything. Just follow the prompts!

---

**Note**: The commissioning orchestrator is designed to be **safe** and **non-destructive**. It only reads system state and runs controlled tests. You can stop at any time with Ctrl+C.
