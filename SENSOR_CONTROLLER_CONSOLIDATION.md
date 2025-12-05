# Unified Sensor Controller - Consolidation Complete

**Status**: ✅ All sensor handling consolidated into single source of truth

## What was accomplished

### Core Module: `app/sensor_controller.py`
- **Single source of truth** for all sensor I/O (EC, pH, RTD)
- **K factor management**: Persisted in settings (not probe memory), restored on every read
- **Calibration endpoints**: `calibrate_ec_low()`, `calibrate_ec_high()`, `clear_ec_calibration()`, `set_ec_k_factor()`
- **Diagnostics**: `get_ec_raw()`, `identify_devices()`, `identify_ec_details()`, `get_ec_calibration_status()`
- **LED control**: `set_sensor_leds()`, `flash_sensor_leds()` unified helpers
- **Locking**: Proper calibration lock (`/tmp/rdwc_calib.lock`) mutual exclusion

### Changes to `app/main.py` - All direct EZO access consolidated
1. **Startup LED hook** → `sensor_controller.set_sensor_leds()`
2. **Sensor read loops** (async & sync) → `sensor_controller.read_sensors()`
3. **LED endpoints**:
   - `POST /api/sensors/leds` → controller
   - `GET /diag/sensors/leds` → controller  
   - `GET /diag/sensors/flash` → controller
4. **Diagnostic endpoints**:
   - `POST /read_now` → controller
   - `POST /fix_ezo` → controller
   - `GET /diag/sensors/once` → controller
5. **EC calibration endpoints** (already unified in prior work):
   - `POST /api/ec/cal/clear` → `sensor_controller.clear_ec_calibration()`
   - `POST /api/ec/cal/low` → `sensor_controller.calibrate_ec_low()`
   - `POST /api/ec/cal/high` → `sensor_controller.calibrate_ec_high()`
   - `POST /api/ec/k` → `sensor_controller.set_ec_k_factor()`
   - `GET /api/ec/cal/status` → `sensor_controller.get_ec_calibration_status()`

### Other modules updated
- `app/sensors_core.py`: `read_all_sensors()` delegates to `sensor_controller.read_sensors()`
- `app/diag.py`: Device identification routed through controller
- `app/debug.py`: EC diagnostics use controller helpers

## Remaining direct EZO access (intentional)
These remain as **pH calibration** is separate from EC/sensor consolidation:
- `app/main.py` lines 1219, 3441, 3469, 3616, 3697, 3706, 3715, 3894, 3936
- These handle pH-specific calibration commands (`Cal,mid`, `Cal,low`, `Cal,high`, etc.)
- pH calibration uses `ezo_i2c_stabilized.EZO` directly per design (not affected by EC consolidation)

## Key design decisions

### K Factor Handling
- EZO EC probe **does NOT persist K** across power cycles
- K is the **only source of truth in settings DB** (`ec.k_value`)
- Every read operation restores K to probe to ensure consistency
- Default K = **0.1** (per sensor label)

### Locking Strategy
- `sensor_controller` uses `/tmp/rdwc_calib.lock` for mutual exclusion
- Calibration operations are atomic: acquire lock → apply command → restore K → release lock
- Read operations are non-blocking (best-effort approach)

### Simulation Mode
- I2C unavailable → graceful fallback with simulated readings
- Windows/dev environment returns safe defaults
- No errors/exceptions thrown; controlled degradation

## Testing
- ✅ `app/main.py` imports without errors
- ✅ `app/sensor_controller` functions work in simulation mode
- ✅ All calibration flow paths integrated

## Deployment readiness
Push to Pi and:
1. Verify EC reads **~1.413 mS/cm** in 1413 µS/cm buffer with K=0.1
2. Confirm `/api/ec/cal/status` returns K=0.1 from settings
3. Test calibration points persist across restarts

## Commits
```
1b11242 Fix syntax error in /diag/sensors/once endpoint (missing except clause)
9b32324 Consolidate all sensor handling into unified sensor_controller
6aac426 Create unified sensor controller module - single source of truth
c9fa330 Fix EC K value default to 0.1 per sensor label
1c41a18 Fix EC calibration K value persistence + Pi-first deployment guide
```
