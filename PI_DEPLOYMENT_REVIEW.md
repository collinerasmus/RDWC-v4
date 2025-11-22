# Pi Deployment & UI Review Guide - Midnight Fix

## Quick Overview
This fix addresses a backend scheduler bug with **NO UI changes**. All UI should work exactly as before. This guide helps you:
1. Deploy the fix to your Pi
2. Review the UI to ensure everything still works
3. Verify the midnight fix is active

---

## Part 1: Deploy to Pi (VS Code Remote SSH)

### Step 1: Connect to Pi via VS Code
1. Open VS Code
2. Press `F1` or `Ctrl+Shift+P`
3. Type "Remote-SSH: Connect to Host"
4. Select your Pi (or enter: `pi@<your-pi-ip>`)
5. Enter password when prompted

### Step 2: Navigate to RDWC Directory
```bash
# In VS Code terminal (Ctrl+`)
cd ~/RDWC-v4
```

### Step 3: Pull Latest Changes
```bash
# Fetch the fix branch
git fetch origin

# Switch to fix branch
git checkout copilot/fix-midnight-schedule-logic

# Pull latest (should be up to date)
git pull

# Verify you're on the right commit
git log --oneline -5
# Should show: 41cfea6 Add technical summary document for midnight fix
```

### Step 4: Restart Services
```bash
# Option A: If using systemd services
sudo systemctl restart rdwc.service
sudo systemctl restart rdwc-sensors.service

# Option B: If running manually, kill and restart
pkill -f "uvicorn app.main:app"
pkill -f "python.*sensor_poller"
# Then start your services as normal

# Verify services are running
sudo systemctl status rdwc.service
# Or check process
ps aux | grep uvicorn
```

### Step 5: Verify API is Running
```bash
# Quick health check
curl http://localhost:8080/api/relays/status

# Should return JSON with relay states
```

---

## Part 2: UI Review Checklist

### Access the UI
Open browser and navigate to: `http://<your-pi-ip>:8080`
(e.g., `http://192.168.88.49:8080`)

### 🔍 Overview Tab
- [ ] **System Status**: All dots should show status (green/yellow/red)
- [ ] **pH/EC Status**: Values displaying correctly
- [ ] **Temperature**: Current reading shown
- [ ] **Controller Mode Chips**: Should show "auto", "manual", or "hold"
- [ ] **Guard Status**: Should show active guards if any

**What to Check:**
- No console errors (F12 → Console tab)
- Status updates every ~6 seconds
- Dots change color based on actual state

### 🌡️ Sensors Tab
- [ ] **Current Readings**: Temperature, pH, EC displaying
- [ ] **Timestamp**: Should be recent (< 60 seconds old)
- [ ] **Chart**: Historical data showing (if exists)
- [ ] **Refresh Button**: Manual refresh works

**What to Check:**
- Sensor freshness indicator (green = fresh, red = stale)
- Values match expected ranges
- No "offline" errors unless sensors actually disconnected

### 💡 Lights Tab (MOST RELEVANT FOR THIS FIX)
- [ ] **Current State**: Shows ON/OFF correctly
- [ ] **Schedule Window**: Shows "Window: HH:MM → HH:MM"
- [ ] **Toggle Button**: Works in manual mode (disabled in auto mode)
- [ ] **Controller Mode**: Shows current mode (auto/manual/hold)

**What to Check:**
- Current lights state matches physical reality
- Schedule window displays correctly
- If schedule spans midnight (e.g., "22:00 → 10:00"), verify it shows correctly
- Mode indicator accurate

### 🧪 pH Tab
- [ ] **Current pH**: Displaying correct value
- [ ] **Target Range**: Shows high/low targets
- [ ] **Auto/Manual Mode**: Toggle works
- [ ] **Dose Buttons**: Respond when clicked (if in manual mode)
- [ ] **Dose History**: Shows recent events (if any)

**What to Check:**
- pH auto controller respects mode setting
- Guards displayed if blocking dosing
- Dose history table loads

### ⚡ EC Tab
- [ ] **Current EC**: Displaying correct value (mS/cm)
- [ ] **Target**: Shows target EC
- [ ] **Pump Selector**: Can select micro/grow/bloom
- [ ] **Dose Buttons**: Work in manual mode
- [ ] **EC History**: Shows recent events

**What to Check:**
- EC values in expected range
- Pump selection persists
- Guards prevent dosing when appropriate

### ❄️ Chiller Tab
- [ ] **Current Temp**: Matches sensor reading
- [ ] **Target Temp**: Shows setpoint
- [ ] **Chiller State**: Shows ON/OFF/AUTO
- [ ] **Min On/Off Times**: Display correctly
- [ ] **Temperature Alerts**: Show if temp out of range

