# GA Merge Instructions - Session #72

**Version:** v4.3.0  
**Date:** 2025-11-22  
**Status:** APPROVED FOR MERGE

---

## Quick Start

### Option 1: GitHub Web Interface (Recommended)

1. Navigate to the pull request for branch `copilot/remove-duplicate-pump-calibrations-again`
2. Review the changes and Session #72 handoff document
3. Click **"Merge pull request"**
4. Select **"Create a merge commit"** (recommended)
5. Confirm the merge
6. Delete the feature branch when prompted

### Option 2: Command Line

```bash
# Switch to main branch
git checkout main

# Pull latest changes
git pull origin main

# Merge the feature branch
git merge copilot/remove-duplicate-pump-calibrations-again

# Push to origin
git push origin main

# Delete the feature branch (optional)
git branch -d copilot/remove-duplicate-pump-calibrations-again
git push origin --delete copilot/remove-duplicate-pump-calibrations-again
```

---

## Pre-Merge Checklist

Before merging to main, verify:

- ✅ All Session #72 acceptance criteria met (see `SESSION_72_GA_HANDOFF.md`)
- ✅ Production validation complete (Pi @ 192.168.88.49:8080)
- ✅ Test coverage comprehensive (8 interlock tests)
- ✅ Documentation updated (CHANGELOG.md, SESSION_72_GA_HANDOFF.md)
- ✅ Version bumped to 4.3.0
- ✅ Known limitations documented (relay POST timeout, remediation latency)
- ✅ No blocking issues identified

---

## Post-Merge Deployment

### Deploy to Production Raspberry Pi

```bash
# SSH to the Pi
ssh pi@192.168.88.49

# Navigate to repository
cd /home/pi/RDWC-v4

# Checkout main branch
git checkout main

# Pull merged changes
git pull origin main

# Verify version
cat VERSION
# Should show: 4.3.0

# Restart sensor service first
sudo systemctl restart rdwc-sensors.service

# Wait for sensors to stabilize
sleep 5

# Restart main service
sudo systemctl restart rdwc.service

# Verify services are running
sudo systemctl status rdwc-sensors.service --no-pager
sudo systemctl status rdwc.service --no-pager
```

### Verify Deployment

```bash
# Check API version
curl -s http://localhost:8080/api/version
# Expected: version field matches commit SHA

# Check chiller interlock status
curl -s http://localhost:8080/api/chiller/status | jq '.interlock_ok, .interlock_details'
# Expected: interlock_ok: true, interlock_details with pump states

# Check controllers status
curl -s http://localhost:8080/api/controllers/status | jq '.system_mode, .estop'
# Expected: system_mode: "auto", estop: false

# Check relay status
curl -s http://localhost:8080/api/relays/status | jq '.relays | keys'
# Expected: Array of relay names including chiller, main_pump, chiller_pump
```

---

## UI Verification

After deployment, verify UI changes in web browser:

1. **Hard Refresh Required**
   - Windows/Linux: `Ctrl + Shift + R`
   - Mac: `Cmd + Shift + R`
   - Or use incognito/private window

2. **Overview Tab** - http://192.168.88.49:8080
   - ✅ Single E-STOP button in header (top-right, red)
   - ✅ No duplicate E-STOP buttons in navigation
   - ✅ Controller status cards visible
   - ✅ No mode buttons on this tab

3. **Sensors Tab** - http://192.168.88.49:8080/?tab=sensors
   - ✅ Clean header, no mode buttons
   - ✅ Sensor readings displaying (pH, EC, Temperature)
   - ✅ Charts functional

4. **Chiller Tab** - http://192.168.88.49:8080/?tab=chiller
   - ✅ **Interlock status banner visible** (green or red)
   - ✅ Green: "🟢 INTERLOCK ACTIVE: Chiller running with circulated pumps"
   - ✅ Red: "⚠️ INTERLOCK VIOLATION: [details]" (if pumps off)
   - ✅ Temperature and status displays
   - ✅ No mode buttons on this tab

5. **System Tab** - http://192.168.88.49:8080/?tab=system
   - ✅ **Mode buttons visible here only**: Auto / Manual / Maintenance / E-STOP
   - ✅ System status section
   - ✅ Settings tabs available

6. **All Other Tabs** (pH, EC, Circulation, Lights, Schedule)
   - ✅ Clean headers, no mode buttons
   - ✅ No duplicate E-STOP buttons
   - ✅ Functionality intact

---

## Rollback Plan

If issues are discovered after merge:

### Quick Rollback (Git Revert)

