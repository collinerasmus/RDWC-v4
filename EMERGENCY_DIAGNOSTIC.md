# EMERGENCY DIAGNOSTIC - System Not Responding
**Date:** 2025-11-24
**HMI IP:** 192.168.88.33
**Pi IP:** 192.168.88.49

## Current Situation

**Problem:** Cannot control ANYTHING - even buttons that should work regardless of mode
- Manual button doesn't change state
- No relay control working
- System appears non-responsive

## Immediate Diagnostic Steps

### Step 1: Run Diagnostic on Pi

**From Windows PowerShell:**
```powershell
# Run diagnostic script
ssh pi@192.168.88.49 'bash -s' < tools\diagnose_pi.sh > pi_diagnostic.txt

# Or manually SSH and run commands:
ssh pi@192.168.88.49
```

**Once on Pi, run these commands:**
```bash
cd ~/RDWC-v4

# 1. Check what branch/commit we're on
git status
git log --oneline -3

# 2. Check if service is running
sudo systemctl status rdwc

# 3. Check recent errors
sudo journalctl -u rdwc -n 100 --no-pager | grep -i error

# 4. Test API directly
curl http://localhost:8080/health
curl http://localhost:8080/api/relays/status
curl http://localhost:8080/api/estop

# 5. Check E-stop state
curl -X POST http://localhost:8080/api/estop -H "Content-Type: application/json" -d '{"active":false}'

# 6. Try to toggle a relay directly
curl -X POST http://localhost:8080/api/relay/lights/toggle
```

### Step 2: Check Browser Console on HMI

**On HMI laptop (192.168.88.33):**
1. Open browser to `http://192.168.88.49:8080`
2. Press F12 to open developer tools
3. Go to Console tab
4. Look for errors (red text)
5. Take screenshot or note what errors appear

**Common issues to look for:**
- 404 errors (files not found)
- 500 errors (backend crashes)
- CORS errors (cross-origin issues)
- WebSocket errors
- "Failed to fetch" errors

### Step 3: Check Network Tab

**In browser F12 → Network tab:**
1. Click Manual button
2. Watch for request to `/api/system_mode`
3. Check if it's:
   - ❌ Red (failed)
   - ⚠️ Yellow (pending forever)
   - ✅ Green (succeeded but no effect)

### Step 4: Check What's Actually Deployed

**On Pi:**
```bash
cd ~/RDWC-v4
git diff --stat HEAD origin/restore-main-files
# If this shows differences, the fixes aren't deployed yet

# Check if changes are actually in files
grep -n "Poll hold state every 5s" app/static/js/circulation.js
grep -n "self-poll" app/static/js/relays_v2.js
```

## Possible Root Causes

### 1. Changes Not Deployed
**Symptom:** Git shows we're not on restore-main-files branch
**Fix:** 
```bash
cd ~/RDWC-v4
git fetch origin
git checkout restore-main-files
git pull origin restore-main-files
sudo systemctl restart rdwc
```

### 2. Service Not Running
**Symptom:** `systemctl status rdwc` shows inactive/failed
**Fix:**
```bash
sudo systemctl start rdwc
sudo systemctl status rdwc
sudo journalctl -u rdwc -f  # Watch logs
```

### 3. E-Stop Engaged
**Symptom:** `/api/estop` shows `"active": true`
**Fix:**
```bash
curl -X POST http://192.168.88.49:8080/api/relays/estop/toggle
# Or click E-STOP button in UI (if it responds)
```

### 4. Database Locked
**Symptom:** Logs show "database is locked" errors
**Fix:**
```bash
cd ~/RDWC-v4
sudo systemctl stop rdwc
sudo systemctl stop rdwc-sensors
sleep 2
sudo rm -f data/rdwc.db-wal data/rdwc.db-shm  # Clear WAL files
sudo systemctl start rdwc
sudo systemctl start rdwc-sensors
```

### 5. Permission Issues
**Symptom:** Logs show "Permission denied" for GPIO or files
**Fix:**
```bash
sudo usermod -a -G gpio pi
sudo chown -R pi:pi ~/RDWC-v4/data
sudo chmod 664 ~/RDWC-v4/data/rdwc.db
```

### 6. Port Conflict
**Symptom:** Service fails to start, port already in use
**Fix:**
```bash
# Find what's using port 8080
sudo lsof -i :8080
# Kill it if it's a zombie process
sudo kill -9 <PID>
sudo systemctl start rdwc
```

### 7. Python Environment Issues
**Symptom:** Service starts but crashes immediately
**Fix:**
```bash
cd ~/RDWC-v4
source venv/bin/activate  # or wherever venv is
pip install -r requirements.txt
deactivate
sudo systemctl restart rdwc
```

## Critical Files to Check

**On Pi, verify these exist and have recent changes:**
```bash
cd ~/RDWC-v4
ls -lh app/static/js/relays_v2.js
ls -lh app/static/js/circulation.js
ls -lh app/static/js/ph.js
ls -lh app/static/js/ec.js

# Check if they have the new code
grep "Poll hold state every 5s" app/static/js/circulation.js
```

## Emergency Reset

**If nothing else works:**
```bash
cd ~/RDWC-v4
git fetch origin
git reset --hard origin/restore-main-files
sudo systemctl stop rdwc rdwc-sensors
sleep 2
sudo systemctl start rdwc rdwc-sensors
sudo systemctl status rdwc
```

## Report Back

Please provide:
1. Output of diagnostic script (or manual commands)
2. Screenshot of browser console errors
3. Result of `systemctl status rdwc`
4. Contents of E-stop status check
5. Current git branch/commit

This will tell me exactly what's wrong so I can fix it properly.