**What to Check:**
- Chiller respects min on/off times
- Auto mode works if enabled
- Manual override possible

### 🔄 Circulation Tab
- [ ] **Main Pump**: Shows status
- [ ] **Sensor Power**: Shows status (if configured)
- [ ] **Toggle Buttons**: Work in manual mode
- [ ] **Cooldown Timers**: Display if active

**What to Check:**
- Pumps respond to commands
- E-STOP respected if active
- Cooldowns enforce safety delays

### 📅 Schedule Tab (RELEVANT FOR THIS FIX)
- [ ] **Schedule Enabled**: Toggle shows current state
- [ ] **Lights Schedule**: Shows ON time and duration
- [ ] **Dosing Schedule**: Shows micro/grow/bloom times
- [ ] **Daily Caps**: Display correctly
- [ ] **Today's Events**: Shows upcoming/past events

**What to Check:**
- Schedule matches settings
- Enable/disable toggle works
- Events log shows lights ON/OFF at correct times
- NO premature OFF at 23:59 for midnight-spanning schedules

### ⚙️ Settings Tab
- [ ] **Targets**: pH high/low, EC target editable
- [ ] **Lights Settings**: ON time and duration editable
- [ ] **Reservoir Volume**: Shows correct value
- [ ] **Timezone**: Africa/Johannesburg displayed
- [ ] **Save Button**: Works and shows confirmation

**What to Check:**
- Values load from database
- Changes persist after save
- Validation prevents invalid values

### 🔧 System Tab
- [ ] **E-STOP Status**: Shows current state
- [ ] **Controller Modes**: All controllers listed with modes
- [ ] **System Info**: Version, uptime, etc.
- [ ] **Logs**: Recent events displaying

**What to Check:**
- E-STOP toggle works
- Mode changes apply correctly
- Version shows current commit or release

---

## Part 3: Midnight Fix Verification

### Check Schedule Configuration
```bash
# View current schedule settings
curl http://localhost:8080/settings | jq '.lights_on_time, .lights_duration_hours'

# Example output:
# "22:00"
# 12
# (This means lights ON at 22:00, OFF at 10:00 next day - SPANS MIDNIGHT)
```

### Monitor Schedule Logs
```bash
# Watch schedule events in real-time
tail -f ~/.rdwc/schedule_log.jsonl

# Look for these event types:
# - "lights_schedule_updated" (at startup/midnight)
# - "lights_schedule_midnight_continuation" (after midnight, in active window)
# - "lights_schedule_on" (at ON time)
# - "lights_schedule_off" (at OFF time)
```

### Expected Behavior for Midnight-Spanning Schedule

**Example Schedule: ON at 22:00, Duration 12h (OFF at 10:00 next day)**

**Day 1 Timeline:**
- `21:00` - Before ON time, schedule shows: ON=22:00, OFF=10:00
- `22:00` - Lights turn ON (edge event logged)
- `23:00` - Lights stay ON (no event)
- `23:59` - **Lights stay ON** ✅ (FIX: previously turned OFF here)

**Day 2 Timeline:**
- `00:00` - Midnight reset, schedule detects continuation
  - Log shows: `"kind": "lights_schedule_midnight_continuation"`
  - Lights stay ON ✅
- `09:00` - Lights still ON (no event)
- `10:00` - **Lights turn OFF** ✅ (edge event logged at correct time)

### Verification Commands

```bash
# 1. Check current lights state
curl http://localhost:8080/api/relays/status | jq '.relays.lights'

# 2. Check controller mode (must be "auto" for scheduler to control)
curl http://localhost:8080/api/controller/lights/mode | jq .

# 3. Check schedule is enabled
cat ~/.rdwc/schedule.json | jq .enabled

# 4. View recent schedule events
tail -n 50 ~/.rdwc/schedule_log.jsonl | grep lights | jq .
```

### If Lights Schedule Doesn't Span Midnight
If your schedule is same-day (e.g., ON at 06:00, OFF at 22:00), you won't see the midnight continuation behavior. This is normal and the fix has **zero impact** on same-day schedules.

---

## Part 4: Troubleshooting

### Issue: Can't Access UI
**Check:**
```bash
# Is service running?
sudo systemctl status rdwc.service

# Is port 8080 open?
curl http://localhost:8080/status

# Check for errors
sudo journalctl -u rdwc.service -n 50
```

### Issue: UI Shows Stale Data
**Fix:**
```bash
# Clear browser cache (Ctrl+F5)
# Or hard refresh in browser

# Check if sensor poller is running
ps aux | grep sensor_poller
sudo systemctl status rdwc-sensors.service
```

