# Raspberry Pi Hardware Commissioning Checklist

**Generated**: 2025-11-16  
**Baseline**: Development environment (Windows) - all hardware operations require Pi deployment

## Automated Commissioning Scripts

**NEW**: Automated Python scripts are now available to replace manual curl commands. These provide structured JSON reports and systematic validation.

### Quick Start (Automated)
```bash
# Full automated commissioning (all phases)
sudo python tools/commission_all.py

# Individual phases
python tools/commission_sensors.py      # Phase 1: Sensor validation
python tools/commission_ph.py           # Phase 2: pH calibration
python tools/commission_ec.py           # Phase 3: EC calibration
python tools/commission_relays.py       # Phase 4: Relay safety tests
python tools/commission_pumps.py        # Phase 5: Pump calibration

# With auto-advance for testing (skips interactive prompts)
python tools/commission_ph.py --auto-advance --skip-reservoir
python tools/commission_ec.py --auto-advance --skip-accuracy
```

**Benefits**:
- Structured JSON reports with metadata and recommendations
- Automatic retry logic with exponential backoff
- Clear exit codes for automation/CI integration
- Progress indicators and colored output
- Safety validation and error handling

**See**: `docs/COMMISSIONING_AUTOMATION.md` for detailed documentation

## Pre-Deployment Verification

