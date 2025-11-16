# Automated Commissioning Scripts Documentation

This document provides detailed documentation for the automated hardware commissioning scripts that replace manual curl-based procedures.

## Overview

The automated commissioning system consists of 6 Python scripts that systematically validate and calibrate hardware components:

1. **commission_sensors.py** - Sensor health validation
2. **commission_ph.py** - pH calibration (3-point)
3. **commission_ec.py** - EC calibration (1 or 2-point)
4. **commission_relays.py** - Relay safety tests
5. **commission_pumps.py** - Pump calibration and safety guards
6. **commission_all.py** - Orchestrator for all phases

All scripts share a common utility library (`commission_utils.py`) that provides:
- Robust HTTP client with retry logic
- Structured JSON output
- Progress indicators and colored terminal output
- Error handling and recommendations

## Installation

### Dependencies

Add to your Python environment:

```bash
pip install requests>=2.31.0 jsonschema>=4.17.0 rich>=13.0.0
```

Or install from `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Environment Configuration

Configure the API base URL (default: `http://localhost:8080`):

```bash
export RDWC_API_URL="http://localhost:8080"
```

For pH calibration, enable calibration mode:

```bash
export CALIB_ENABLE=1
```

## Quick Start

### Full Automated Commissioning

Run all phases in sequence:

```bash
sudo python tools/commission_all.py
```

This will:
1. Validate sensors
2. Calibrate pH (interactive prompts)
3. Calibrate EC (interactive prompts)
4. Test relay safety
5. Calibrate dosing pumps (interactive prompts)
6. Generate comprehensive report
7. Archive results to `docs/commissioning_YYYYMMDD/`

### Individual Phases

Run specific phases as needed:

```bash
# Sensor validation (fast, no prompts)
python tools/commission_sensors.py

# pH calibration (requires buffers and user interaction)
python tools/commission_ph.py

# EC calibration (requires calibration solution)
python tools/commission_ec.py --k-value 1.0

# Relay safety tests (automated)
python tools/commission_relays.py

# Pump calibration (requires measuring dispensed volume)
python tools/commission_pumps.py
```

## Script Reference

### 1. commission_sensors.py

**Purpose**: Validate I²C sensors, poller service, data freshness, and health states.

**Usage**:
```bash
python tools/commission_sensors.py [options]
```