### Issue: Schedule Not Running
**Check:**
```bash
# 1. Controller mode
curl http://localhost:8080/api/controller/lights/mode
# Must be "auto" (not "manual" or "hold")

# 2. Schedule enabled
cat ~/.rdwc/schedule.json | jq .enabled
# Must be true

# 3. Recent errors
tail -n 100 ~/.rdwc/schedule_log.jsonl | grep error | jq .
```

### Issue: Lights Turned OFF at Wrong Time
**Investigate:**
```bash
# Check actual schedule times
curl http://localhost:8080/settings | jq '
  {
    on_time: .lights_on_time,
    duration: .lights_duration_hours,
    timezone: .general_timezone
  }
'

# Check edge events around that time
grep -A 2 -B 2 "23:59\|00:00\|10:00" ~/.rdwc/schedule_log.jsonl | jq .
```

---

## Part 5: Rollback (If Needed)

If you encounter issues and need to revert:

```bash
# 1. Stop services
sudo systemctl stop rdwc.service rdwc-sensors.service

# 2. Switch back to main branch
git checkout main
git pull

# 3. Restart services
sudo systemctl start rdwc.service rdwc-sensors.service

# 4. Verify
curl http://localhost:8080/api/relays/status
```

---

## Summary of Changes (What Got Fixed)

### What Changed (Backend Only)
- ✅ `app/scheduler.py` - Fixed midnight boundary logic
- ✅ `tests/test_scheduler_midnight.py` - Added 7 comprehensive tests
- ✅ Documentation - CHANGELOG, deployment guide, technical summary

### What Didn't Change (UI Unchanged)
- ⚪ No changes to any HTML files
- ⚪ No changes to any JavaScript files
- ⚪ No changes to any CSS files
- ⚪ No changes to API endpoints (same routes, same responses)
- ⚪ No changes to database schema

### Expected Outcome
- **Same-day schedules**: Zero impact, works exactly as before
- **Midnight-spanning schedules**: Lights now stay ON correctly through midnight
- **UI**: Looks and behaves identically (no visual changes)
- **Performance**: No measurable difference (one additional check at midnight)

---

## Quick Test Scenario

### Test 1: UI Still Works
1. Open UI in browser
2. Navigate through all tabs (Overview, Sensors, pH, EC, Chiller, etc.)
3. Check for JavaScript errors in console (F12)
4. Verify status updates every few seconds
5. Test manual control toggle (lights, pumps) in manual mode

**Expected**: Everything works as before, no errors

### Test 2: Schedule Configuration
1. Go to Settings tab
2. Note current lights schedule (ON time and duration)
3. Calculate: Does it span midnight?
   - Example: ON=22:00, Duration=12h → OFF=10:00 (SPANS)
   - Example: ON=06:00, Duration=16h → OFF=22:00 (SAME DAY)
4. Go to Schedule tab
5. Verify schedule shows correctly

**Expected**: Schedule displays accurate times

### Test 3: Wait for Edge Event (Optional)
If you can wait until a scheduled event:
1. Note next edge time (ON or OFF)
2. Watch schedule logs: `tail -f ~/.rdwc/schedule_log.jsonl`
3. Observe lights state change at exact scheduled time
4. For midnight-spanning schedules, verify lights stay ON after 23:59

**Expected**: Lights change state at exact scheduled times only

---

## Support

If you find issues:
1. Check logs: `~/.rdwc/schedule_log.jsonl`
2. Verify config: `curl http://localhost:8080/settings`
3. Check controller mode: `curl http://localhost:8080/api/controller/lights/mode`
4. Review this guide's troubleshooting section
5. Check GitHub issue comments for updates

---

## Files to Review in VS Code (Optional)

If you want to see what changed:

```bash
# View the scheduler fix
code ~/RDWC-v4/app/scheduler.py

# View the new tests
code ~/RDWC-v4/tests/test_scheduler_midnight.py

# View deployment guide
code ~/RDWC-v4/MIDNIGHT_FIX_DEPLOYMENT.md

# View technical summary
code ~/RDWC-v4/MIDNIGHT_FIX_SUMMARY.md

# Compare changes
git diff 492d212..HEAD app/scheduler.py
```

---

## Next Steps After Review

1. ✅ Deploy fix to Pi (done above)
2. ✅ Review UI (done above)
3. ✅ Verify fix is active (check logs)
4. ⏳ Monitor for 24 hours (especially around midnight if schedule spans)
5. ✅ Merge PR if satisfied (GitHub web interface)

---

**Note**: This is a backend-only fix. If the UI looks/works exactly as before, that's correct! The fix prevents lights from turning OFF at 23:59 for midnight-spanning schedules - a backend scheduler bug with no UI component.
