# EC Dose History Chart - Fix Verification Guide

## Issue Description
The EC Control tab's "Dose History" chart had critical problems:
1. Console errors on refresh
2. No EC data visible despite backend having data (0.42 mS/cm current reading)
3. Missing setpoint rendering (target range 1.8–2.2 mS/cm not displayed)
4. Static date selectors not updating
5. No live refresh mechanism

## Root Causes Identified
1. **Missing Live Update Mechanism** - Chart had no `fetchLatestSensor()` or auto-refresh
2. **No Rolling Window Updates** - Date selectors were static, didn't track "now"
3. **Potential Annotation Issues** - Detection logic may not have worked reliably

## Fixes Implemented

### 1. Live Data Appending (`fetchLatestSensor()`)
```javascript
// New function added to fetch current EC reading
async function fetchLatestSensor() {
  const r = await fetch('/api/sensors', { cache: 'no-store' });
  const j = await r.json();
  return {
    x: (j.ts * 1000),  // Convert seconds to milliseconds
    ec: Number(j.ec_mscm)  // Already in mS/cm
  };
}

// Integrated into renderChart():
// - Fetches latest sensor data
// - Checks if within current time window
// - Checks if newer than last chart point
// - Appends to ecReadings array if valid
```

### 2. Auto-Refresh Scheduling
```javascript
function scheduleAutoRefresh() {
  // Only refresh if viewing near-realtime (within 5 min of now)
  const isNearRealtime = Math.abs(endMs - now) < 5 * 60 * 1000;
  
  if (isNearRealtime) {
    // Poll every 5 seconds
    refreshTimer = setTimeout(async () => {
      // For presets, roll window forward
      if (currentRange.preset !== 'custom') {
        selectPreset(currentRange.preset);
      } else {
        await loadAndRender();
      }
    }, 5000);
  }
}
```

### 3. Date Selector Updates
```javascript
function updateDateSelectors() {
  // Update datetime-local inputs to show current window bounds
  fromEl.value = formatForInput(new Date(currentRange.start).getTime());
  toEl.value = formatForInput(new Date(currentRange.end).getTime());
}

function formatForInput(ts) {
  // Format: YYYY-MM-DDTHH:mm for datetime-local
  const d = new Date(ts);
  return `${yyyy}-${mm}-${dd}T${hh}:${min}`;
}
```

### 4. Enhanced Annotation Detection
```javascript
// Improved detection with fallbacks and logging
let hasAnnotation = false;
if (Chart.registry && Chart.registry.plugins) {
  const plugin = Chart.registry.plugins.get('annotation');
  hasAnnotation = !!plugin;
  if (hasAnnotation) {
    log('Annotation plugin detected via registry');
  }
}

if (!hasAnnotation) {
  logError('Chart annotation plugin NOT available - target range will not be displayed');
}
```

### 5. Time Bounds Configuration
```javascript
// Changed from Date objects to millisecond timestamps
scales: {
  x: {
    min: currentRange.start ? new Date(currentRange.start).getTime() : undefined,
    max: currentRange.end ? new Date(currentRange.end).getTime() : undefined,
    // ... rest of config
  }
}
```

## Verification Steps

### Pre-Deployment Checks ✅
1. **Syntax Validation** - `node -c app/static/js/ec_chart.js` → PASSED
2. **File Structure** - Verified script loading order in index.html
3. **Backend Endpoints** - Confirmed all required APIs exist:
   - `/api/trends` - Historical EC data
   - `/api/sensors` - Live sensor readings
   - `/api/ec/dose_log` - Dose events
   - `/api/ec/status` - Current status & targets

### Browser Console Verification (To Perform on Pi)

