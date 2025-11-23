# Pi Deployment Review - Branch Validation Guide

## Overview
This document provides validation steps for deploying and testing feature branches on the Raspberry Pi hardware.

**Current Pi Configuration**:
- Host: 192.168.88.49
- UI: http://192.168.88.49:8080
- Services: `rdwc.service`, `rdwc-sensors.service`
- Active Branch: `copilot/continue-fix-midnight-schedule`

## Branch: copilot/continue-fix-midnight-schedule

### Features Added
1. **Chiller Interlock Status API** - Exposes interlock conditions via `/api/chiller/status`
2. **Midnight Schedule Logic Tests** - Validates edge-only behavior, no phantom edges
3. **Relay POST Performance** - Investigated and validated <50ms response times

### Deployment Steps

#### 1. Connect to Pi
```bash
ssh pi@192.168.88.49
```

#### 2. Deploy Branch
```bash
cd RDWC-v4
git fetch origin
git checkout copilot/continue-fix-midnight-schedule
git pull
sudo systemctl restart rdwc.service
```

#### 3. Verify Service Status
```bash
# Check main service
sudo systemctl status rdwc.service

# Check sensor poller
sudo systemctl status rdwc-sensors.service

# View recent logs
sudo journalctl -u rdwc.service -n 50 --no-pager
sudo journalctl -u rdwc-sensors.service -n 50 --no-pager
```

### API Validation Commands

#### Basic Health Checks
```bash
# Version and build info
curl -s http://192.168.88.49:8080/api/version | jq

# E-STOP status
curl -s http://192.168.88.49:8080/api/estop | jq

# Controller modes
curl -s http://192.168.88.49:8080/api/controllers/status | jq
```

#### Chiller Interlock Validation
```bash
# Get chiller status with interlock details
curl -s http://192.168.88.49:8080/api/chiller/status | jq

# Expected fields in response:
# - interlock_ok: boolean
# - interlock_details.main_pump_on: boolean
# - interlock_details.chiller_pump_on: boolean
# - interlock_details.chiller_running: boolean
# - interlock_details.auto_enabled: boolean
# - interlock_details.violations: null or array of strings
```

**Expected Output (Safe State)**:
```json
{
  "interlock_ok": true,
  "interlock_details": {
    "main_pump_on": true,
    "chiller_pump_on": true,
    "chiller_running": false,
    "auto_enabled": false,
    "violations": null
  },
  "is_running": false,
  "target_temp": 19.0,
  "current_temp": 21.5,
  ...
}
```

**Expected Output (Violation State)**:
```json
{
  "interlock_ok": false,
  "interlock_details": {
    "main_pump_on": false,
    "chiller_pump_on": true,
    "chiller_running": true,
    "auto_enabled": true,
    "violations": ["main_pump_off"]
  },
  ...
}
```

#### Relay Performance Test
```bash
# Test relay endpoint response time
curl -w "@curl-format.txt" -o /dev/null -s \
  -X POST http://192.168.88.49:8080/relay/set \
  -H "Content-Type: application/json" \
  -d '{"name":"dosing_grow","on":false}'
```

Create `curl-format.txt` first:
```bash
cat > curl-format.txt << 'EOF'
time_namelookup:    %{time_namelookup}s\n
time_connect:       %{time_connect}s\n
time_starttransfer: %{time_starttransfer}s\n
time_total:         %{time_total}s\n
EOF
```

**Expected**: `time_total` should be < 2.0s (typically < 0.5s)

#### Sensor Data Validation
```bash
# Get sensor readings
curl -s http://192.168.88.49:8080/api/sensors | jq

# Check sensor poller status
curl -s http://192.168.88.49:8080/api/sensors/status | jq

# Expected: timestamp age < 60 seconds
```

### UI Validation Checklist

#### 1. Global UI Elements
- [ ] Single E-STOP button in header (not duplicated on tabs)
- [ ] System mode selector only on System tab
- [ ] No tab-level E-STOP buttons

#### 2. Chiller Tab
- [ ] Green "Interlock Active" banner visible when interlock_ok=true
- [ ] Red/Yellow warning if interlock_ok=false
- [ ] Current temp, target temp, and stage displayed
- [ ] Auto/Manual mode reflected correctly
- [ ] No redundant automation buttons

#### 3. Circulation Tab
- [ ] Main pump status badge (ON/OFF)
- [ ] Chiller pump status badge (ON/OFF)
- [ ] Mode chip shows AUTO or MANUAL
- [ ] Hold button functional

#### 4. Schedule Tab
- [ ] Lights schedule displays correctly
- [ ] ON time and OFF time shown
- [ ] Duration hours calculated correctly
- [ ] Preview shows next 48 hours

### Midnight Schedule Testing

#### Manual Edge Validation
Test that lights only trigger at exact schedule times:

