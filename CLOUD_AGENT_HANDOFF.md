# Cloud Agent Handoff: pH Chart Real-Time Update Issue

## SESSION CONTEXT (2025-11-29 19:58 UTC)
**Handoff from**: GitHub Copilot CLI Agent  
**Handoff to**: GitHub Cloud Agent  
**Reason**: User requested cloud agent takeover for pH chart troubleshooting

## CURRENT STATUS - PARTIALLY RESOLVED ⚠️

### PRIMARY ISSUE: pH Chart Not Showing Real-Time Updates ❌
**User Report**: "the ph graph is not giving the new reading as it comes"
**Status**: Chart may be rendering but NOT updating with fresh sensor readings
**Previous Work**: 
- Files deployed: `app/static/index.html` and `app/static/js/ph_chart.js`
- Service restarted: `rdwc.service` on Pi
- These changes did NOT fully resolve the issue

### What Was Deployed (Latest Session)
**Timestamp**: 2025-11-29 ~19:55 UTC
**Commands executed**:
```bash
scp app/static/index.html pi@192.168.88.49:~/RDWC-v4/app/static/
scp app/static/js/ph_chart.js pi@192.168.88.49:~/RDWC-v4/app/static/js/
ssh pi@192.168.88.49 "sudo systemctl restart rdwc.service"
```

**Files Transferred**: 
- `app/static/index.html` (Frontend HTML)
- `app/static/js/ph_chart.js` (Chart rendering logic)

**Result**: Files successfully deployed, service restarted, but pH chart still not showing real-time updates