#### Expected Console Output (Success)
```
[EC Chart] Initializing...
[EC Chart] Module loaded
[EC Chart] Selecting preset: 24h
[EC Chart] Time range set: 2025-12-02T19:38:00.000Z to 2025-12-03T19:38:00.000Z
[EC Chart] Loading data for range: 24h
[EC Chart] Fetching EC readings from: /api/trends?from=...&to=...&gran=60&max=2000
[EC Chart] Trends API response - ec points: 147
[EC Chart] Parsed EC readings: 147 points, unit scale: 1
[EC Chart] Fetching dose events from: /api/ec/dose_log?start=...&end=...&limit=500
[EC Chart] Dose events response - count: 8
[EC Chart] renderChart called - ecReadings: 147 doseEvents: 8 status: present
[EC Chart] Appended live EC reading: 0.420 at 2025-12-03T19:38:15.000Z
[EC Chart] Dose counts - grow: 3 micro: 2 bloom: 3
[EC Chart] Y-axis range: 0 - 2 mS/cm, current EC: 0.420
[EC Chart] Annotation plugin detected via registry
[EC Chart] Chart rendered successfully:
[EC Chart]   - EC readings: 148 points
[EC Chart]   - Dose events: 8
[EC Chart]   - Y-axis range: 0 - 2 mS/cm
[EC Chart]   - Annotations: 3
[EC Chart]   - Current EC: 0.420
[EC Chart]   - Target range: 1.8 - 2.2
[EC Chart] Auto-refresh enabled (near real-time)
```

#### Console Errors to Watch For (Should NOT Appear)
```
❌ Invalid scale configuration for scale: y2
❌ Cannot read properties of undefined (reading 'x')
❌ Chart is not a constructor
❌ Annotation plugin not found
❌ Failed to fetch EC readings: [any error]
```

### Visual Verification Checklist

**EC Line Rendering:**
- [ ] Orange/green EC line visible on chart
- [ ] Line spans full 24-hour window (or selected range)
- [ ] Y-axis shows 0 to ~2.0 mS/cm (or higher if current EC demands)
- [ ] Current EC value (~0.42 mS/cm) is within visible range

**Setpoint/Target Range:**
- [ ] Green shaded band visible from 1.8 to 2.2 mS/cm
- [ ] Dashed green centerline at 2.0 mS/cm with "Target: 2.00" label
- [ ] Yellow dashed line at current EC with "Now: 0.42" label

**Dose Event Markers:**
- [ ] Triangle markers for Grow doses (green)
- [ ] Square markers for Micro doses (blue)
- [ ] Circle markers for Bloom doses (purple)
- [ ] Markers appear at correct times
- [ ] Hover tooltips show dose details (pump, duration, EC change)

**Live Updates:**
- [ ] Date selectors show current time window (end = now)
- [ ] Chart advances right as time passes (5-second refresh)
- [ ] New data points appear at right edge
- [ ] Window rolls forward for preset ranges (24h, 7d, etc.)

**Controls:**
- [ ] Range dropdown functional (24h, 7d, 30d, 90d, grow, today, custom)
- [ ] Custom date/time inputs accept manual entry
- [ ] "Apply" button works for custom ranges
- [ ] "Refresh" button reloads chart immediately
- [ ] "Export CSV" button downloads data

### Performance Metrics
- [ ] Initial chart render < 100ms
- [ ] Auto-refresh overhead < 50ms per cycle
- [ ] No memory leaks after 1 hour of operation
- [ ] Network requests cached appropriately