**Options**:
- `--api-url URL` - API base URL (default: http://localhost:8080)
- `--output FILE` - Output JSON file (default: sensor_report.json)
- `--max-age SECONDS` - Maximum sensor data age (default: 60)
- `--test-power-cycle` - Test sensor power cycling if configured
- `--no-color` - Disable colored output

**Exit Codes**:
- `0` - All sensors operational
- `1` - I²C device missing
- `2` - Sensors offline/stale
- `3` - Service not running

**Example Output** (sensor_report.json):
```json
{
  "metadata": {
    "script": "commission_sensors.py",
    "version": "1.0.0",
    "timestamp": "2025-11-16T13:45:00Z",
    "host": {"hostname": "raspberrypi", "platform": "linux"}
  },
  "config": {
    "api_url": "http://localhost:8080",
    "max_age_seconds": 60
  },
  "results": {
    "i2c_device": {"exists": true, "path": "/dev/i2c-1"},
    "sensor_addresses": {
      "success": true,
      "addresses_found": [
        {"name": "pH", "address": "0x63"},
        {"name": "EC", "address": "0x64"},
        {"name": "RTD", "address": "0x66"}
      ]
    },
    "sensor_poller": {"success": true, "running": true},
    "sensor_data": {
      "success": true,
      "online": true,
      "age_seconds": 5,
      "health_state": "green"
    }
  },
  "errors": [],
  "recommendations": []
}
```

**Troubleshooting**:
- **I²C device not found**: Ensure I²C is enabled (`sudo raspi-config`)
- **Sensors offline**: Check wiring, run `i2cdetect -y 1`
- **Poller not running**: Start with `sudo systemctl start rdwc-sensors`

---

### 2. commission_ph.py

**Purpose**: Automate 3-point pH calibration workflow (mid/low/high points).

**Usage**:
```bash
python tools/commission_ph.py [options]
```

**Options**:
- `--api-url URL` - API base URL
- `--output FILE` - Output JSON file (default: ph_calibration.json)
- `--auto-advance` - Skip interactive prompts (testing mode)
- `--skip-reservoir` - Skip final accuracy validation
- `--timeout SECONDS` - Stability wait timeout (default: 45)
- `--threshold VALUE` - Stability threshold (default: 0.03)
- `--no-color` - Disable colored output

**Exit Codes**:
- `0` - Calibration successful
- `1` - Calibration capabilities check failed
- `2` - Calibration procedure failed
- `3` - Accuracy validation failed

**Workflow**:
1. Check calibration capabilities
2. Clear existing calibration
3. **Mid-point (pH 7.00)**:
   - Place probe in pH 7.00 buffer
   - Wait for stability (±0.03 over 45s)
   - Execute calibration
4. **Low-point (pH 4.01)**:
   - Place probe in pH 4.01 buffer
   - Wait for stability
   - Execute calibration
5. **High-point (pH 10.00)**:
   - Place probe in pH 10.00 buffer
   - Wait for stability
   - Execute calibration
6. Verify calibration flags
7. Optional: Check accuracy vs reference meter (±0.05 tolerance)

**Example**:
```bash
# Interactive mode (prompts for buffer placement)
export CALIB_ENABLE=1
python tools/commission_ph.py

# Automated mode for testing (skip prompts and accuracy check)
python tools/commission_ph.py --auto-advance --skip-reservoir
```

**Tips**:
- Use fresh buffer solutions (< 6 months old)
- Clean probe between buffers
- Allow 30-60 seconds for probe to equilibrate in each buffer
- Store probe in storage solution between calibrations

---

### 3. commission_ec.py

**Purpose**: Automate EC K-value configuration and calibration (1 or 2-point).

**Usage**:
```bash
python tools/commission_ec.py [options]
```

**Options**:
- `--api-url URL` - API base URL
- `--output FILE` - Output JSON file (default: ec_calibration.json)
- `--k-value VALUE` - Probe K-value constant (default: 1.0)
- `--two-point` - Enable two-point calibration (low + high)
- `--skip-accuracy` - Skip reservoir accuracy check
- `--auto-advance` - Skip interactive prompts (testing mode)
- `--no-color` - Disable colored output

**Exit Codes**:
- `0` - Calibration successful
- `1` - K-value configuration failed
- `2` - Calibration procedure failed
- `3` - Accuracy validation failed

**Workflow**:
1. Set probe K-value (typically 1.0)
2. Clear existing calibration
3. **Low-point (1413 µS/cm)**:
   - Place probe in 1413 µS/cm solution
   - Wait for stability (30s)
   - Execute calibration
4. **High-point (12880 µS/cm)** (optional with `--two-point`):
   - Place probe in 12880 µS/cm solution
   - Wait for stability
   - Execute calibration
5. Verify calibration status
6. Optional: Check accuracy vs reference meter (±50 µS/cm)

**Example**:
```bash
# Standard 1-point calibration
python tools/commission_ec.py --k-value 1.0

# 2-point calibration for better accuracy
python tools/commission_ec.py --k-value 1.0 --two-point

# Testing mode
python tools/commission_ec.py --auto-advance --skip-accuracy
```

**K-Value Selection**:
- K=0.1: High conductivity (> 10 mS/cm)
- K=1.0: Most common, medium range (100-10,000 µS/cm)
- K=10: Low conductivity (< 100 µS/cm)

---

### 4. commission_relays.py

**Purpose**: Validate relay safety mechanisms (E-STOP, cooldowns, protected relays).

**Usage**:
```bash
python tools/commission_relays.py [options]
```

**Options**:
- `--api-url URL` - API base URL
- `--output FILE` - Output JSON file (default: relay_safety.json)
- `--no-color` - Disable colored output

**Exit Codes**:
- `0` - All safety checks pass
- `1` - E-STOP failure
- `2` - Cooldown violation
- `3` - Protected relay bypass

**Tests Performed**:
1. **E-STOP Toggle**:
   - Activate E-STOP
   - Verify all relays turn OFF
   - Attempt relay operation (should be blocked)
   - Deactivate E-STOP
   - Verify restoration

2. **Mode Transitions**:
   - Switch to manual mode
   - Switch to auto mode
   - Verify clean transitions

3. **Protected Relays**:
   - Test lights relay with non-whitelisted reason (should block)
   - Test chiller_power relay with non-whitelisted reason (should block)

4. **Cooldown Enforcement**:
   - Turn relay ON
   - Immediately try to turn OFF (should be blocked by cooldown)
   - Wait for cooldown expiry
   - Verify OFF operation succeeds

5. **Service Restart** (informational):
   - Check current relay states
   - Note: Full test requires manual service restart

**Example**:
```bash
python tools/commission_relays.py
```

---

### 5. commission_pumps.py

**Purpose**: Calibrate dosing pumps and test safety guards.

**Usage**:
```bash
python tools/commission_pumps.py [options]
```

**Options**:
- `--api-url URL` - API base URL
- `--output FILE` - Output JSON file (default: pump_calibration.json)
- `--pump ID` - Calibrate specific pump (e.g., ph_up, grow, micro, bloom)
- `--prime-sec SECONDS` - Prime duration (default: 5)
- `--run-sec SECONDS` - Calibration run duration (default: 30)
- `--skip-guards` - Skip safety guard tests
- `--auto-advance` - Skip interactive prompts (testing mode)
- `--no-color` - Disable colored output

**Exit Codes**:
- `0` - All pumps calibrated successfully
- `1` - Failed to discover pumps
- `2` - Calibration procedure failed
- `3` - Safety guard tests failed

**Workflow (per pump)**:
1. Prime pump (default: 5 seconds)
2. Run calibration cycle (default: 30 seconds into graduated cylinder)
3. Prompt user for measured volume
4. Calculate ml/s rate
5. Commit calibration
6. Verify updated rate

**Safety Guard Tests**:
1. **press_cap**: Reject excessive single dose (999 ml)
2. **E-STOP**: Verify E-STOP blocks all dosing
3. **pH/EC guards**: (informational - requires specific conditions)

**Example**:
```bash
# Calibrate all pumps
python tools/commission_pumps.py

# Calibrate specific pump
python tools/commission_pumps.py --pump ph_up

# Custom run duration
python tools/commission_pumps.py --pump grow --run-sec 60

# Testing mode (auto volume)
python tools/commission_pumps.py --auto-advance --skip-guards
```

**Tips**:
- Use distilled water for testing
- Have graduated cylinders ready (50-100 ml)
- Record actual dispensed volumes accurately
- Typical rates: 0.3-0.6 ml/s for peristaltic pumps

---

### 6. commission_all.py

**Purpose**: Orchestrate all 5 phases with comprehensive reporting.

**Usage**:
```bash
python tools/commission_all.py [options]
```

**Options**:
- `--api-url URL` - API base URL
- `--phase PHASE` - Run specific phase only (sensors|ph|ec|relays|pumps)
- `--continue-on-error` - Don't abort on phase failure
- `--dry-run` - Validate without execution
- `--auto-advance` - Use auto-advance for pH/EC calibration
- `--skip-reservoir` - Skip pH reservoir accuracy check
- `--skip-accuracy` - Skip EC accuracy check
- `--no-archive` - Don't archive reports to docs/
- `--no-color` - Disable colored output

**Exit Codes**:
- `0` - All phases completed successfully
- `1-5` - Specific phase failed (1=sensors, 2=pH, 3=EC, 4=relays, 5=pumps)
- `99` - Multiple phases failed

**Workflow**:
1. Run Phase 1: Sensors
2. Run Phase 2: pH (if Phase 1 succeeds)
3. Run Phase 3: EC (if Phase 2 succeeds)
4. Run Phase 4: Relays (if Phase 3 succeeds)
5. Run Phase 5: Pumps (if Phase 4 succeeds)
6. Archive reports to `docs/commissioning_YYYYMMDD/`
7. Generate comprehensive JSON report
8. Generate human-readable summary

**Output Files**:
- `commissioning_report_YYYYMMDD_HHMMSS.json` - Comprehensive JSON report
- `commissioning_summary.txt` - Human-readable summary
- `docs/commissioning_YYYYMMDD/` - Archived phase reports

**Example**:
```bash
# Full commissioning (interactive)
sudo python tools/commission_all.py

# Single phase
python tools/commission_all.py --phase sensors

# Continue on errors (run all phases regardless)
python tools/commission_all.py --continue-on-error

# Dry run (validation only)
python tools/commission_all.py --dry-run

# Testing mode
python tools/commission_all.py --auto-advance --skip-reservoir --skip-accuracy
```

## JSON Output Schema

All scripts produce structured JSON output with this schema:

```json
{
  "metadata": {
    "script": "script_name.py",
    "version": "1.0.0",
    "timestamp": "2025-11-16T13:45:00Z",
    "host": {
      "hostname": "raspberrypi",
      "platform": "linux",
      "python_version": "3.9.2"
    }
  },
  "config": {
    // Script-specific configuration
  },
  "results": {
    // Script-specific results
  },
  "errors": [
    // List of errors encountered
  ],
  "recommendations": [
    // Actionable recommendations
  ]
}
```

## Error Handling

### Network Errors

All scripts use retry logic (3 attempts, exponential backoff) for HTTP requests:

```python
# Automatic retry on:
# - Connection errors
# - Timeouts (default: 30s per request)
# - Server errors (500, 502, 503, 504)
# - Rate limiting (429)
```

### Hardware Errors

Scripts detect and report hardware-specific errors:

- **I²C errors**: Device not found, sensor communication failures
- **GPIO errors**: Pin conflicts, permission issues
- **Timeout errors**: Operations exceeding configured timeouts

### Exit Code Reference

| Exit Code | Meaning | Action |
|-----------|---------|--------|
| 0 | Success | Continue to next phase |
| 1 | Critical failure (hardware/config) | Fix before continuing |
| 2 | Procedure failure | Retry with corrections |
| 3 | Validation failure | Check calibration/accuracy |

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Hardware Commissioning

on:
  workflow_dispatch:
    inputs:
      phase:
        description: 'Commissioning phase'
        required: false
        default: 'all'
        type: choice
        options:
          - all
          - sensors
          - relays

jobs:
  commission:
    runs-on: self-hosted  # Raspberry Pi runner
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run commissioning
        run: |
          if [ "${{ github.event.inputs.phase }}" == "all" ]; then
            sudo python tools/commission_all.py --auto-advance
          else
            python tools/commission_${{ github.event.inputs.phase }}.py
          fi
      
      - name: Upload reports
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: commissioning-reports
          path: |
            *_report.json
            *_calibration.json
            *_safety.json
            commissioning_summary.txt
```

### Shell Script Example

```bash
#!/bin/bash
# automated_commission.sh

set -e

RDWC_API_URL="${RDWC_API_URL:-http://localhost:8080}"
LOG_DIR="/var/log/rdwc/commissioning"

mkdir -p "$LOG_DIR"

# Run commissioning
python tools/commission_all.py \
  --api-url "$RDWC_API_URL" \
  --auto-advance \
  --skip-reservoir \
  --skip-accuracy \
  2>&1 | tee "$LOG_DIR/commission_$(date +%Y%m%d_%H%M%S).log"

EXIT_CODE=$?

# Alert on failure
if [ $EXIT_CODE -ne 0 ]; then
  echo "Commissioning failed with exit code $EXIT_CODE" | \
    mail -s "RDWC Commissioning Failed" admin@example.com
fi

exit $EXIT_CODE
```

## Troubleshooting Guide

### Common Issues

#### 1. Module Not Found Errors

**Problem**: `ModuleNotFoundError: No module named 'requests'`

**Solution**:
```bash
pip install requests jsonschema rich
```

#### 2. Permission Denied

**Problem**: `/dev/i2c-1: Permission denied`

**Solution**:
```bash
sudo usermod -a -G i2c $USER
sudo chmod 666 /dev/i2c-1
```

Or run with sudo:
```bash
sudo python tools/commission_sensors.py
```

#### 3. Calibration Lock Errors

**Problem**: `Calibration lock file exists`

**Solution**:
```bash
# Stop sensor poller temporarily
sudo systemctl stop rdwc-sensors

# Remove stale lock
sudo rm /tmp/rdwc_calib.lock

# Run calibration
python tools/commission_ph.py

# Restart poller
sudo systemctl start rdwc-sensors
```

#### 4. API Connection Refused

**Problem**: `Connection refused to http://localhost:8080`

**Solution**:
```bash
# Check API service
sudo systemctl status rdwc.service

# Start if needed
sudo systemctl start rdwc.service

# Or specify different URL
export RDWC_API_URL="http://raspberrypi.local:8080"
python tools/commission_sensors.py
```

#### 5. Unstable pH Readings

**Problem**: pH reading never stabilizes

**Solution**:
- Increase timeout: `--timeout 90`
- Increase threshold: `--threshold 0.05`
- Clean probe thoroughly
- Use fresh buffer solutions
- Allow longer equilibration time

#### 6. EC Calibration Fails

**Problem**: EC calibration not accepted

**Solution**:
- Verify K-value is correct for probe type
- Ensure solution temperature is stable
- Check solution expiration date
- Clean probe with isopropyl alcohol
- Verify probe is fully submerged

## Best Practices

### Before Commissioning

1. **Prepare Materials**:
   - Fresh calibration solutions (< 6 months old)
   - Graduated cylinders (50-100 ml)
   - Distilled water for rinsing
   - Paper towels
   - Reference meter (optional, for accuracy checks)

2. **System Check**:
   ```bash
   # Verify services
   sudo systemctl status rdwc.service
   sudo systemctl status rdwc-sensors.service
   
   # Check I²C
   i2cdetect -y 1
   
   # Test API
   curl http://localhost:8080/api/sensors
   ```

3. **Environment**:
   - Stable temperature (20-25°C)
   - No direct sunlight on solutions
   - Clean work area

### During Commissioning

1. **Follow Order**: Sensors → pH → EC → Relays → Pumps
2. **Allow Settling Time**: 30-60 seconds between buffer changes
3. **Rinse Probes**: Distilled water between buffers/solutions
4. **Record Results**: Save JSON reports for future reference
5. **Verify Each Step**: Check output before proceeding

### After Commissioning

1. **Archive Reports**:
   ```bash
   mkdir -p ~/commissioning_history
   cp *.json ~/commissioning_history/
   ```

2. **Validate in UI**:
   - Check sensor readings
   - Verify relay controls
   - Test dosing buttons

3. **Document Changes**:
   - Record calibration dates
   - Note any anomalies
   - Update maintenance log

## Support

### Getting Help

1. **Check Documentation**:
   - This file: `docs/COMMISSIONING_AUTOMATION.md`
   - Checklist: `PI_COMMISSIONING_CHECKLIST.md`
   - README: `README.md`

2. **Review Logs**:
   ```bash
   # API logs
   journalctl -u rdwc.service -n 100
   
   # Sensor poller logs
   journalctl -u rdwc-sensors.service -n 100
   ```

3. **Check JSON Reports**:
   - Review `errors` array
   - Check `recommendations` array
   - Examine detailed `results` object

4. **GitHub Issues**:
   - Search existing issues: https://github.com/collinerasmus/RDWC-v4/issues
   - Create new issue with JSON report attached

### Reporting Bugs

When reporting issues, include:
1. Full JSON report output
2. Script command used
3. System information (`uname -a`)
4. Python version (`python --version`)
5. API service logs (last 50 lines)
6. Screenshots of any UI errors

## Version History

### 1.0.0 (2025-11-16)
- Initial release
- All 6 commissioning scripts
- Shared utilities library
- Comprehensive test suite
- Full documentation

## License

This project follows the same license as the main RDWC-v4 repository.
