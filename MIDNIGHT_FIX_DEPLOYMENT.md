# Lights Schedule Midnight Fix - Deployment Guide

## Version
**v4.3.0** - Lights Schedule Midnight Boundary Fix

## What Changed
Fixed critical bug where lights incorrectly turned OFF at 23:59 when the schedule spanned midnight (e.g., ON at 22:00, OFF at 10:00 next day). Lights now correctly stay ON through midnight and turn OFF at the scheduled time.

## Impact
- **HIGH PRIORITY** for users with lights schedules that cross midnight
- **LOW IMPACT** for users with same-day schedules (e.g., 06:00-22:00)
- **ZERO DOWNTIME** deployment - drop-in replacement
- **NO DATABASE CHANGES** required
- **NO CONFIGURATION CHANGES** required

## Pre-Deployment Checklist
- [ ] Verify current lights schedule settings (check `/settings` endpoint)
- [ ] Note current lights state (ON/OFF) before deployment
- [ ] Verify scheduler is enabled (`schedule.json` has `"enabled": true`)
- [ ] Backup current schedule configuration: `cp ~/.rdwc/schedule.json ~/.rdwc/schedule.json.backup`

## Deployment Steps

### Option 1: Standard Pi Deployment (Recommended)
```bash
# 1. SSH to your Pi
ssh pi@<your-pi-ip>

# 2. Navigate to RDWC directory
cd ~/RDWC-v4

# 3. Pull latest changes
git fetch origin
git checkout copilot/fix-midnight-schedule-logic
git pull

# 4. Restart services (pick one)
# Option A: If using systemd services
sudo systemctl restart rdwc.service
sudo systemctl restart rdwc-sensors.service  # if separate

# Option B: If running manually
pkill -f "uvicorn app.main:app"
pkill -f "python.*sensor_poller"
# Then restart your services as normal

# 5. Verify scheduler is running
curl http://localhost:8080/api/relays/status | jq .mode

# 6. Monitor schedule logs
tail -f ~/.rdwc/schedule_log.jsonl
```

### Option 2: Docker Deployment
```bash
# 1. Pull latest code
git checkout copilot/fix-midnight-schedule-logic
git pull

# 2. Rebuild and restart
docker-compose down
docker-compose up -d --build

# 3. Verify
docker-compose logs -f rdwc
```

## Post-Deployment Verification

### Immediate Checks (0-5 minutes)
1. **API Health**: `curl http://localhost:8080/api/relays/status`
   - Should return 200 OK with relay states
   - `mode` should show current mode (auto/manual)

2. **Scheduler Running**: Check logs for startup
   ```bash
   tail -n 50 ~/.rdwc/schedule_log.jsonl | grep -E "lights_schedule_updated|midnight_continuation"
   ```

3. **Lights State**: Verify lights are in expected state for current time
   ```bash
   curl http://localhost:8080/api/relays/status | jq '.relays.lights'
   ```

### 24-Hour Monitoring
Monitor the following events in `~/.rdwc/schedule_log.jsonl`:

1. **Schedule Updates** (at midnight):
   ```json
   {"ts": <timestamp>, "kind": "lights_schedule_updated", "on_time": "22:00", "off_time": "10:00", ...}
   ```
   OR
   ```json
   {"ts": <timestamp>, "kind": "lights_schedule_midnight_continuation", "on_time_yesterday": "22:00", "off_time_today": "10:00", ...}
   ```

2. **Edge Events** (at scheduled times):
   ```json
   {"ts": <timestamp>, "kind": "lights_schedule_on", "time": "22:00", "changed": true}
   {"ts": <timestamp>, "kind": "lights_schedule_off", "time": "10:00", "changed": true}
   ```

### Expected Behavior Examples

#### Scenario 1: Midnight-Spanning Schedule (22:00-10:00)
**Before Fix (BROKEN):**
- 22:00: Lights turn ON ✅
- 23:59: Lights turn OFF ❌ (BUG!)
- 00:00: Lights stay OFF ❌
- 10:00: Lights stay OFF ❌

**After Fix (CORRECT):**
- 22:00: Lights turn ON ✅
- 23:59: Lights stay ON ✅ (no edge)
- 00:00: Lights stay ON ✅ (midnight continuation detected)
- 10:00: Lights turn OFF ✅

#### Scenario 2: Same-Day Schedule (06:00-22:00)
**Both Before and After Fix (CORRECT):**
- 06:00: Lights turn ON ✅
- 22:00: Lights turn OFF ✅
- No midnight issues (schedule doesn't span midnight)

## Troubleshooting

### Issue: Lights didn't turn ON/OFF at scheduled time
**Check:**
1. Controller mode: `curl http://localhost:8080/api/controller/lights/mode`
   - Must be `"auto"` for scheduler to control lights
   - If `"manual"` or `"hold"`, scheduler is disabled

2. Schedule enabled: `cat ~/.rdwc/schedule.json | jq .enabled`
   - Must be `true`

3. Recent errors: `tail -n 100 ~/.rdwc/schedule_log.jsonl | grep error`

### Issue: Lights turned OFF at wrong time
**Check:**
1. Current schedule: `curl http://localhost:8080/settings | jq '.lights_on_time, .lights_duration_hours'`
2. Verify timezone: `date` on Pi should match Africa/Johannesburg (SA timezone)
3. Check schedule log for edge events around the time it turned OFF

### Issue: Scheduler not running
**Check:**
1. Service status: `sudo systemctl status rdwc.service`
2. Process running: `ps aux | grep scheduler`
3. Recent logs: `tail -n 50 ~/.rdwc/schedule_log.jsonl`

## Rollback Procedure (If Needed)
```bash
# 1. Stop services
sudo systemctl stop rdwc.service rdwc-sensors.service

# 2. Restore previous version
git checkout <previous-commit-hash>  # e.g., 492d212

# 3. Restart services
sudo systemctl start rdwc.service rdwc-sensors.service

# 4. Verify
curl http://localhost:8080/api/relays/status
```

## Technical Notes for Developers

### Code Changes
- **File**: `app/scheduler.py`
- **Method**: `_update_lights_schedule()`
- **Lines**: ~93-165

### Key Logic
1. Detect midnight-spanning windows: `off_dt.date() > on_dt.date()`
2. Check if current time is in yesterday's continuation: `now.date() > on_dt.date() and now < off_dt`
3. Set on_time to yesterday's time (already passed), off_time to today's time (will trigger at correct time)
4. Edge detection still fires only at exact HH:MM:00 times (s == 0)

### Test Coverage
- **File**: `tests/test_scheduler_midnight.py`
- **Tests**: 7 comprehensive tests covering all midnight scenarios
- **Run**: `pytest tests/test_scheduler_midnight.py -v`

## Support
If you encounter issues:
1. Check logs: `~/.rdwc/schedule_log.jsonl`
2. Verify settings: `curl http://localhost:8080/settings`
3. Check controller mode: `curl http://localhost:8080/api/controller/lights/mode`
4. Open issue on GitHub with logs and configuration

## References
- CHANGELOG.md - v4.3.0 release notes
- tests/test_scheduler_midnight.py - Test scenarios
- app/scheduler.py - Implementation details
