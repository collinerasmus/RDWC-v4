# Deployment Troubleshooting Guide

**Issue:** Changes deployed to Pi but UI doesn't reflect them after hard refresh  
**Date:** 2025-11-19  
**Branch:** copilot/finish-task-session-63  
**Commit:** ba2d680

---

## Quick Diagnosis

### 1. Verify You're on the Correct Branch

```bash
cd /opt/rdwc  # or wherever your repo is
git branch
```

**Expected Output:**
```
* copilot/finish-task-session-63
  main
  other-branches...
```

If you see `* main` or another branch, you're not on the right branch!

**Fix:**
```bash
git fetch origin
git checkout copilot/finish-task-session-63
git pull origin copilot/finish-task-session-63
```

---

### 2. Verify Correct Commit

```bash
git log -1 --oneline
```

**Expected Output:**
```
ba2d680 Copy all changes from PR #63 (copilot/xenial-lizard): Complete UI consolidation...
```

If you see a different commit (like `dd1d5bc Initial plan`), you don't have the changes!

**Fix:**
```bash
git pull origin copilot/finish-task-session-63
```

---

### 3. Check Service is Running with New Code

```bash
sudo systemctl status rdwc.service --no-pager | head -20
```

**Look for:**
- `Active: active (running)` ✅
- Recent restart timestamp (should be after you pulled changes)

**If not running or old timestamp:**
```bash
sudo systemctl restart rdwc.service
sleep 5
sudo systemctl status rdwc.service --no-pager
```

---

### 4. Verify Asset Version

```bash
curl -s http://localhost:8080/api/version
```

**Expected Output:**
```json
{"version": "ba2d680"}  // or another recent git SHA
```

If this doesn't match your current commit, the service hasn't reloaded!

**Fix:**
```bash
sudo systemctl restart rdwc.service
sleep 5
curl -s http://localhost:8080/api/version
```

---

### 5. Check New Endpoints Exist

```bash
# Test consolidated controllers status (NEW in PR #63)
curl -s http://localhost:8080/api/controllers/status | jq '.'

# Test chiller events (NEW in PR #63)
curl -s http://localhost:8080/api/chiller/events?limit=5 | jq '.'
```

**Expected:**
- First command returns JSON with `.controllers` key containing `ph`, `ec`, `chiller`, `lights`, `circulation`
- Second command returns an array (may be empty if no chiller events yet)

**If 404 errors:**
- Service is running old code
- Force restart: `sudo systemctl stop rdwc.service && sleep 3 && sudo systemctl start rdwc.service`

---

### 6. Verify Static Files Updated

```bash
# Check new JavaScript file exists
ls -la /opt/rdwc/app/static/js/sensors_calib.js

# Check it's loaded in HTML
grep "sensors_calib.js" /opt/rdwc/app/static/index.html
```

**Expected:**
- File exists with size > 10KB
- HTML contains two lines referencing it (in script loader)

**If file missing:**
```bash
cd /opt/rdwc
git status
# If shows "nothing to commit", but file missing, try:
git reset --hard HEAD
```

---

### 7. Browser Cache Issues

Even after all above checks pass, browser may cache old assets.

**Solution 1: Hard Refresh (Most Effective)**
- Windows/Linux: `Ctrl + Shift + R`
- Mac: `Cmd + Shift + R`

**Solution 2: Clear Cache via DevTools**
1. Open DevTools (F12)
2. Right-click on refresh button
3. Select "Empty Cache and Hard Reload"

**Solution 3: Incognito/Private Window**
- Open new incognito window
- Navigate to `http://192.168.88.49:8080`
- Should show new UI immediately

**Solution 4: Manual Cache Clear**
- Browser Settings → Privacy → Clear Browsing Data
- Select "Cached images and files"
- Time range: "All time"
- Clear data

---

## Detailed Diagnostics

### Check Service Logs for Errors

```bash
# Recent logs
sudo journalctl -u rdwc.service -n 100 --no-pager

# Follow logs in real-time
sudo journalctl -u rdwc.service -f
```

