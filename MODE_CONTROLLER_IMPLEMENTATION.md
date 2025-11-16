# Mode Controller System Implementation

## Overview

The RDWC-v4 system now has a complete and tested mode controller implementation that allows independent control of automation for each subsystem (pH, EC, Chiller, Lights, Circulation).

Each controller can be in one of three modes:
- **Auto**: Automation enabled, controller actively manages its subsystem
- **Manual**: Automation disabled, only manual operations allowed
- **Maintenance**: Special mode for debugging/diagnostics (automation suppressed, safety checks may be relaxed)

## Architecture

### Backend Components

#### 1. Mode Persistence (`app/controller_modes.py`)
- Stores mode state in SQLite database (`settings` table)
- Supports 5 controllers: `ph`, `ec`, `chiller`, `lights`, `circulation`
- Key functions:
  - `get_mode(controller)` - retrieve current mode
  - `set_mode(controller, mode)` - persist mode change
  - `get_all_modes()` - retrieve all controller modes at once

#### 2. Controller Integration

Each controller's automation worker checks its mode before taking action:

**pH Controller** (`app/ph_control.py` line 752-760):
```python
from app.controller_modes import get_mode
if get_mode("ph") != "auto":
    _set_auto_block("mode_hold")
    continue
```

**EC Controller** (`app/ec_control.py` line 1132-1139):
```python
from app.controller_modes import get_mode
if get_mode("ec") != "auto":
    with _auto_lock:
        _auto_last_holding_reason = "mode_hold"
    continue
```

**Chiller Controller** (`app/chiller_control.py` line 244-254):
```python
from app.controller_modes import get_mode
mode = get_mode('chiller')
auto_enabled = bool(int(get_setting('chiller.auto_enabled', '0'))) and mode == 'auto'
if mode != 'auto':
    return False, f'Mode {mode} holds automation'
```

**Lights/Scheduler** (`app/scheduler.py` line 163-174):
```python
from app.controller_modes import get_mode
lights_mode = get_mode("lights")
if self._current_lights_on_time and self._current_lights_off_time and lights_mode == "auto":
    # Proceed with automatic light control
```

#### 3. API Endpoints (`app/main.py`)

```
GET  /api/controller/modes
     → Returns all controller modes and valid mode values
     
GET  /api/controller/{name}/mode
     → Returns current mode for specific controller (ph, ec, chiller, lights, circulation)
     
POST /api/controller/{name}/mode
     → Sets mode for specific controller
     Body: {"mode": "auto"|"manual"|"maintenance"}
```

### Frontend Components

Each tab's JavaScript controller has been updated to:
1. Sync mode from backend on page load
2. Update mode to backend when user changes it
3. Prevent race conditions between localStorage and backend

#### JavaScript Files Updated

**pH Control** (`app/static/js/ph.js`):
- Added `syncModeFromBackend()` - fetches mode from API on load
- Updated `setMode()` with `syncBackend` parameter
- Called `await syncModeFromBackend()` in `initPH()`

**EC Control** (`app/static/js/ec.js`):
- Added `syncModeFromBackend()` 
- Updated `setMode()` with `syncBackend` parameter
- Called `await syncModeFromBackend()` in `init()`

**Chiller Control** (`app/static/js/chiller.js`):
- Added `syncEnvModeFromBackend()`
- Updated `envSetMode()` with `syncBackend` parameter
- Called `await syncEnvModeFromBackend()` on DOMContentLoaded

**Lights Control** (`app/static/js/lights_v2.js`):
- Added `syncModeFromBackend()`
- Updated `setMode()` with `syncBackend` parameter
- Called `await syncModeFromBackend()` in `init()`

**Circulation Control** (`app/static/js/circulation.js`):
- Added `syncCircModeFromBackend()`
- Updated `circSetMode()` with `syncBackend` parameter
- Called `await syncCircModeFromBackend()` on DOMContentLoaded

## Testing

### Test Coverage

#### Integration Tests (`tests/test_mode_integration.py`)
15 tests covering:
- Mode persistence across module reloads
- Retrieving all modes
- Invalid mode/controller rejection
- Each controller's mode awareness
- All valid mode transitions
- Concurrent controller operation with different modes
- Default mode behavior
- Maintenance mode support
- API compatibility