```bash
# Find the merge commit
git log --oneline -5

# Revert the merge commit (replace MERGE_SHA with actual SHA)
git revert -m 1 MERGE_SHA

# Push the revert
git push origin main

# Redeploy to Pi (use deployment commands above)
```

### Full Rollback (Reset)

```bash
# WARNING: Only use if git revert doesn't work
# This will lose any commits after the merge

# Find commit SHA before the merge
git log --oneline -10

# Reset to previous commit (replace PREVIOUS_SHA)
git reset --hard PREVIOUS_SHA

# Force push (requires force push permissions)
git push --force origin main

# Redeploy to Pi (use deployment commands above)
```

---

## Troubleshooting

### Issue: UI Not Showing Changes

**Symptoms:** 
- Old UI still visible after deployment
- Interlock banner not showing
- Duplicate buttons still present

**Solutions:**
1. Hard refresh browser (`Ctrl + Shift + R`)
2. Clear browser cache completely
3. Try incognito/private window
4. Try different browser
5. Verify service restart: `sudo systemctl status rdwc.service`
6. Check logs: `sudo journalctl -u rdwc.service -n 50`

### Issue: Interlock Banner Not Working

**Symptoms:**
- Banner not showing on Chiller tab
- API returns interlock_ok but no UI update

**Solutions:**
1. Check JavaScript console for errors (F12 → Console)
2. Verify `/api/chiller/status` endpoint: `curl http://localhost:8080/api/chiller/status`
3. Check `app/static/js/chiller.js` loaded correctly
4. Review nginx logs if using reverse proxy

### Issue: Services Not Starting

**Symptoms:**
- `systemctl status` shows failed state
- API not responding

**Solutions:**
1. Check service logs: `sudo journalctl -u rdwc.service -n 100`
2. Verify Python environment: `which python3`, `python3 --version`
3. Test manual start: `cd /home/pi/RDWC-v4 && python3 -m uvicorn app.main:app`
4. Check for port conflicts: `sudo lsof -i :8080`
5. Verify file permissions: `ls -la /home/pi/RDWC-v4/app/`

### Issue: Relay POST Timeout

**Symptoms:**
- `/relay/set` endpoint hangs
- Relay control from API doesn't work

**Status:** Known limitation (documented in SESSION_72_GA_HANDOFF.md)

**Workaround:**
- Use UI toggle buttons (functional)
- Monitor via GET endpoints only
- Deferred to Phase 8 (post-GA)

---

## Success Criteria

Deployment is successful when:

✅ Version shows 4.3.0  
✅ Services running (rdwc.service, rdwc-sensors.service)  
✅ API responds to all endpoints  
✅ UI shows single E-STOP in header  
✅ Mode buttons only on System tab  
✅ Chiller tab shows interlock banner  
✅ Interlock logic active (chiller blocked without pumps)  
✅ All 8 interlock tests pass: `pytest tests/test_chiller_interlock.py -v`  
✅ No new errors in service logs  

---

## Next Steps After GA Merge

### Phase 8: Post-GA Enhancements

1. **Fix Relay POST Timeout**
   - Create GitHub issue
   - Investigate `RequestAuditMiddleware` body consumption
   - Test async handler conversions
   - Target: <5s response time

2. **Optimize Remediation Latency**
   - Implement relay state change listener
   - Replace 30s poll with event-driven model
   - Target: <1s detection + remediation

3. **Enhanced Monitoring**
   - Add Grafana dashboard for interlock events
   - Configure alerts for prolonged violations
   - Implement historical trend analysis

### Phase 9: Future Enhancements

- Real-time relay listener (0s latency)
- Advanced interlock analytics
- Predictive maintenance alerts
- Mobile app integration

---

## References

- **Detailed Implementation**: `SESSION_72_GA_HANDOFF.md`
- **Changelog**: `CHANGELOG.md` (v4.3.0 section)
- **Test Coverage**: `tests/test_chiller_interlock.py`
- **Architecture**: `SYSTEM_ARCHITECTURE.md`
- **Deployment Troubleshooting**: `DEPLOYMENT_TROUBLESHOOTING.md`

---

## Support

If you encounter issues not covered in this document:

1. Check `DEPLOYMENT_TROUBLESHOOTING.md`
2. Review `SESSION_72_GA_HANDOFF.md` for technical details
3. Examine service logs: `sudo journalctl -u rdwc.service -n 100`
4. Review API responses: `curl -s http://localhost:8080/api/chiller/status | jq`
5. Check JavaScript console for UI errors (F12 → Console)

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-22  
**Status:** Final - Ready for GA Merge

---

*End of GA Merge Instructions*