- [x] All Dependabot PRs resolved (#52-55)
- [x] GitHub Actions upgraded to Node 24
- [x] Test suite stable (no errors in workspace)
- [x] Repository reduced to 5 commissioning issues (#56-60)
- [x] Commissioning readiness tooling complete
- [x] API snapshot endpoint available (`/api/commissioning/snapshot`)

## Pi Deployment Steps

### 1. Code Deployment
```bash
# On Pi
cd /home/pi/RDWC-v4
git pull origin main
source venv/bin/activate
pip install -r requirements.txt --upgrade
```

### 2. Service Verification
```bash
# Check sensor poller service
sudo systemctl status rdwc-sensors.service
sudo systemctl start rdwc-sensors.service  # if not running

# Check API service
sudo systemctl status rdwc.service
sudo systemctl restart rdwc.service
```

### 3. I²C Hardware Check
```bash
# Verify I²C device exists
ls -l /dev/i2c-1

# Scan for EZO sensors (expect 0x63, 0x64, 0x66)
i2cdetect -y 1

# Test API I²C endpoint
curl http://localhost:8080/diag/sensors/once
```

## Hardware Commissioning Sequence

### Phase 1: Sensor Health (#59)
**Objective**: Validate I²C communication, freshness tracking, temperature compensation

**Automated Script**: `python tools/commission_sensors.py` (outputs: `sensor_report.json`)

**Acceptance Criteria**:
- [ ] All 3 sensors detected at correct addresses (pH 0x63, EC 0x64, RTD 0x66)
- [ ] Sensor poller running (`systemctl status rdwc-sensors`)
- [ ] Fresh readings: `GET /api/sensors` shows `online: true`, age <60s
- [ ] Health state: green (<60s)
- [ ] Temperature compensation throttling active

**Manual Commands** (or use automated script above):
```bash
# Baseline snapshot
curl http://localhost:8080/api/commissioning/snapshot > snapshot_sensors_baseline.json

# Check poller status
curl http://localhost:8080/api/sensors/status

# Verify fresh data
curl http://localhost:8080/api/sensors | jq '.online, .age_seconds, .health_state'

# One-shot read test (lock coordination)
curl -X POST http://localhost:8080/read_now

# Optional: Power cycle sensors (if RDWC_SENSOR_POWER_PIN configured)
curl -X POST "http://localhost:8080/api/sensors/power_cycle?off_ms=2000&post_wait_ms=4000&validate=1"
```

**Validation**:
```bash
python tools/commissioning_readiness.py --compact --require-sensors
# Exit code 0 = success, 2 = sensors offline
```

### Phase 2: pH Calibration (#56)
**Objective**: 3-point calibration (mid/low/high), validate accuracy

**Automated Script**: `python tools/commission_ph.py` (outputs: `ph_calibration.json`)
- With options: `--auto-advance` (skip prompts), `--skip-reservoir` (skip accuracy check)

**Prerequisites**:
- Fresh pH 4.01, 7.00, 10.00 buffer solutions
- pH probe cleaned and hydrated
- `CALIB_ENABLE=1` environment variable set

**Manual Commands** (or use automated script above):
```bash
# Check calibration capabilities
curl http://localhost:8080/calib/ph/caps

# Clear existing calibration
curl -X POST http://localhost:8080/calib/ph/clear

# Mid-point (pH 7.00)
curl http://localhost:8080/calib/ph/read  # Check current reading
curl "http://localhost:8080/calib/ph/read_stable?timeout_s=45&delta=0.03"  # Wait for stability
curl -X POST http://localhost:8080/calib/ph/mid

# Low-point (pH 4.01)
# (Place probe in pH 4.01 buffer, wait for stability)
curl "http://localhost:8080/calib/ph/read_stable?timeout_s=45&delta=0.03"
curl -X POST http://localhost:8080/calib/ph/low

# High-point (pH 10.00)
# (Place probe in pH 10.00 buffer, wait for stability)
curl "http://localhost:8080/calib/ph/read_stable?timeout_s=45&delta=0.03"
curl -X POST http://localhost:8080/calib/ph/high

# Verify calibration flags
curl http://localhost:8080/calib/ph/status | jq '.flags'

# Capture snapshot
curl http://localhost:8080/api/commissioning/snapshot > snapshot_ph_calibrated.json
```

**Acceptance Criteria**:
- [ ] All 3 flags present: `mid`, `low`, `high`
- [ ] Stable readings in buffers (±0.02 pH over 30s)
- [ ] Reservoir reading within ±0.05 of reference meter

**Validation**:
```bash
python tools/commissioning_readiness.py --compact --require-sensors --require-ph
# Exit code 0 = success, 3 = pH invalid
```

### Phase 3: EC Calibration (#57)
**Objective**: Set K-value, 1-point low calibration (1413 µS/cm)

**Automated Script**: `python tools/commission_ec.py` (outputs: `ec_calibration.json`)
- With options: `--k-value 1.0`, `--two-point` (enable high-point), `--skip-accuracy`

**Prerequisites**:
- EC 1413 µS/cm calibration solution
- Optional: EC 12,880 µS/cm for 2-point

**Manual Commands** (or use automated script above):
```bash
# Set probe K-value (typically K=1.0)
curl -X POST http://localhost:8080/api/ec/k -H "Content-Type: application/json" -d '{"k_value": 1.0}'

# Clear existing calibration
curl -X POST http://localhost:8080/api/ec/cal/clear

# Low-point (1413 µS/cm)
# (Place probe in 1413 solution, wait for stability)
curl -X POST http://localhost:8080/api/ec/cal/low -H "Content-Type: application/json" -d '{"value": 1413}'

# Optional: High-point (12880 µS/cm)
curl -X POST http://localhost:8080/api/ec/cal/high -H "Content-Type: application/json" -d '{"value": 12880}'

# Verify calibration
curl http://localhost:8080/api/ec/cal/status | jq '.cal'

# Capture snapshot
curl http://localhost:8080/api/commissioning/snapshot > snapshot_ec_calibrated.json
```

**Acceptance Criteria**:
- [ ] K-value correctly set (1.0 typical)
- [ ] Low-point calibration accepted
- [ ] Reservoir reading within ±50 µS/cm of reference meter

### Phase 4: Relay Safety Tests (#58)
**Objective**: Validate E-STOP, manual/auto modes, cooldown enforcement

**Automated Script**: `python tools/commission_relays.py` (outputs: `relay_safety.json`)

**Manual Commands** (or use automated script above):
```bash
# Baseline relay state
curl http://localhost:8080/api/relays/status | jq '.mode, .estop, .relays | keys'

# Test E-STOP
curl -X POST http://localhost:8080/api/relays/estop/toggle
curl http://localhost:8080/api/relays/status | jq '.estop'  # Should be true

# Attempt relay operation (should fail)
curl -X POST http://localhost:8080/api/relays/set -H "Content-Type: application/json" \
  -d '{"relay_key": "main_pump", "state": true, "reason": "test"}'
# Expect guard block

# Release E-STOP
curl -X POST http://localhost:8080/api/relays/estop/toggle
curl http://localhost:8080/api/relays/status | jq '.estop'  # Should be false

# Test manual mode
curl -X POST http://localhost:8080/api/relays/mode -H "Content-Type: application/json" -d '{"mode": "manual"}'
# Toggle relays individually via UI, observe cooldown enforcement

# Test auto mode
curl -X POST http://localhost:8080/api/relays/mode -H "Content-Type: application/json" -d '{"mode": "auto"}'

# Power-on test (state restoration)
sudo systemctl restart rdwc.service
sleep 5
curl http://localhost:8080/api/relays/status | jq '.relays | map_values(.is_on)'
# Expect all false (safe default)
```

**Acceptance Criteria**:
- [ ] E-STOP blocks all relay operations
- [ ] Cooldown timers enforce MIN_ON/OFF periods
- [ ] Manual/auto mode transitions clean
- [ ] Relays default to OFF on service restart
- [ ] Protected relays (lights/chiller) require whitelisted reasons

### Phase 5: Dosing Pump Calibration (#60)
**Objective**: Calibrate all pumps (pH Up, Grow, Micro, Bloom), validate safety guards

**Automated Script**: `python tools/commission_pumps.py` (outputs: `pump_calibration.json`)
- With options: `--pump ph_up` (specific pump), `--skip-guards`, `--auto-advance`

**Prerequisites**:
- Graduated cylinders or scale
- Pumps primed with appropriate fluids (or water for testing)

**Manual Commands** (or use automated script above):
```bash
# List available pumps
curl http://localhost:8080/calib/dose/pumps | jq '.pumps[] | {key, relay, ml_per_sec}'

# For each pump (example: ph_up)
PUMP="ph_up"

# Prime pump (5 seconds)
curl -X POST http://localhost:8080/calib/dose/prime -H "Content-Type: application/json" \
  -d "{\"pump_id\": \"$PUMP\", \"duration_sec\": 5}"

# Calibration run (30 seconds into graduated cylinder)
curl -X POST http://localhost:8080/calib/dose/run -H "Content-Type: application/json" \
  -d "{\"pump_id\": \"$PUMP\", \"duration_sec\": 30}"

# Measure dispensed volume, then commit (example: 15.2 mL)
curl -X POST http://localhost:8080/calib/dose/commit -H "Content-Type: application/json" \
  -d "{\"pump_id\": \"$PUMP\", \"volume_ml\": 15.2}"

# Verify updated rate
curl http://localhost:8080/calib/dose/pumps | jq ".pumps[] | select(.key==\"$PUMP\") | .ml_per_sec"

# Repeat for grow, micro, bloom pumps

# Test safety guards
# 1. Excessive dose (press_cap)
curl -X POST http://localhost:8080/api/ph/dose -H "Content-Type: application/json" \
  -d '{"ml": 999}'  # Should be blocked

# 2. Daily cap enforcement (track multiple doses)

# 3. E-STOP blocks dosing
curl -X POST http://localhost:8080/api/relays/estop/toggle
curl -X POST http://localhost:8080/api/ph/dose -H "Content-Type: application/json" \
  -d '{"ml": 5}'  # Should be blocked
curl -X POST http://localhost:8080/api/relays/estop/toggle  # Release

# Final snapshot
curl http://localhost:8080/api/commissioning/snapshot > snapshot_pumps_calibrated.json
```

**Acceptance Criteria**:
- [ ] All pumps show ml_per_sec > 0
- [ ] Volume accuracy within ±5% of measured
- [ ] press_cap enforced (single dose limit)
- [ ] daily_cap enforced (total daily limit)
- [ ] pH/EC guards block dosing when targets met
- [ ] Stale sensor blocks dosing (age >5min)
- [ ] E-STOP blocks all dosing operations

## Final Validation

### Commissioning Readiness (Strict)
```bash
# All systems operational
python tools/commissioning_readiness.py --compact --require-sensors --require-ph
# Exit code 0 = fully ready

# Generate final snapshot
curl http://localhost:8080/api/commissioning/snapshot > snapshot_final.json
```

### Data Archive
```bash
# Collect all snapshots
mkdir -p docs/commissioning_$(date +%Y%m%d)
mv snapshot_*.json docs/commissioning_$(date +%Y%m%d)/

# Query frontend logs for errors during commissioning
curl "http://localhost:8080/api/frontend/logs?level=error&hours=24" > commissioning_errors.json
```

### Issue Closure
After successful commissioning:
- Close issue #59 (Sensor Health) with snapshot evidence
- Close issue #56 (pH Calibration) with calibration flags
- Close issue #57 (EC Calibration) with status confirmation
- Close issue #58 (Relay Safety) with test results
- Close issue #60 (Dosing Pumps) with pump rates

## Troubleshooting

### Sensors Not Detected
```bash
# Check I²C device permissions
ls -l /dev/i2c-1
sudo usermod -a -G i2c pi  # Add pi user to i2c group

# Verify EZO addresses via i2cdetect
i2cdetect -y 1

# Check sensor poller logs
journalctl -u rdwc-sensors.service -n 50
```

### Calibration Lock Issues
```bash
# Check lock file
ls -l /tmp/rdwc_calib.lock

# Remove stale lock if needed (ensure poller not reading)
sudo rm /tmp/rdwc_calib.lock
```

### Relay Guard Not Initialized
```bash
# Restart API service
sudo systemctl restart rdwc.service

# Verify guard initialization in logs
journalctl -u rdwc.service -n 50 | grep -i guard
```

### Temperature Compensation Not Applied
```bash
# Check temp_comp fields in sensor response
curl http://localhost:8080/api/sensors | jq '.temp_comp_applied, .temp_comp_reason'

# Throttling requires ΔT ≥ 0.2°C or ≥60s since last update
# Wait 60s then retry
```

## Notes

- **Hardware is connected** per user confirmation
- Development environment (Windows) lacks I²C/GPIO hardware
- All commissioning steps require Pi deployment
- Use snapshot endpoints to capture state at each milestone
- Compare snapshots to track calibration progress
- Frontend log retention active (7 days, 5000 row cap)
