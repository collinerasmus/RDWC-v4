# Cloud Agent Handoff: pH Chart & UI Issues - Session 88

## CRITICAL ISSUES - UNFIXED (2025-11-29 Latest Status)

### 1. pH Chart Still Blank ❌
**Status**: Previous fixes were insufficient. Chart canvas renders but shows no data.
**User Confirmation**: "the graph is still blank. the fixes were not sufficient, it must do a better and deeper job"

### 2. Duplicate "AUTO" Indicators ❌  
**Status**: Still present after cleanup attempts
**Location**: Multiple "AUTO" badges visible in pH Control section
**Root Cause**: Unknown - agent must identify all sources rendering AUTO status

### 3. Orphaned Parameters ❌
**Status**: Two parameter fields lost under Parameters subtab with zero values:
- Max ml/hour: 0
- Max ml/day: 0
**Action Required**: Remove or properly integrate these fields

### 4. Code Duplication ❌
**User Mandate**: "clean up this page and get rid of all the duplicate code. only one source of truth all round!"

## Current Deployment State (2025-11-29)
- **Branch**: copilot/sweet-cat, commit 972a0c7
- **Pi Status**: rdwc.service active, files deployed via scp
- **Build Marker**: BUILD_COMMIT a951afe (stale, should be 972a0c7)
- **API Health**: All endpoints responding (pH 6.96, auto enabled, targets 5.8-6.2)

## Required Deep Investigation

The agent MUST perform comprehensive analysis:

1. **Chart Data Pipeline**:
   - Verify `/api/trends` returns pH series data
   - Check `phReadings` array population in ph_chart.js
   - Confirm Chart.js dataset registration
   - Verify canvas element visibility (CSS/layout issues)
   - Check browser console for JavaScript errors
   - Validate time range calculations

2. **Duplicate AUTO Indicators**:
   - Search ALL templates for "AUTO" badge rendering
   - Identify multiple pH auto status displays
   - Consolidate to SINGLE source of truth
   - Check for: inline badges, header badges, control panel badges

3. **Parameters Fields**:
   - Locate "Max ml/hour" and "Max ml/day" in HTML
   - Determine if these are legacy/deprecated fields
   - Either wire to actual settings OR remove completely

4. **Code Deduplication**:
   - Find all pH status rendering code
   - Find all auto mode indicator code
   - Consolidate duplicate logic
   - Ensure single source updates all UI elements

## Agent Task List (Priority Order)

### TASK 1: Fix Blank Chart (CRITICAL) 🔴
**Issue**: Chart renders but shows no pH data line, no annotations, nothing visible
**Steps**:
1. Add comprehensive logging to ph_chart.js fetchPhReadings()
2. Verify `/api/trends` response structure matches expectations
3. Check if phReadings array is empty or malformed
4. Verify Chart.js datasets are properly constructed
5. Check for CSS/display issues hiding chart content
6. Test with hardcoded sample data to isolate data vs rendering issue
7. Verify time range calculations (default 1h view)

### TASK 2: Remove Duplicate AUTO Indicators (HIGH) 🟡
**Issue**: Multiple "AUTO" badges showing simultaneously
**Steps**:
1. Search index.html for ALL occurrences of "AUTO" badge/pill/indicator
2. Identify each source: header badge, control panel badge, inline badge, etc.
3. Design SINGLE authoritative location for auto status
4. Remove all duplicates
5. Ensure single update point when auto mode toggles

### TASK 3: Clean Up Parameters Subtab (MEDIUM) 🟡
**Issue**: Orphaned "Max ml/hour: 0" and "Max ml/day: 0" fields
**Steps**:
1. Locate these fields in HTML (Parameters subtab)
2. Check if backed by actual settings keys
3. If unused/deprecated: DELETE completely
4. If needed: Wire to proper settings API and validation

### TASK 4: Code Deduplication (MEDIUM) 🟡
**Issue**: User reports duplicate code throughout pH control page
**Steps**:
1. Identify repeated pH status fetching logic
2. Identify repeated auto mode display logic
3. Create single reusable function for status updates
4. Refactor all consumers to use shared function
5. Document single source of truth pattern

**Current Code**:
```javascript
const startISO = schedule.grow_start_date ? new Date(schedule.grow_start_date) : null;
if (startISO && !isNaN(startISO.getTime())) {
  schedule.weeks.forEach((wk) => {
    // ... render bands
  });
  console.log('[pH Chart] Added week bands:', Object.keys(annotations).filter(k=>k.startsWith('wkBand')).length);
} else {
  console.warn('[pH Chart] No grow_start_date in schedule; skipping week bands');
}
```