**Look for:**
- ✅ "Application startup complete"
- ✅ "Uvicorn running on http://0.0.0.0:8080"
- ❌ Any Python exceptions or errors
- ❌ Import errors (ModuleNotFoundError)
- ❌ Permission errors (GPIO, I²C)

**Common Errors and Fixes:**

**Error: "ModuleNotFoundError: No module named 'app'"**
```bash
# Fix: Set PYTHONPATH in service file
sudo nano /etc/systemd/system/rdwc.service

# Add this line in [Service] section:
Environment="PYTHONPATH=/opt/rdwc:/opt/rdwc/app"

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart rdwc.service
```

**Error: "Permission denied: '/dev/i2c-1'"**
```bash
# Fix: Add user to i2c group
sudo usermod -a -G i2c $(whoami)
sudo reboot  # Required for group change to take effect
```

**Error: "Address already in use (port 8080)"**
```bash
# Fix: Kill old process
sudo lsof -ti:8080 | xargs sudo kill -9
sleep 2
sudo systemctl start rdwc.service
```

---

### Verify Database Accessible

```bash
# Check database file exists and is writable
ls -la /opt/rdwc/data/rdwc.db

# Expected: File owned by user running service, size > 50KB
```

**If database issues:**
```bash
# Check database integrity
sqlite3 /opt/rdwc/data/rdwc.db "PRAGMA integrity_check;"
# Should output: ok

# List tables
sqlite3 /opt/rdwc/data/rdwc.db ".tables"
# Should show: chiller_events, controller_modes, settings, etc.
```

---

### Network and Firewall

```bash
# Verify service listening on port 8080
sudo netstat -tulpn | grep 8080

# Expected output:
# tcp    0    0 0.0.0.0:8080    0.0.0.0:*    LISTEN    <PID>/python3
```

**If port not listening:**
```bash
# Check if service is actually running
ps aux | grep uvicorn

# If not running, check service status
sudo systemctl status rdwc.service
```

**If firewall blocking:**
```bash
# Allow port 8080 (if using ufw)
sudo ufw allow 8080/tcp
sudo ufw reload
```

---

## Step-by-Step Verification Checklist

Use this checklist to systematically verify deployment:

### Code Verification
- [ ] On correct branch: `copilot/finish-task-session-63`
- [ ] Correct commit: `ba2d680`
- [ ] `sensors_calib.js` file exists
- [ ] HTML references `sensors_calib.js`
- [ ] 27 files show as modified from main

### Service Verification
- [ ] `rdwc.service` is active and running
- [ ] `rdwc-sensors.service` is active and running
- [ ] Recent restart timestamp (after pulling changes)
- [ ] No errors in journalctl logs
- [ ] Process listening on port 8080

### API Verification
- [ ] `/health` returns 200 OK
- [ ] `/api/version` shows correct git SHA
- [ ] `/api/controllers/status` returns 200 with controllers object
- [ ] `/api/chiller/events` returns 200 with array
- [ ] `/api/sensors` returns recent reading

### Browser Verification
- [ ] Hard refresh performed (Ctrl+Shift+R)
- [ ] DevTools console shows no 404 errors
- [ ] DevTools Network tab shows sensors_calib.js loaded
- [ ] Asset version in HTML source matches git SHA

### UI Verification
- [ ] Sensors Settings shows 3 accordions (not 5)
- [ ] pH Settings has "Pump Calibration" section
- [ ] EC Settings has "EC Pumps Calibration" section
- [ ] No redundant automation buttons visible
- [ ] Mode chips present in all tab headers
- [ ] Learned value KPIs visible in pH/EC readings

---

## Expected UI Changes (Visual Guide)

### Sensors Tab - Settings Section