## Current Deployment State
- **Branch**: copilot/sweet-cat
- **Latest Commit**: 972a0c7 (from PR #88 - Fix pH chart)
- **Pi IP**: 192.168.88.49:8080
- **Service**: rdwc.service (systemd, currently active)
- **API Health**: Endpoints responding normally

## CRITICAL INVESTIGATION REQUIRED

### Focus: Real-Time Chart Updates Not Working

The agent MUST investigate why pH chart doesn't show new sensor readings as they arrive:

1. **Polling Mechanism**:
   - Check if `fetchPhReadings()` is called on interval
   - Verify polling interval configuration (should be ~5-10 seconds)
   - Check if chart updates are triggered when new data arrives
   - Look for event listeners or setInterval() calls in ph_chart.js

2. **Data Freshness**:
   - Verify `/api/trends` returns latest sensor readings with recent timestamps
   - Check if sensor poller service is writing fresh data to database
   - Validate that API query time range includes current time (not just historical)
   - Check for timezone/UTC issues in time range calculations

3. **Chart.update() Calls**:
   - Verify Chart.js instance is updated after new data fetch
   - Check if chart.update() is called with proper parameters
   - Look for debouncing or throttling that may delay updates
   - Verify dataset.data array is modified before update() call

4. **Browser Console Errors**:
   - Check for JavaScript errors preventing chart refresh
   - Look for failed API calls or CORS issues
   - Verify network tab shows regular polling requests
   - Check for missing dependencies or null reference errors

5. **Caching Issues**:
   - Static files may be cached - user needs hard refresh (Ctrl+Shift+R)
   - Check for service worker or browser cache preventing updates
   - Verify deployed files on Pi match local changes

## Agent Task List (Priority Order)

### TASK 1: Fix Real-Time Chart Updates (CRITICAL) 🔴
**Issue**: Chart does not show new pH readings as they come in from sensors
**User Quote**: "the ph graph is not giving the new reading as it comes"

**Investigation Steps**:
1. Add console logging to track when fetchPhReadings() is called
2. Verify setInterval or polling loop exists and is active
3. Check `/api/trends` response contains data with recent timestamps
4. Verify chart.update() is called after each data fetch
5. Test with browser DevTools Network tab to see polling frequency
6. Check for errors preventing chart refresh cycle
7. Validate time range calculation includes "now" (not just past data)

**Likely Root Causes**:
- Polling interval not set up correctly
- Chart.update() not called after fetching new data
- Time range filter excludes current readings
- Browser cache serving stale JavaScript files
- Event loop blocked or throttled

### TASK 2: Browser Cache Resolution (HIGH) 🟡
**Issue**: User may be viewing cached version of ph_chart.js
**User Action Required**:
1. Hard refresh: `Ctrl+Shift+R` or `Cmd+Shift+R`
2. Clear browser cache for http://192.168.88.49:8080
3. Open DevTools (F12) → Network tab → Check "Disable cache" → Reload

**Agent Can Implement**:
Add cache-busting query parameters to script tags or implement versioning

### TASK 3: Verify Sensor Poller Health (MEDIUM) 🟡
**Issue**: If sensor poller stopped, no new data will be available
**Check**:
```bash
ssh pi@192.168.88.49 "systemctl status rdwc-sensors.service"
ssh pi@192.168.88.49 "tail -n 50 /var/log/rdwc/sensors.log"
curl "http://192.168.88.49:8080/api/sensors/status"
```

### TASK 4: Add Enhanced Logging (LOW) 🔵
**Purpose**: Help diagnose future issues
**Actions**:
- Add timestamps to all fetch operations
- Log data array lengths before/after updates
- Log chart.update() calls with success/failure
- Add visual indicator on UI when chart refreshes

## Code Context from Previous Work

### ph_chart.js - Key Functions
The chart rendering logic is in `app/static/js/ph_chart.js`:

**Critical Functions**:
- `fetchPhReadings()` - Fetches pH data from /api/trends
- `phBuildChart()` - Constructs Chart.js instance
- `phLoadRangeAndRender()` - Main orchestrator

**Known Enhancement Needed** (from previous session):
Enhanced logging for viewport/band filtering was added but real-time polling may be missing:

```javascript
// Need to verify this polling loop exists and works:
setInterval(async () => {
  await fetchPhReadings();
  if (phChart) {
    phChart.update(); // CRITICAL: Must be called to refresh display
  }
}, 10000); // Poll every 10 seconds
```

**If this interval doesn't exist, that's the root cause** - chart won't auto-refresh.

### index.html - Chart Container
Chart canvas location in `app/static/index.html`:
- pH Control tab contains chart canvas element
- Canvas ID: Check for `<canvas id="phChart">` or similar
- Verify canvas is not hidden by CSS or display:none

### API Endpoints
**Key endpoints** for chart data:
- `GET /api/trends?hours=1&ph=1` - Returns pH readings for time range
- `GET /api/sensors` - Current sensor snapshot (pH, temp, EC)
- `GET /api/ph/dose_log` - Pump activity for overlay bars

**Expected response structure** from /api/trends:
```json
{
  "ph": [
    {"ts": "2025-11-29T19:55:00Z", "value": 6.15},
    {"ts": "2025-11-29T19:56:00Z", "value": 6.18},
    ...
  ]
}
```

## Diagnostic Commands for Agent

### Verify Chart Data Availability
```bash
# Check if trends API returns pH data
curl -s "http://192.168.88.49:8080/api/trends?hours=1&ph=1" | python3 -m json.tool

# Check dose log for chart overlay
curl -s "http://192.168.88.49:8080/api/ph/dose_log?start=2025-11-29T00:00:00Z&end=2025-11-29T23:59:59Z&limit=100"
```

### Find Duplicate AUTO Code
```bash
# Search for all AUTO badge/indicator HTML
grep -n "AUTO" app/static/index.html | grep -i "badge\|pill\|indicator\|status"

# Search for pH auto status rendering in JS
grep -n "auto" app/static/js/ph.js | grep -i "badge\|indicator\|status"
```

### Locate Orphaned Parameters
```bash
# Find Max ml/hour and Max ml/day fields
grep -n "ml/hour\|ml/day" app/static/index.html
```

## Key Files to Investigate

### 1. app/static/js/ph_chart.js
**Purpose**: Renders pH chart with dose events overlay
**Current Issues**:
- Chart blank despite successful API calls
- Possible data pipeline break between API and Chart.js
- May need additional error handling and logging

**Critical Functions**:
- `fetchPhReadings()` - Gets pH data from /api/trends
- `phBuildChart()` - Constructs Chart.js instance
- `phLoadRangeAndRender()` - Main orchestrator

### 2. app/static/index.html
**Purpose**: Main UI template
**Current Issues**:
- Duplicate AUTO indicators (search for all "AUTO" badges)
- Orphaned parameters (Max ml/hour, Max ml/day)
- Possible duplicate status update code

**Critical Sections**:
- pH Control tab (around line 1000-2000)
- Parameters subtab
- Header status indicators

### 3. app/static/js/ph.js
**Purpose**: pH control logic and UI updates
**Current Issues**:
- May contain duplicate status rendering
- Check for multiple updateStatus() type functions

**Critical Functions**:
- Status update logic
- Auto mode toggle handlers
- Parameter field bindings

## Expected Deliverables

### 1. Working Real-Time pH Chart ✅
- **Acceptance**: Chart displays pH reading line with data points
- **Acceptance**: Chart auto-refreshes every 5-10 seconds with new data
- **Acceptance**: Latest sensor reading appears on chart within ~10 seconds
- **Acceptance**: Time axis shows "now" and scrolls forward automatically
- **Acceptance**: No manual page refresh required to see new readings
- **Acceptance**: Console logs show regular polling activity
- **Acceptance**: Dose events show as overlay (green triangles)
- **Acceptance**: Pump activity shows as vertical bars (if applicable)

### 2. Verified Data Pipeline ✅
- **Acceptance**: `/api/trends` returns data with timestamps < 60 seconds old
- **Acceptance**: Sensor poller service is active and writing to database
- **Acceptance**: Chart time range includes current moment (not just historical)
- **Acceptance**: Browser Network tab shows periodic API polling requests

### 3. Enhanced Diagnostics ✅
- **Acceptance**: Console logs indicate when chart refreshes
- **Acceptance**: Data fetch timing visible in logs
- **Acceptance**: Errors (if any) clearly reported in console
- **Acceptance**: Visual indicator on UI when chart updates (optional enhancement)

## User's Current Request

> "let the cloud agent take over please"

**Context**: User has been working on pH chart issues for multiple sessions. Previous fixes deployed but chart still not showing real-time updates. User is frustrated and wants comprehensive cloud agent investigation and resolution.

**User Expectation**:
- Deep investigation of real-time update mechanism
- Complete fix for chart polling/refresh cycle
- Working solution without need for manual page refreshes
- All sensor readings should appear on chart as they are collected

## Contact & Deployment Info

- **Pi IP**: 192.168.88.49:8080
- **Service**: rdwc.service (systemd)
- **Database**: ~/RDWC-v4/data/rdwc.db
- **Branch**: copilot/sweet-cat
- **PR**: #88
- **Current HEAD**: 972a0c7

---

## SESSION HANDOFF COMPLETE

**Status**: Ready for cloud agent investigation and resolution  
**Priority**: HIGH - Real-time chart updates not working  
**User State**: Frustrated, waiting for working solution  
**Next Agent Action**: Investigate polling mechanism in ph_chart.js and implement real-time refresh cycle

**Files to Focus On**:
1. `app/static/js/ph_chart.js` - Chart rendering and polling logic
2. `app/static/index.html` - Chart container and script loading
3. API endpoint: `/api/trends` - Data source verification

**Quick Win Hypothesis**: Missing or broken setInterval() for periodic chart refresh. If polling loop doesn't exist or chart.update() not called, that explains why chart doesn't show new readings.
