# RDWC-v4 Deployment Verification Guide

This guide provides step-by-step verification procedures to ensure the Pi deployment is properly synced with the latest code, particularly focusing on the circulation safety interlock and E-STOP UI consolidation features.

## Quick Verification (PowerShell)

From your Windows machine:

```powershell
# Set Pi connection details
$env:PI_HOST = "192.168.88.49"
$env:PI_USER = "pi"

# Run verification script
.\deploy\verify_pi_sync.ps1
```

This script will check:
- ✓ Current Git commit on Pi
- ✓ Services running (rdwc.service, rdwc-sensors.service)
- ✓ `/api/controllers/status` endpoint correctness
- ✓ State field fix (commit 8bcad99) is present
- ✓ E-STOP status consistency

## Manual Verification Steps

### 1. Check Pi Git Status

SSH to the Pi and verify the current commit:

```bash
ssh pi@192.168.88.49
cd ~/RDWC-v4
git branch --show-current  # Should show: main
git rev-parse --short HEAD # Should match your local commit
git log --oneline -5       # Review recent commits
```

### 2. Verify Services Are Running

```bash
# Check service status
systemctl status rdwc.service
systemctl status rdwc-sensors.service

# Check recent logs
journalctl -u rdwc.service -n 20 --no-pager
journalctl -u rdwc-sensors.service -n 20 --no-pager
```

### 3. API Endpoint Verification

#### 3.1 Controllers Status Endpoint

From your Windows machine or directly on Pi:

```powershell
# PowerShell
$resp = Invoke-RestMethod http://192.168.88.49:8080/api/controllers/status
$resp.controllers.circulation | ConvertTo-Json
```

```bash
# Bash (on Pi or any Linux machine)
curl -s http://192.168.88.49:8080/api/controllers/status | jq '.controllers.circulation'
```

**Expected output:**
```json
{
  "mode": "auto",
  "main_pump": true,    # boolean (true/false)
  "chiller_pump": false # boolean (true/false)
}
```

**⚠️ Common Issue:** If values show as `null` or are missing when pump is ON, the Pi is missing commit 8bcad99 (state field fix).

#### 3.2 Relays Status Endpoint (for comparison)

```bash
curl -s http://192.168.88.49:8080/api/relays/status | jq '.relays | {main_pump, chiller_pump}'
```

**Expected output:**
```json
{
  "main_pump": {
    "pin_bcm": 26,
    "active_low": true,
    "is_on": true,
    "label": "Main Pump"
  },
  "chiller_pump": {
    "pin_bcm": 16,
    "active_low": true,
    "is_on": false,
    "label": "Chiller Pump"
  }
}
```

**Verification:** The `circulation.main_pump` value from `/api/controllers/status` should match `relays.main_pump.is_on` from `/api/relays/status`.

**Note:** The `/api/relays/status` endpoint returns `is_on` as a field name (translated from the internal `state` field for UI compatibility).

### 4. Python Verification Script

Run the comprehensive verification script:

```bash
# On Pi
cd ~/RDWC-v4
python3 tools/verify_circulation_interlock.py --base http://localhost:8080

# From remote machine
python3 tools/verify_circulation_interlock.py --base http://192.168.88.49:8080
```

This script will:
- Compare circulation pump states between endpoints
- Verify E-STOP status consistency
- Provide detailed diagnostics if issues are found

### 5. UI Verification

Open the web interface: http://192.168.88.49:8080

**E-STOP Button Verification:**
- ✓ Single E-STOP button in the header of each tab
- ✓ No duplicate E-STOP banners in System tab content area
- ✓ E-STOP state updates within 3 seconds across all tabs
- ✓ Button shows "ACTIVE" state when engaged (red, different styling)

**Circulation Controller Verification:**
1. Navigate to any tab (Overview, Sensors, etc.)
2. Turn ON main pump
3. Turn ON chiller
4. Verify: Chiller pump auto-starts
5. Verify: Banner shows "✅ INTERLOCK ACTIVE" (if UI includes this)
6. Try turning OFF chiller pump directly
7. Verify: Operation blocked with error message
8. Turn OFF chiller
9. Verify: Chiller pump shows "STANDBY"

### 6. Test Scenarios

#### Scenario A: Normal Operation
1. E-STOP is OFF (released)
2. Turn ON main pump → Success
3. Turn ON chiller → Chiller pump auto-starts
4. All indicators show correct states

#### Scenario B: E-STOP Engaged
1. Toggle E-STOP → All relays turn OFF
2. Verify: All tabs show E-STOP active within 3 seconds
3. Try turning ON main pump → Blocked
4. Release E-STOP
5. Verify: Normal operation resumes

#### Scenario C: Safety Interlock
1. Main pump OFF
2. Try turning ON chiller → Blocked (requires main pump)
3. Turn ON main pump
4. Turn ON chiller → Success, chiller pump auto-starts
5. Chiller ON, try turning OFF chiller pump → Blocked
6. Turn OFF chiller first → Pump can then be turned OFF