#### API Tests (`tests/test_mode_api.py`)
14 tests covering:
- GET all controller modes
- GET specific controller mode
- POST to set controller mode
- Invalid controller/mode handling
- Mode persistence across HTTP requests
- Independent controller mode management
- Complete mode transition sequences
- Concurrent API calls

#### Existing Tests
3 original tests in `tests/test_controller_modes.py`:
- Basic set/get operations
- Get all modes
- Persistence verification

**Total: 32 mode-related tests, all passing**

### Running Tests

```bash
# All mode tests
pytest tests/test_mode_*.py tests/test_controller_modes.py -v

# Integration tests only
pytest tests/test_mode_integration.py -v

# API tests only
pytest tests/test_mode_api.py -v
```

## Usage Examples

### API Usage

```bash
# Get all controller modes
curl http://localhost:8080/api/controller/modes

# Get pH controller mode
curl http://localhost:8080/api/controller/ph/mode

# Set EC controller to manual mode
curl -X POST http://localhost:8080/api/controller/ec/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "manual"}'

# Set chiller to auto mode
curl -X POST http://localhost:8080/api/controller/chiller/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "auto"}'
```

### Python Usage

```python
from app.controller_modes import get_mode, set_mode, get_all_modes

# Check if pH automation should run
if get_mode("ph") == "auto":
    # Proceed with automation
    pass

# Disable EC automation
set_mode("ec", "manual")

# Get all current modes
modes = get_all_modes()
print(modes)  # {'ph': 'auto', 'ec': 'manual', ...}
```

### UI Usage

Each controller tab has mode buttons:
- Click **Auto** to enable automation
- Click **Manual** to disable automation and allow manual control only
- Click **Maintenance** for diagnostic mode (if available)

The UI automatically syncs with the backend on page load, so the correct mode is always displayed.

## Safety Features

### Mode Enforcement

1. **Automation Only in Auto Mode**: All automated dosing and control only occurs when the controller mode is "auto"
2. **Manual Override Always Available**: Manual operations are always allowed regardless of mode (subject to safety guards)
3. **Independent Controllers**: Each controller's mode is independent - you can have pH on auto while EC is on manual
4. **Persistence**: Modes survive server restarts and page reloads
5. **Race Prevention**: Frontend sync prevents conflicts between localStorage and backend state

### Safety Guards Still Active

Even in maintenance mode, critical safety guards remain:
- E-STOP blocks all operations
- Reservoir volume checks
- Sensor staleness detection
- Hardware protection (relay cooldowns, min on/off times)

## Implementation Status

### ✅ Complete

- [x] Backend mode persistence system
- [x] Controller mode checks in automation loops
- [x] API endpoints for mode management
- [x] Frontend mode synchronization
- [x] Comprehensive test coverage (32 tests)
- [x] All controllers integrated (pH, EC, Chiller, Lights, Circulation)
- [x] Documentation

### ℹ️ Notes

1. **Circulation Controller**: Mode is persisted and can be set via API, but there's currently no circulation automation worker. The mode system is ready for future implementation.

2. **Maintenance Mode**: Implemented in persistence and UI, but behavior is controller-specific. pH and EC use it to show maintenance banners. Lights may use it for testing.

3. **Backward Compatibility**: System defaults to "auto" mode for all controllers, maintaining existing behavior for systems that upgrade.

## Troubleshooting

### Mode Not Syncing to UI

If the UI shows the wrong mode after reload:
1. Check browser console for fetch errors
2. Verify API is accessible: `curl http://localhost:8080/api/controller/modes`
3. Clear localStorage and reload page

### Automation Not Running in Auto Mode

If automation doesn't work despite being in auto mode:
1. Check other safety guards (E-STOP, sensor staleness, daily caps)
2. View controller status endpoint (e.g., `/api/ph/status`)
3. Check for "mode_hold" in blocking reasons

### Mode Changes Not Persisting

If mode reverts after server restart:
1. Verify database write permissions
2. Check that `data/rdwc.db` exists and is writable
3. Review application logs for SQLite errors

## Future Enhancements

Potential improvements:
- Mode change audit log
- Scheduled mode changes (auto during day, manual at night)
- Mode groups (set multiple controllers at once)
- Alert on unexpected mode transitions
- Circulation automation worker implementation

## Summary

The mode controller system is now fully implemented and tested. All controllers respect their persisted modes, the UI properly synchronizes with the backend, and comprehensive tests ensure reliability. The system provides fine-grained control over automation while maintaining all safety features.
