# pH Calibration Relocation

**Date:** 2025-11-08  
**Status:** ✅ COMPLETE  
**Commit:** eecc5a5

## Objective
Move pH calibration exclusively to the pH Settings collapsible section within the pH Controller card, removing it from the Settings → Calibration tab.

## User Request
> "i want ph calibration to only be inside ph tab, inside the settings subtab. only there, remove it from the other locations."

## Changes Made

### 1. Added pH Calibration to pH Settings Section (`app/static/index.html`)
**Location:** pH Controller card → pH Settings `<details>` element  
**Position:** After "Save pH Settings" button, before closing `</details>`

**Added Components:**
- Warning banner (CALIB_ENABLE=1 requirement)
- Current pH display with Read/Stabilize/Status buttons
- Buffer solution selector (Mid/Low/High) with value input
- Calibrate and Clear Calibration buttons
- Probe LED controls (On/Off/Blink)
- Message display area
- Calibration log (timestamped events)

**Element ID Suffix:** All IDs suffixed with `-Inline` to avoid conflicts:
- `ph-calib-banner-inline`
- `ph-current-inline`
- `btnPhReadInline`, `btnPhStabilizeInline`, `btnPhStatusInline`
- `ph-buffer-kind-inline`, `ph-buffer-val-inline`
- `btnPhCalibrateInline`, `btnPhClearInline`
- `btnLedsOnInline`, `btnLedsOffInline`, `btnLedsBlinkInline`
- `ph-calib-msg-inline`, `ph-calib-log-inline`

### 2. Wired Event Handlers (`app/static/js/ph.js`)
**Location:** In `wire()` function, after CSV export handlers

**Added Handlers:**
- `btnPhReadInline` → `GET /calib/ph/read`
- `btnPhStabilizeInline` → `GET /calib/ph/read_stable`
- `btnPhStatusInline` → `GET /calib/ph/status`
- `btnPhCalibrateInline` → `POST /calib/ph/{mid|low|high}?value=X.XX`
- `btnPhClearInline` → `POST /calib/ph/clear`
- `btnLedsOnInline` → `POST /calib/leds/on`
- `btnLedsOffInline` → `POST /calib/leds/off`
- `btnLedsBlinkInline` → `POST /calib/leds/blink`

**Helper Functions:**
- `setMsg(text, ok)` - Updates message display and appends to log
- `setCurrent(value)` - Updates current pH reading display
- `setBanner(on)` - Shows/hides CALIB_ENABLE warning
- `checkCaps()` - Checks if calibration is enabled, called on init

### 3. Removed pH Calibration from Settings Tab (`app/static/js/settings.js`)
**Deleted:**
- `phWrap` element creation (40 lines of HTML)
- All pH event handler functions: `read()`, `status()`, `stabilize()`, `caps()`, `doCal()`, `clear()`
- pH button event listener bindings (8 listeners)
- pH initialization calls: `setMsg('')`, `caps()`, `status()`, `read()`
- `panel.appendChild(phWrap)`

**Preserved:**
- EC Calibration wizard
- Dosing Calibration wizard
- Panel-scoped query helper `qP()`

## Final UI Structure

### pH Controller Card
```
pH Controller
├── Summary pills (Today/Week totals)
├── Tabs: Status | Manual | Automation
└── pH Settings <details> (collapsible)
    ├── Target Range (Low/High pH)
    ├── Dosing Parameters (Grow/Micro/Bloom, Max ml/hour, Max ml/day, Mix delay, pH Up ml/s)
    ├── Alert Thresholds (Low/High Alert pH)
    ├── Save pH Settings button
    └── 🧪 pH Probe Calibration ← NEW LOCATION
        ├── Warning banner (CALIB_ENABLE)
        ├── Current pH reading panel
        ├── Buffer solution calibration
        ├── LED controls
        ├── Message display
        └── Calibration log
```

### Settings → Calibration Tab
```
Settings → Calibration
├── EC Calibration (full wizard)
└── Dosing Calibration (full wizard)
```
*pH Calibration removed from this location*

## Benefits
1. **Co-location**: pH calibration is now adjacent to pH-specific settings (targets, dosing parameters, alerts)
2. **Logical Grouping**: pH Settings details section contains all pH controller configuration in one place
3. **Reduced Clutter**: Settings → Calibration tab is simpler with only EC and Dosing
4. **User Intent**: Matches user's mental model: "ph calibration inside ph tab, inside settings subtab"

## Verification Steps (On Live Pi)
1. Open UI → Navigate to pH Controller card
2. Expand "pH Settings" details section
3. Scroll down to see "🧪 pH Probe Calibration" section
4. Test calibration buttons:
   - Click "Read" → verify pH value updates
   - Click "Status" → verify calibration status displays
   - Click "Calibrate" → verify endpoint is called (requires CALIB_ENABLE=1)
5. Verify Settings → Calibration tab no longer shows pH calibration
6. Confirm EC and Dosing calibrations still work in Settings → Calibration

## Files Modified
- `app/static/index.html`: +47 lines (pH calibration HTML in pH Settings)
- `app/static/js/ph.js`: +86 lines (event handlers and initialization)
- `app/static/js/settings.js`: -133 lines (removed pH calibration from Settings)

**Net Change:** +0 lines (simplified Settings, enriched pH Controller)

## Rollback Plan
If issues arise:
1. Revert commit eecc5a5
2. Restart web service: `sudo systemctl restart rdwc-api`
3. pH calibration will return to Settings → Calibration tab

## Testing Notes
- Element IDs use `-Inline` suffix to prevent conflicts with any future global pH calibration references
- Event handlers follow same pattern as Settings calibration (fetch → parse → display)
- Calibration lock (`/tmp/rdwc_calib.lock`) is respected by backend endpoints
- CALIB_ENABLE=1 environment variable still required for write operations

---

**Agent Notes:**
- User's phrasing "inside ph tab, inside the settings subtab" interpreted as pH Controller card → pH Settings `<details>` section
- This is the most logical location as it groups all pH controller configuration together
- Previous reorganization (commit bd030cc) moved EC calibration to Settings → Calibration; this completes the per-controller calibration organization
- Architecture now consistent: controller cards contain controller-specific calibration; Settings → Calibration contains shared/system-level calibration (Dosing pumps)