```bash
# Get current schedule
curl -s http://192.168.88.49:8080/api/schedule | jq '.entries[] | select(.name=="grow_lights")'

# Monitor scheduler log for edges
sudo journalctl -u rdwc.service -f | grep -i "lights_schedule"
```

**Expected Behavior**:
- Exactly ONE `lights_schedule_on` event at ON time (s=0)
- Exactly ONE `lights_schedule_off` event at OFF time (s=0)
- Guard events (`schedule_guard_on/off`) at s=1..5
- NO phantom edges at midnight (00:00)

#### Test Midnight Crossing
Set lights schedule to span midnight (e.g., 20:00 - 04:00):

```bash
# Update lights schedule via settings
curl -X POST http://192.168.88.49:8080/api/settings/import \
  -H "Content-Type: application/json" \
  -d '{
    "schedule.lights_on_time": "20:00",
    "schedule.lights_duration_hours": "8"
  }'

# Monitor logs around midnight transition
sudo journalctl -u rdwc.service --since "23:50" --until "00:10" | grep lights
```

**Expected**:
- Lights turn ON at 20:00
- Lights stay ON through midnight (no spurious OFF)
- Lights turn OFF at 04:00 the next day
- No extra edges at 00:00

### Performance Monitoring

#### System Load
```bash
# Check CPU and memory
top -b -n 1 | head -20

# Check I/O wait
vmstat 1 5

# Check service resource usage
systemctl status rdwc.service | grep -A 5 "Memory\|CPU"
```

#### Database Health
```bash
# Check database locks
lsof ~/RDWC-v4/data/rdwc.db

# Check database size
ls -lh ~/RDWC-v4/data/rdwc.db

# Check recent sensor writes
sqlite3 ~/RDWC-v4/data/rdwc.db "SELECT COUNT(*) FROM readings WHERE ts_utc > $(date -d '1 hour ago' +%s);"
```

### Rollback Procedure

If issues are detected:

```bash
# Stop services
sudo systemctl stop rdwc.service
sudo systemctl stop rdwc-sensors.service

# Revert to previous branch/commit
cd RDWC-v4
git checkout <previous-commit-or-branch>

# Restart services
sudo systemctl start rdwc-sensors.service
sudo systemctl start rdwc.service

# Verify
curl -s http://192.168.88.49:8080/api/version
```

### Common Issues and Solutions

#### Issue: Interlock status not appearing
**Symptom**: `/api/chiller/status` missing `interlock_ok` field

**Solution**:
```bash
# Check branch is deployed
cd ~/RDWC-v4 && git branch --show-current

# Verify code is updated
grep -n "interlock_ok" ~/RDWC-v4/app/chiller_control.py

# Restart service
sudo systemctl restart rdwc.service
```

#### Issue: Relay POST timeouts
**Symptom**: UI relay controls slow or timing out

**Diagnosis**:
```bash
# Check system load
uptime

# Check for sensor poller conflicts
ps aux | grep sensor_poller

# Test endpoint directly
time curl -X POST http://192.168.88.49:8080/relay/set \
  -H "Content-Type: application/json" \
  -d '{"name":"dosing_grow","on":false}'
```

**See**: `docs/RELAY_POST_TIMEOUT_INVESTIGATION.md` for detailed analysis

#### Issue: Lights triggering extra edges
**Symptom**: Multiple ON/OFF events at midnight or schedule times

**Diagnosis**:
```bash
# Check scheduler log
sudo journalctl -u rdwc.service --since "1 hour ago" | grep lights_schedule | grep -v guard

# Should see exactly 2 non-guard events per day
```

### Acceptance Criteria

This branch is validated when:

- [x] All 191 tests pass in CI
- [ ] `/api/chiller/status` returns `interlock_ok` and `interlock_details`
- [ ] UI shows green banner when interlock conditions met
- [ ] Relay POST responds in < 2 seconds
- [ ] No phantom light edges at midnight in 24h observation
- [ ] Exactly 2 light edges per day (ON and OFF) in logs
- [ ] System services stable for 24h
- [ ] No errors in `journalctl` output

### Test Results Log

**Date**: _____________  
**Tester**: _____________  
**Branch Commit**: _____________

| Test | Pass/Fail | Notes |
|------|-----------|-------|
| API version check | [ ] | |
| Interlock status fields present | [ ] | |
| Relay POST < 2s | [ ] | |
| UI banner displays | [ ] | |
| Midnight edge test (24h) | [ ] | |
| System stability (24h) | [ ] | |
| Service logs clean | [ ] | |

### Related Documentation
- `docs/CHILLER_INTERLOCK_DOCUMENTATION.md` - Interlock system details
- `docs/RELAY_POST_TIMEOUT_INVESTIGATION.md` - Performance analysis
- `DEPLOYMENT_TROUBLESHOOTING.md` - General deployment issues
- `deploy/DEPLOYMENT_SUMMARY.md` - Deployment process overview

---
**Last Updated**: 2025-11-23  
**Branch**: copilot/continue-fix-midnight-schedule  
**Status**: Ready for validation