### Error Handling Verification
- [ ] Chart gracefully handles empty data (shows "No doses recorded")
- [ ] Chart handles missing annotation plugin (logs warning but doesn't crash)
- [ ] Chart handles failed API requests (logs error, shows last known data)
- [ ] Chart handles invalid EC values (filters out NaN/null)

## Deployment Instructions

### To Deploy:
```bash
# On development machine
cd /path/to/RDWC-v4
git checkout copilot/soft-manatee
git pull origin copilot/soft-manatee

# Copy to Pi (adjust IP as needed)
scp app/static/js/ec_chart.js pi@192.168.88.49:/home/pi/rdwc/app/static/js/

# On Pi, restart service
ssh pi@192.168.88.49
sudo systemctl restart rdwc
```

### Verification URL:
```
http://192.168.88.49:8080/#ec
```

### Rollback (if needed):
```bash
# On Pi
cd /home/pi/rdwc
git checkout stable-ec-baseline-3b60c32
sudo systemctl restart rdwc
```

## Expected Outcomes

### Acceptance Criteria (All Must Pass)
1. ✅ **Console**: Zero errors on hard refresh (Ctrl+Shift+R) and normal refresh
2. ✅ **Data visibility**: EC line renders from history with proper scale (0–3 mS/cm typical)
3. ✅ **Setpoint**: Target range 1.8–2.2 mS/cm clearly marked as green band
4. ✅ **Live behavior**: Chart moves right as new readings arrive; window end tracks "now" for 24h preset
5. ✅ **Performance**: Single chart instance, no memory leaks, <100ms render time
6. ✅ **Code quality**: No duplicate chart logic; ec_chart.js independent from trends.js

## Technical Notes

### Data Flow:
1. **Initial Load**: `init()` → `wireControls()` → `selectPreset('24h')` → `loadAndRender()`
2. **loadAndRender()**: Fetches trends data, dose events, status → `renderChart()` → `scheduleAutoRefresh()`
3. **renderChart()**: Fetches live sensor → appends if valid → builds Chart.js config → renders
4. **Auto-refresh**: Timeout triggers → re-calls `selectPreset()` or `loadAndRender()` → repeat

### Unit Conversion Logic:
- Historical data from `/api/trends`: Auto-detects units by median value
  - If median > 10: Assumes µS/cm, converts to mS/cm (multiply by 0.001)
  - If median ≤ 10: Assumes already mS/cm, no conversion
- Live data from `/api/sensors`: Uses `ec_mscm` field (already in mS/cm)

### Annotation Plugin:
- Loaded in HTML head: `<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3"></script>`
- Detected via Chart.registry.plugins.get('annotation')
- Provides 3 annotations:
  1. `targetBand` - Green box from low to high target
  2. `setpointLine` - Dashed line at midpoint with label
  3. `currentLine` - Yellow dashed line at current EC with label

## Troubleshooting Guide

### Issue: "No data visible on chart"
**Check:**
- Browser console for fetch errors
- Backend API responses: `curl http://192.168.88.49:8080/api/trends?from=...&to=...&gran=60`
- Database has readings: `sqlite3 /home/pi/rdwc/data/rdwc.db "SELECT COUNT(*) FROM readings;"`

**Fix:**
- If no data in DB: Wait for sensor poller to run
- If API errors: Check rdwc service logs: `sudo journalctl -u rdwc -f`

### Issue: "Annotation plugin not available"
**Check:**
- Browser console for "Annotation plugin NOT available" warning
- Network tab shows chartjs-plugin-annotation@3 loaded successfully
- Chart.registry.plugins.get('annotation') returns truthy value

**Fix:**
- Hard refresh browser (Ctrl+Shift+F5) to clear CDN cache
- Verify CDN is accessible from Pi network
- Check Pi date/time is correct (affects SSL cert validation)

### Issue: "Chart not updating in realtime"
**Check:**
- Console shows "Auto-refresh enabled (near real-time)" message
- Selected range is 24h, 7d, etc. (not custom historical range)
- Window end is within 5 minutes of current time

**Fix:**
- Switch to "Last 24 Hours" preset
- Check refreshTimer is set: Look for timeout messages in console
- Verify /api/sensors endpoint is returning fresh data

### Issue: "Date selectors not updating"
**Check:**
- `updateDateSelectors()` is called after render
- datetime-local inputs have correct IDs: `ecDoseFrom`, `ecDoseTo`

**Fix:**
- Check HTML has correct input IDs
- Verify formatForInput() returns valid datetime-local format

## Success Metrics

### Quantitative:
- 0 console errors on any refresh type
- 100% of EC data points visible and scaled correctly
- Target range visible in 100% of views where targets are configured
- <100ms chart render time (measured via Performance API)
- 5-second refresh cycle maintained for 24h+ without degradation

### Qualitative:
- User can see EC trend at a glance
- Dose events are clearly visible and informative
- Target range provides clear reference for "in range" vs "needs adjustment"
- Chart feels responsive and "alive" with live updates
- UI is intuitive and requires no documentation to understand

## Related Files Modified

| File | Lines Changed | Purpose |
|------|---------------|---------|
| `app/static/js/ec_chart.js` | +142, -15 | Main chart implementation with live updates |

## Related Files NOT Modified (Working as Expected)

| File | Purpose | Status |
|------|---------|--------|
| `app/static/js/trends.js` | Main trends chart (reference implementation) | ✅ Working |
| `app/static/index.html` | HTML structure, script loading | ✅ Correct |
| `app/ec_control.py` | Backend API endpoints | ✅ Working |
| `app/main.py` | FastAPI routing | ✅ Working |

## Commit History

1. **Initial diagnostic plan** - Analyzed issue and created fix plan
2. **Add live data append and auto-refresh** - Implemented core fixes
3. **EC chart fixes complete** - Ready for testing (this commit)