**OLD (Before PR #63):**
```
Settings (5 sections):
1. Sensor Reading
2. pH Probe Calibration
3. EC Probe Calibration
4. pH Pump Calibration  ← Should NOT be here
5. EC Pumps Calibration ← Should NOT be here
```

**NEW (After PR #63):**
```
Settings (3 sections):
1. Sensor Reading
2. pH Probe Calibration
3. EC Probe Calibration
```

### pH Tab - Settings Section

**NEW (After PR #63):**
```
Settings:
- Parameters (blue-tinted)
- Manual Dosing
- 💧 Pump Calibration  ← MOVED HERE from Sensors
- Automation (with Clear Learned Value button)
```

### EC Tab - Settings Section

**NEW (After PR #63):**
```
Settings:
- Parameters (blue-tinted)
- 💧 EC Pumps Calibration  ← MOVED HERE from Sensors
  - Grow Pump
  - Micro Pump
  - Bloom Pump
- Automation (with Clear Learned Value button)
```

### All Tabs - Header

**NEW (After PR #63):**
```
Tab Header:
- Title
- Mode Chips: [Auto] [Manual] [Maintenance]  ← ONLY mode control
- Status indicators

NO redundant automation toggle buttons!
```

---

## Common Scenarios and Solutions

### Scenario 1: "I see old UI even after hard refresh"

**Root Cause:** Service worker or aggressive browser caching

**Solution:**
```bash
# 1. Clear browser completely
# In browser: Settings → Privacy → Clear all data

# 2. Restart browser completely (close all windows)

# 3. Try incognito window first
# If incognito shows new UI but normal doesn't, it's cache

# 4. Disable service workers (if present)
# DevTools → Application → Service Workers → Unregister
```

### Scenario 2: "New endpoints return 404"

**Root Cause:** Service running old code

**Solution:**
```bash
# 1. Verify commit
cd /opt/rdwc
git log -1 --oneline
# Must show: ba2d680

# 2. Force service restart
sudo systemctl stop rdwc.service
sleep 5  # Wait for process to fully terminate
sudo systemctl start rdwc.service

# 3. Verify new version
curl -s http://localhost:8080/api/version
# Should show git SHA matching current commit

# 4. Test new endpoint
curl -s http://localhost:8080/api/controllers/status | jq '.controllers | keys'
# Should return: ["chiller", "circulation", "ec", "lights", "ph"]
```

### Scenario 3: "Git says 'Already up to date' but I don't have changes"

**Root Cause:** On wrong branch or local branch not tracking remote

**Solution:**
```bash
# 1. Check current branch
git branch
# If not on copilot/finish-task-session-63:

# 2. Switch to correct branch
git fetch origin
git checkout copilot/finish-task-session-63

# 3. Force pull
git reset --hard origin/copilot/finish-task-session-63

# 4. Verify commit
git log -1 --oneline
# Must show: ba2d680
```

### Scenario 4: "Service won't start after pulling changes"

**Root Cause:** Missing dependencies or Python errors

**Solution:**
```bash
# 1. Check service logs for specific error
sudo journalctl -u rdwc.service -n 50 --no-pager

# 2. If ModuleNotFoundError, install dependencies
cd /opt/rdwc
pip3 install -r requirements.txt

# 3. If still fails, try manual start for better error messages
cd /opt/rdwc
PYTHONPATH=/opt/rdwc:$PYTHONPATH uvicorn app.main:app --host 0.0.0.0 --port 8080
# Watch for any Python exceptions

# 4. Fix errors, then start service normally
sudo systemctl start rdwc.service
```

### Scenario 5: "Only some tabs show changes"

**Root Cause:** Partial browser cache clear

**Solution:**
```bash
# This is definitely browser cache

# 1. Clear browser cache COMPLETELY
# Not just "last hour" - select "All time"

# 2. Close ALL browser windows

# 3. Verify with curl that server has all changes
curl -s http://localhost:8080/api/controllers/status | jq '.'
curl -s http://localhost:8080/api/chiller/events | jq '.'

# If curl shows correct data but browser doesn't:
# 4. Try different browser
# 5. Try incognito mode
# 6. Check browser extensions (some cache aggressively)
```

---

## Diagnostic Script

Save this as `diagnose.sh` and run it:

```bash
#!/bin/bash
echo "=== RDWC Deployment Diagnostics ==="
echo ""

echo "1. Git Branch:"
cd /opt/rdwc && git branch | grep '*'
echo ""

echo "2. Git Commit:"
cd /opt/rdwc && git log -1 --oneline
echo ""

echo "3. Service Status:"
sudo systemctl is-active rdwc.service
echo ""

echo "4. Asset Version:"
curl -s http://localhost:8080/api/version 2>/dev/null || echo "Service not responding"
echo ""

echo "5. New File Exists:"
ls -la /opt/rdwc/app/static/js/sensors_calib.js 2>/dev/null && echo "✅ File exists" || echo "❌ File missing"
echo ""

echo "6. Controllers Status Endpoint:"
curl -s http://localhost:8080/api/controllers/status 2>/dev/null | jq '.controllers | keys' || echo "Endpoint not available"
echo ""

echo "7. Chiller Events Endpoint:"
curl -s http://localhost:8080/api/chiller/events?limit=1 2>/dev/null | jq 'length' || echo "Endpoint not available"
echo ""

echo "=== Diagnosis Complete ==="
```

**Run it:**
```bash
chmod +x diagnose.sh
./diagnose.sh
```

---

## When to Contact Support

If after following all steps above:

1. ✅ Git shows correct commit (ba2d680)
2. ✅ Service is running without errors
3. ✅ New endpoints return 200 OK
4. ✅ Browser cache completely cleared
5. ✅ Incognito mode also shows old UI

**Then there may be a deeper issue.** Provide:

1. Output of `diagnose.sh` (above)
2. Last 100 lines of service logs: `sudo journalctl -u rdwc.service -n 100 --no-pager`
3. Screenshot of browser DevTools → Network tab showing loaded assets
4. Output of: `curl -s http://localhost:8080/api/version`

---

## Success Indicators

You'll know deployment succeeded when:

### API Level
✅ `/api/version` shows recent git SHA  
✅ `/api/controllers/status` returns all 5 controllers  
✅ `/api/chiller/events` returns 200 (array, may be empty)  
✅ All API requests return within 100ms  

### UI Level
✅ Hard refresh loads new assets (check DevTools Network tab)  
✅ Sensors Settings shows only 3 sections  
✅ pH Settings has Pump Calibration section  
✅ EC Settings has EC Pumps section  
✅ No redundant automation buttons anywhere  
✅ Mode chips work on all tabs  
✅ Learned values show in pH/EC if available  

### Functional Level
✅ Mode changes propagate to all tabs within 5 seconds  
✅ Pump calibration workflow works (Prime/Run/Commit)  
✅ Clear Learned Value buttons work with confirmation  
✅ Chiller responds to temperature (if in auto mode)  
✅ All existing features still work  

---

## Quick Reference Commands

```bash
# Check branch
cd /opt/rdwc && git branch

# Check commit
git log -1 --oneline

# Update code
git pull origin copilot/finish-task-session-63

# Restart service
sudo systemctl restart rdwc.service

# Check logs
sudo journalctl -u rdwc.service -n 50 --no-pager

# Test API
curl -s http://localhost:8080/health
curl -s http://localhost:8080/api/version
curl -s http://localhost:8080/api/controllers/status | jq '.'

# Verify files
ls -la /opt/rdwc/app/static/js/sensors_calib.js
grep "sensors_calib.js" /opt/rdwc/app/static/index.html
```

---

## Document Info

**Version:** 1.0  
**Date:** 2025-11-19  
**Purpose:** Troubleshoot deployment issues  
**Related:** SYSTEM_VALIDATION_CHECKPOINT.md, SYSTEM_ARCHITECTURE.md

**Most Common Issue:** Browser cache - always try hard refresh first!

---

*End of Deployment Troubleshooting Guide*
