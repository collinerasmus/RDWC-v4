# Commissioning Commands Cheat Sheet

Quick reference for commissioning your RDWC-v4 system.

## 🚀 Quick Start

```bash
# Complete commissioning (all phases)
python tools/commission_system.py

# Just required phases (sensors + relays)
python tools/commission_system.py --phase sensors --phase relays

# Skip optional phases
python tools/commission_system.py --skip-phase pumps

# Auto mode (no prompts)
python tools/commission_system.py --auto
```

---

## 📋 Individual Phase Scripts

### Sensors (Required)
```bash
python tools/commission_sensors.py
# Output: sensor_report.json
# Exit codes: 0=success, 1=I²C missing, 2=offline, 3=service down
```

### Relays (Required)
```bash
python tools/commission_relays.py
# Output: relay_safety.json
# Exit codes: 0=success, 1=E-STOP fail, 2=cooldown fail, 3=protected fail
```

### pH Calibration (Optional)
```bash
python tools/commission_ph.py
# Output: ph_calibration.json
# Requires: pH buffers (4.01, 7.00, 10.00)

# Auto mode (testing without buffers)
python tools/commission_ph.py --auto-advance --skip-reservoir
```

### EC Calibration (Optional)
```bash
python tools/commission_ec.py
# Output: ec_calibration.json
# Requires: 1413 µS/cm solution

# Auto mode (testing)
python tools/commission_ec.py --auto-advance --skip-accuracy
```

### Pump Calibration (Optional)
```bash
python tools/commission_pumps.py
# Output: pump_calibration.json
# Requires: Graduated cylinders

# Auto mode (testing)
python tools/commission_pumps.py --skip-guards --auto-advance
```

---

## 🔍 System Status Checks

### Check Overall Readiness
```bash
python tools/commissioning_readiness.py --compact
```

### Check Specific Requirements
```bash
# Require sensors online
python tools/commissioning_readiness.py --compact --require-sensors

# Require pH calibrated
python tools/commissioning_readiness.py --compact --require-ph

# Both
python tools/commissioning_readiness.py --compact --require-sensors --require-ph
```

---

## 🌐 API Endpoints (Manual Testing)

### System Status
```bash
# API version
curl http://localhost:8080/api/version

# Relay status
curl http://localhost:8080/api/relays/status

# Sensor data
curl http://localhost:8080/api/sensors

# Sensor poller status
curl http://localhost:8080/api/sensors/status

# E-STOP status
curl http://localhost:8080/api/relays/status | jq '.estop'

# Full commissioning snapshot
curl http://localhost:8080/api/commissioning/snapshot
```

### Sensors
```bash
# Read sensors once (bypasses cache)
curl -X POST http://localhost:8080/read_now

# Check I²C addresses
curl -X POST http://localhost:8080/fix_ezo

# Power cycle sensors (if sensor_power relay exists)
curl -X POST "http://localhost:8080/api/sensors/power_cycle?off_ms=2000&post_wait_ms=4000&validate=1"
```

### pH Calibration
```bash
# Check capabilities
curl http://localhost:8080/calib/ph/caps

# Current pH reading
curl http://localhost:8080/calib/ph/read

# Wait for stable reading
curl "http://localhost:8080/calib/ph/read_stable?timeout_s=45&delta=0.03"

# Calibration status
curl http://localhost:8080/calib/ph/status

# Apply calibrations (requires CALIB_ENABLE=1)
curl -X POST http://localhost:8080/calib/ph/mid    # pH 7.00
curl -X POST http://localhost:8080/calib/ph/low    # pH 4.01
curl -X POST http://localhost:8080/calib/ph/high   # pH 10.00

# Clear calibration
curl -X POST http://localhost:8080/calib/ph/clear
```

### EC Calibration
```bash
# Set K-value
curl -X POST http://localhost:8080/api/ec/k \
  -H "Content-Type: application/json" \
  -d '{"k_value": 1.0}'

# Clear calibration
curl -X POST http://localhost:8080/api/ec/cal/clear

# Apply low-point calibration
curl -X POST http://localhost:8080/api/ec/cal/low \
  -H "Content-Type: application/json" \
  -d '{"value": 1413}'

# Calibration status
curl http://localhost:8080/api/ec/cal/status
```

### Dosing Pumps
```bash
# List all pumps
curl http://localhost:8080/calib/dose/pumps

# Prime pump (5 seconds)
curl -X POST http://localhost:8080/calib/dose/prime \
  -H "Content-Type: application/json" \
  -d '{"pump_id": "ph_up", "duration_sec": 5}'

# Calibration run (30 seconds)
curl -X POST http://localhost:8080/calib/dose/run \
  -H "Content-Type: application/json" \
  -d '{"pump_id": "ph_up", "duration_sec": 30}'

# Commit measured volume
curl -X POST http://localhost:8080/calib/dose/commit \
  -H "Content-Type: application/json" \
  -d '{"pump_id": "ph_up", "volume_ml": 15.2}'
```