**Enhancement**:
```javascript
const startISO = schedule.grow_start_date ? new Date(schedule.grow_start_date) : null;
if (startISO && !isNaN(startISO.getTime())) {
  let addedBands = 0;
  schedule.weeks.forEach((wk) => {
    const w = Number(wk.week);
    const low = Number(wk.ph_low);
    const high = Number(wk.ph_high);
    if (!w || isNaN(low) || isNaN(high)) return;
    const xMin = new Date(startISO.getTime() + (w-1) * 7 * 24 * 3600 * 1000);
    const xMax = new Date(startISO.getTime() + w * 7 * 24 * 3600 * 1000);
    // Log filtering decisions
    if (timeMin && xMax < timeMin) {
      console.debug(`[pH Chart] Week ${w} band ends before chart viewport (${xMax.toISOString()} < ${timeMin.toISOString()})`);
      return;
    }
    if (timeMax && xMin > timeMax) {
      console.debug(`[pH Chart] Week ${w} band starts after chart viewport (${xMin.toISOString()} > ${timeMax.toISOString()})`);
      return;
    }
    const key = `wkBand${w}`;
    annotations[key] = { /* ... */ };
    addedBands++;
  });
  console.log(`[pH Chart] Added ${addedBands}/${schedule.weeks.length} week bands within viewport (${timeMin?.toISOString()} to ${timeMax?.toISOString()})`);
  
  // Alert if no bands visible
  if (addedBands === 0 && schedule.weeks.length > 0) {
    console.warn('[pH Chart] ⚠️ No weekly bands visible in current viewport. Grow start date may be misaligned with sensor data.');
  }
} else {
  console.warn('[pH Chart] No grow_start_date in schedule; skipping week bands');
}
```

**Acceptance Criteria**: Console shows clear diagnostic messages about band visibility and filtering

### 3. **Add Fallback Rendering** 🟡
If weekly bands don't overlap viewport, ensure chart still shows:
- Current pH reading line (from `/api/trends`)
- Current targets band (from schedule.ph_band or settings targets)
- Setpoint line (midpoint of current targets)
- Pump activity bars (from dose log)

**Verification**:
- Check if `phReadings` array from `/api/trends` is populated and rendered
- Check if current targets annotation exists in `annotations` object (not dependent on weekly bands)
- Verify dose events bars render independently of weekly bands

### 4. **Browser Cache Resolution** 🔵
**User Action Required** (cannot be done by agent):
1. Hard refresh: `Ctrl+Shift+R` or `Cmd+Shift+R`
2. Clear browser cache for `http://192.168.88.49:8080`
3. Open DevTools (F12) → Network tab → Check "Disable cache" → Reload

**Alternative** (Agent can implement):
Add timestamp-based cache busting to all static resources:
```html
<!-- In index.html around line 2937 -->
<script>
  const cacheBust = Date.now();
  window.__app_version = cacheBust;
  window.BUILD_COMMIT = 'a951afe';
</script>
<script src="/static/js/ph_chart.js?v=<cacheBust>&commit=a951afe"></script>
```

## Screenshots Provided (2025-11-29)

User has attached screenshots showing:
1. **Blank pH Chart**: Large black empty canvas under "Dose History" section
2. **Duplicate AUTO Indicators**: Multiple "AUTO" badges visible in pH Control
3. **Parameters Subtab**: Shows "Max ml/hour: 0" and "Max ml/day: 0" fields (orphaned)
4. **General UI**: Tabs and layout appear correct, but functionality broken

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

### 1. Working pH Chart
- **Acceptance**: Chart displays pH reading line with data points
- **Acceptance**: Dose events show as green triangles overlay
- **Acceptance**: Pump activity shows as purple vertical bars
- **Acceptance**: Hysteresis band visible (green shaded region)
- **Acceptance**: Totals KPI pill shows aggregated dose amount

### 2. Single AUTO Indicator
- **Acceptance**: Only ONE "AUTO" badge/pill visible in entire pH Control section
- **Acceptance**: Badge updates in real-time when auto mode toggled
- **Acceptance**: No duplicate status indicators anywhere

### 3. Clean Parameters Subtab
- **Acceptance**: No orphaned fields with zero values
- **Acceptance**: All visible parameters map to actual settings
- **Acceptance**: Fields update correctly when saved

### 4. Refactored Code
- **Acceptance**: Single function handles pH status updates
- **Acceptance**: No duplicate auto mode display logic
- **Acceptance**: Code comments document single source of truth pattern

## User's Final Mandate

> "clean up this page and get rid of all the duplicate code. only one source of truth all round! this fix must be done by the agent"

The agent MUST:
- Fix ALL issues, not just partial fixes
- Perform DEEP investigation, not superficial changes
- Deliver COMPLETE solution with all acceptance criteria met
- Test thoroughly before marking complete

## Contact & Deployment Info

- **Pi IP**: 192.168.88.49:8080
- **Service**: rdwc.service (systemd)
- **Database**: ~/RDWC-v4/data/rdwc.db
- **Branch**: copilot/sweet-cat
- **PR**: #88
- **Current HEAD**: 972a0c7

---

**Status**: UNFIXED - Previous attempts insufficient. Agent must do better and deeper job. All issues remain open and require resolution.
