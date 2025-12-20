# Settings History & Dynamic Target Bands - Implementation Complete

## Overview
Implemented a complete settings history tracking system to enable visual display of target/hysteresis changes over time on the overview chart. Users can now see when pH, EC, and temperature targets were adjusted and how they impacted the control bands on the live/historical chart view.

## Changes Made

### 1. Database (app/settings.py)
- **New table**: `settings_history` with columns:
  - `id` (INTEGER PRIMARY KEY)
  - `key` (TEXT) - setting key (e.g., `targets.ph_low`)
  - `value` (TEXT) - setting value
  - `ts` (INTEGER) - unix timestamp (seconds)
  - **Indexes**: on `ts` and `key` for fast historical queries

- **Modified function**: `upsert_settings(partial: Dict[str, Any])`
  - Now logs changes to tracked keys: `targets.ph_low`, `targets.ph_high`, `targets.ec_low`, `targets.ec_high`, `targets.temp_target_c`, `temperature.hysteresis`
  - Each change is inserted into `settings_history` with current unix timestamp
  - Logging failures don't block the main setting update (wrapped in try/except)

### 2. API Endpoint (app/main.py)
- **New endpoint**: `GET /api/settings/history`
  - **Query parameters**:
    - `start` (ISO 8601) - history start time (default: 24h ago)
    - `end` (ISO 8601) - history end time (default: now)
    - `keys` (comma-separated) - filter specific settings (default: all tracked keys)
  - **Response**: `[{ts: unix_seconds, key: string, value: string}, ...]`
  - Returns events in chronological order; allows UI to reconstruct target values over time

### 3. Chart Frontend (app/static/js/overview_combined_chart.js)
- **New helper function**: `buildSettingsHistorySeries(history, keys, window)`
  - Converts settings history events into per-key step series arrays
  - Returns `{key: [{x: ms, y: value}, ...]}` dictionary for each tracked key
  - Handles "prior state before window" logic for small zoom ranges

- **Modified onDataFetch**:
  - Added `settingsHistoryUrl` computed with time range
  - Fetches `/api/settings/history` alongside sensor/relay data
  - Returns `settingsHistory` in data payload

- **Modified onRender**:
  - Calls `buildSettingsHistorySeries()` to convert history to per-key step series
  - Stores result in `historyData` variable
  - **pH band**: Now uses `historyData['targets.ph_low']` and `historyData['targets.ph_high']` instead of hardcoded 6.1–6.2
  - **EC band**: Uses `historyData['targets.ec_low']` and `historyData['targets.ec_high']`
  - **Temperature band**: Combines `targets.temp_target_c` and `temperature.hysteresis` history into low/high band via `buildTempBands()` helper
  - Fallback to static values if history is empty (for initial chart render or edge cases)

## Visual Behavior

### Step Function Rendering
When a target setting changes:
1. User updates pH target in settings UI (e.g., 6.1 → 6.0)
2. Change is logged to `settings_history` with unix timestamp
3. Chart fetches updated history via `/api/settings/history`
4. Band dataset is rebuilt as step function: flat line at old value → vertical jump → flat line at new value
5. On zoom to historical range, user sees exact timing of when bands shifted

### Zoom Behavior
- **1-hour live zoom**: Shows current settings only (last value before window.start is carried forward if history empty)
- **24-hour zoom**: Shows all settings changes within the day
- **Custom range**: Shows changes within selected time range

## Testing

Run `python test_settings_history.py` to verify:
1. Settings can be updated via `/api/settings/import`
2. Changes are logged to `settings_history` with correct timestamps
3. `/api/settings/history` returns events grouped by key
4. All 6 tracked keys (pH low/high, EC low/high, Temp target/hysteresis) are properly recorded

### Test Results
```
✓ targets.ph_low
✓ targets.ph_high
✓ targets.ec_low
✓ targets.ec_high
✓ targets.temp_target_c
✓ temperature.hysteresis
```

## Integration Points
- **Settings UI**: Any change to targets/hysteresis via settings panel is automatically logged
- **API imports**: `/api/settings/import` endpoint triggers logging for tracked keys
- **Database queries**: Chart fetches history with ISO time ranges; endpoint handles timestamp conversion

## Deployment Status
✅ Code deployed to Pi:
- `app/settings.py` - settings history table + logging
- `app/main.py` - `/api/settings/history` endpoint
- `app/static/js/overview_combined_chart.js` - dynamic band rendering

✅ API service restarted and tested
✅ Settings history confirmed working end-to-end

## Future Enhancements
- Export historical settings changes as CSV
- UI panel to view/replay settings changes
- Alerts for out-of-band settings changes
- Compare target effectiveness before/after adjustments