### E-STOP and Relays
```bash
# Toggle E-STOP
curl -X POST http://localhost:8080/api/relays/estop/toggle

# Set relay mode (manual or auto)
curl -X POST http://localhost:8080/api/relays/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "manual"}'

# Set individual relay
curl -X POST http://localhost:8080/api/relays/set \
  -H "Content-Type: application/json" \
  -d '{"relay_key": "main_pump", "state": true, "reason": "test"}'
```

### Auto Modes
```bash
# Enable pH auto-dosing
curl -X POST "http://localhost:8080/api/ph/auto_mode?enable=true"

# Enable EC auto-dosing
curl -X POST "http://localhost:8080/api/ec/auto_mode?enable=true"

# Check pH status
curl http://localhost:8080/api/ph/status

# Check EC status
curl http://localhost:8080/api/ec/status
```

---

## 📊 View Reports

### List Reports
```bash
ls -lh commissioning_reports/
```

### View Summary (using jq)
```bash
# Overall summary
cat commissioning_reports/commissioning_final_*.json | jq '.summary'

# Sensor results
cat commissioning_reports/sensors_*.json | jq '.results'

# Relay test results
cat commissioning_reports/relays_*.json | jq '.results'

# pH calibration
cat commissioning_reports/ph_*.json | jq '.results'

# Recommendations
cat commissioning_reports/sensors_*.json | jq '.recommendations'
```

### View All Reports (pretty print)
```bash
for f in commissioning_reports/*.json; do
  echo "=== $f ==="
  jq '.' "$f"
  echo
done
```

---

## 🔧 System Services

### Sensor Poller
```bash
# Status
sudo systemctl status rdwc-sensors.service

# Start
sudo systemctl start rdwc-sensors.service

# Stop
sudo systemctl stop rdwc-sensors.service

# Restart
sudo systemctl restart rdwc-sensors.service

# Logs
journalctl -u rdwc-sensors.service -n 50
```

### API Service
```bash
# Status
sudo systemctl status rdwc.service

# Start
sudo systemctl start rdwc.service

# Stop
sudo systemctl stop rdwc.service

# Restart
sudo systemctl restart rdwc.service

# Logs
journalctl -u rdwc.service -n 100
```

---

## 🛠️ Troubleshooting

### Enable I²C
```bash
sudo raspi-config
# Interface Options → I2C → Enable
sudo reboot
```

### Check I²C Devices
```bash
# Check device exists
ls -l /dev/i2c-1

# Scan for sensors
i2cdetect -y 1
# Expected: 0x63 (pH), 0x64 (EC), 0x66 (RTD)
```

### Remove Stale Locks
```bash
# Calibration lock
sudo rm /tmp/rdwc_calib.lock

# Sensor poller lock
sudo rm /run/rdwc_sensors.lock
```

### Check Python Environment
```bash
# Python version (needs 3.9+)
python3 --version

# Activate venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 📖 Documentation

- **START_HERE.md** - Read first!
- **COMMISSIONING_QUICKSTART.md** - Step-by-step guide
- **COMMISSIONING_SUMMARY.md** - Complete overview
- **COMMISSIONING_RUNBOOK.md** - Detailed manual runbook

---

## 💡 Tips

### Save Command History
```bash
# Save useful commands for later
history | grep commission > my_commissioning_history.txt
```

### Watch Sensor Data in Real-Time
```bash
# Update every 2 seconds
watch -n 2 'curl -s http://localhost:8080/api/sensors | jq "{temp: .temperature_c, ph: .ph, ec: .ec_mscm, online: .online}"'
```

### Check Disk Space for Reports
```bash
df -h /home/pi/RDWC-v4/commissioning_reports/
```

### Archive Old Reports
```bash
# Create dated archive
tar -czf commissioning_archive_$(date +%Y%m%d).tar.gz commissioning_reports/
```

---

## 🎯 Quick Acceptance Check

After commissioning, run this to check everything:

```bash
#!/bin/bash
echo "=== Sensors ==="
curl -s http://localhost:8080/api/sensors | jq '{online, age_seconds, health_state}'

echo "=== E-STOP ==="
curl -s http://localhost:8080/api/relays/status | jq '{estop, mode}'

echo "=== pH Calibration ==="
curl -s http://localhost:8080/calib/ph/status | jq '.flags'

echo "=== EC Calibration ==="
curl -s http://localhost:8080/api/ec/cal/status | jq '.cal'

echo "=== Pumps ==="
curl -s http://localhost:8080/calib/dose/pumps | jq '.pumps | to_entries[] | {pump: .key, rate: .value.ml_per_sec}'
```

Save as `check_commissioning.sh` and run with `bash check_commissioning.sh`