## Update Pi to Latest Code

If verification fails, update the Pi:

### Option 1: Using PowerShell Script (Recommended)

```powershell
.\deploy\refresh_api.ps1 -PiHost 192.168.88.49 -PiUser pi
```

### Option 2: Manual Update

SSH to Pi and run:

```bash
cd ~/RDWC-v4
git fetch origin
git reset --hard origin/main
sudo systemctl restart rdwc.service
sudo systemctl restart rdwc-sensors.service

# Wait a moment and verify
sleep 3
systemctl status rdwc.service --no-pager
systemctl status rdwc-sensors.service --no-pager
```

### Option 3: Atomic Update with Verification

```bash
cd ~/RDWC-v4
echo "Current commit: $(git rev-parse --short HEAD)"
git fetch origin
git reset --hard origin/main
echo "New commit: $(git rev-parse --short HEAD)"
sudo rm -f /tmp/rdwc_calib.lock
sudo systemctl restart rdwc.service
sudo systemctl restart rdwc-sensors.service
sleep 3
curl -s http://localhost:8080/api/controllers/status | jq '.controllers.circulation'
```

## Troubleshooting

### Issue: Controllers Status Shows Wrong Values

**Symptom:** `/api/controllers/status` shows `main_pump: false` when pump is actually ON, or values don't match between endpoints.

**Cause:** Controller endpoint implementation is incorrect or Pi has old code.

**Fix:** 
- Update Pi to latest main branch
- Verify `app/main.py` lines ~1211-1212 correctly read from `get_relay_status()` using `.get("state", False)`
- Restart services after update

### Issue: Services Not Starting

**Check logs:**
```bash
journalctl -u rdwc.service -n 50 --no-pager
journalctl -u rdwc-sensors.service -n 50 --no-pager
```

**Common causes:**
- Python import errors (missing dependencies)
- I²C permission issues
- Port already in use (8080)
- Database lock issues

**Fix:**
```bash
# Reinstall dependencies
cd ~/RDWC-v4
pip install -r requirements.txt

# Check ports
sudo netstat -tlnp | grep 8080

# Reset database locks
sudo rm -f /tmp/rdwc_calib.lock /run/rdwc_sensors.lock
```

### Issue: E-STOP UI Not Updating

**Symptom:** E-STOP toggle doesn't update across tabs or takes >3 seconds.

**Check:**
1. Browser console for JS errors (F12)
2. Ensure `estop_store.js` exists (if UI consolidation is implemented)
3. Check if periodic polling is working (should poll every 2-3 seconds)

**Fix:**
- Clear browser cache (Ctrl+F5)
- Check if `global_health.js` or `relays_v2.js` has E-STOP polling logic

## Success Criteria

All of the following should be true:

- ✅ Pi is on `main` branch (or expected branch)
- ✅ All services are `active (running)`
- ✅ `/api/controllers/status` returns correct boolean pump states
- ✅ Pump states match between `/api/controllers/status` and `/api/relays/status`
- ✅ E-STOP status is consistent across endpoints
- ✅ E-STOP button appears once per tab (in header)
- ✅ E-STOP toggles update all tabs within 3 seconds
- ✅ Circulation interlock prevents unsafe operations
- ✅ Chiller auto-starts chiller pump when activated
- ✅ No Python errors in service logs
- ✅ Sensor readings are fresh (<60 seconds old)

## Related Documentation

- [PI_COMMISSIONING_CHECKLIST.md](../PI_COMMISSIONING_CHECKLIST.md) - Initial Pi setup and commissioning
- [DEPLOYMENT_TROUBLESHOOTING.md](../DEPLOYMENT_TROUBLESHOOTING.md) - General deployment troubleshooting
- [SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) - System architecture overview

## Automation Scripts

| Script | Purpose |
|--------|---------|
| `deploy/verify_pi_sync.ps1` | Comprehensive Pi sync verification (PowerShell) |
| `tools/verify_circulation_interlock.py` | Circulation interlock and controller status verification (Python) |
| `tools/deploy_verify.py` | General deployment verification - runs key API endpoints and summarizes acceptance criteria (Python) |
| `deploy/refresh_api.ps1` | Deploy latest code to Pi (PowerShell) |

## Quick Reference Commands

```bash
# Check Pi status
ssh pi@192.168.88.49 'cd RDWC-v4 && git log --oneline -3 && systemctl is-active rdwc.service rdwc-sensors.service'

# Quick API test
curl -s http://192.168.88.49:8080/api/controllers/status | jq '{estop, circulation: .controllers.circulation}'

# Service restart
ssh pi@192.168.88.49 'sudo systemctl restart rdwc.service rdwc-sensors.service'

# Tail logs
ssh pi@192.168.88.49 'journalctl -u rdwc.service -f'
```
