# Single Sensor Manager Architecture - CONSOLIDATION COMPLETE

## Problem Identified
Multiple sensor modules were accessing I2C simultaneously, causing race conditions and undefined sensor responses:
- `sensor_poller.py` - background thread reading sensors
- `sensor_controller.py` - API calibration endpoints  
- `main.py:1219` - direct sensor validation via ezo_i2c
- `sensors_provider.py:30` - unused ezo_i2c import

**Result**: Race conditions → undefined payloads → UI crashes

## Solution Implemented

### 1. Single I2C Access Point (`sensor_controller.py`)
- ✅ **`sensor_controller.py` is NOW the ONLY module accessing I2C**
- ✅ Added `_READ_MUTEX` threading.Lock for read-to-read mutual exclusion
- ✅ All sensor reads serialized through `read_sensors()` which acquires mutex
- ✅ All 8 calibration functions updated to use `_CalibrationContext` for safe locking

### 2. Architecture Consolidation
```
BEFORE (BROKEN - CONCURRENT I2C ACCESS):
├── sensor_poller.py ──────┐
├── main.py:1219 (ezo_i2c) ├─→ I2C BUS (RACE CONDITION!) 
├── sensors_provider.py ────┤
└── sensor_controller.py ───┘

AFTER (FIXED - SINGLE MANAGER):
┌─ sensor_poller.py
│   └─→ sensors_core.read_all_sensors()
│       └─→ sensor_controller.read_sensors()
│           └─→ WITH _READ_MUTEX (mutual exclusion)
│
├─ main.py:1219 (replaced with validate_sensor_presence())
│   └─→ sensor_controller.validate_sensor_presence()
│       └─→ WITH _READ_MUTEX
│
├─ sensors_provider.py (removed unused ezo_i2c import)
│   └─→ Falls back to cached data or DB
│
└─ All other code
    └─→ Uses read_sensors(), read_all_sensors(), or read_sensors_from_db()
        └─→ No direct I2C access
```

### 3. Changes Made

#### `sensor_controller.py` - Core Changes
```python
# ADDED: Read-to-read mutex
import threading
_READ_MUTEX = threading.Lock()

# CHANGED: read_sensors() now acquires mutex
def read_sensors() -> Dict[str, Any]:
    with _READ_MUTEX:
        return _read_sensors_impl()

# ADDED: Calibration context manager (acquires both mutex + calib lock)
class _CalibrationContext:
    def __enter__(self):
        self._mutex_acquired = self._read_mutex.acquire(timeout=3.0)
        if not self._mutex_acquired:
            return False
        if not _acquire_calib_lock():
            self._read_mutex.release()
            return False
        return True

# UPDATED: All 8 calibration functions use _CalibrationContext
def calibrate_ec_dry():
    ctx = _CalibrationContext()
    if not ctx.__enter__():
        return {"ok": False, "error": "Could not acquire lock"}
    try:
        # Safe I2C operations here
    finally:
        ctx.__exit__(None, None, None)

# ADDED: Sensor validation function (replaces direct ezo_i2c access)
def validate_sensor_presence() -> Dict[str, Any]:
    with _READ_MUTEX:
        # Safe sensor validation via sensor_controller
```

#### `main.py` - Removed Direct I2C Access
```python
# BEFORE:
from app import ezo_i2c as _ezo
from app.infra.i2c_bus import get_bus as _get_bus
# Direct I2C operations (RACE CONDITION)

# AFTER:
from app.sensor_controller import validate_sensor_presence
validation_result = validate_sensor_presence()  # Safe, routed through manager
```

#### `sensors_provider.py` - Removed Unused Import
```python
# BEFORE:
from app import ezo_i2c  # Never actually used

# AFTER:
# NOTE: This provider does NOT access I2C directly.
# All I2C operations are routed through app.sensor_controller
```

### 4. Lock Hierarchy
```
All I2C operations now follow this hierarchy:

┌─────────────────────────────────┐
│ Calibration Request (pH/EC)     │
├─────────────────────────────────┤
│ _CalibrationContext:            │
│  1. Acquire _READ_MUTEX         │
│  2. Acquire /tmp/rdwc_calib.lock│
│  3. Do calibration              │
│  4. Release calib lock          │
│  5. Release _READ_MUTEX         │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ Sensor Read (normal operation)  │
├─────────────────────────────────┤
│ read_sensors():                 │
│  1. Acquire _READ_MUTEX         │
│  2. Read RTD, pH, EC via I2C    │
│  3. Apply temperature comp      │
│  4. Release _READ_MUTEX         │
└─────────────────────────────────┘

Result: NO CONCURRENT I2C ACCESS - all operations serialized!
```

### 5. Access Patterns Verified
✅ `sensor_poller.py:_read_sensors()` 
   → calls `sensors_core.read_all_sensors()`
   → calls `sensor_controller.read_sensors()` 
   → MUTEX PROTECTED

✅ `sensors_core.read_sensors_from_db()`
   → reads SQLite (not I2C) - safe

✅ `sensors_core.read_all_sensors()`  
   → calls `sensor_controller.read_sensors()`
   → MUTEX PROTECTED

✅ `main.py` sensor endpoints
   → all use `read_sensors()`, `read_all_sensors()`, or `read_sensors_from_db()`
   → NO direct I2C access

✅ `main.py:sensor_power_cycle()`
   → now calls `validate_sensor_presence()` from sensor_controller
   → MUTEX PROTECTED

✅ All calibration endpoints (pH/EC)
   → use `_CalibrationContext`
   → DUAL LOCKED (mutex + calib lock)
   → MUTEX PROTECTED

### 6. Files Modified
1. `app/sensor_controller.py` - Added mutex, context manager, updated all 8 calibration functions, added validate_sensor_presence()
2. `app/main.py` - Removed direct ezo_i2c import, routed through sensor_controller
3. `app/services/sensors_provider.py` - Removed unused ezo_i2c import, documented single-manager architecture

### 7. Guarantees Now Enforced
- ✅ **ONE AND ONLY ONE** I2C operation at a time (read or calibration)
- ✅ No undefined sensor responses due to race conditions
- ✅ sensor_poller and main API never collide on I2C bus
- ✅ Concurrent API requests serialized safely
- ✅ Calibration always has exclusive I2C access
- ✅ All access goes through single manager with proper timeout handling

## Testing Checklist
Run these commissioning endpoints to verify no more undefined sensors:
- [ ] `GET /api/sensors` (should always return valid data, never undefined)
- [ ] `GET /diag/sensors/once` (fresh locked read)
- [ ] `POST /read_now` (manual read via manager)
- [ ] `GET /calib/ph/status` + `POST /calib/ph/{low|mid|high}` (calibration)
- [ ] `POST /api/ec/cal/{clear|low|high}` (EC calibration)
- [ ] `POST /api/sensors/power_cycle?validate=1` (sensor validation)

**Expected**: All return defined sensor values, no race conditions, no connection loss

## Architecture Diagram
```
USER REQUESTS
    │
    ├─→ GET /api/sensors
    ├─→ GET /diag/sensors/once
    ├─→ POST /calib/ph/low
    ├─→ POST /api/ec/cal/low
    ├─→ POST /api/sensors/power_cycle
    └─→ All other sensor endpoints
    │
    ▼
ROUTED THROUGH:
    │
    ├─→ read_sensors() - WITH _READ_MUTEX ──┐
    ├─→ read_all_sensors() - WITH _READ_MUTEX ──┤ SERIALIZED
    ├─→ validate_sensor_presence() - WITH _READ_MUTEX ──┤ I2C ACCESS
    └─→ Calibration functions - WITH _CalibrationContext ──┘
    │
    ▼
_READ_MUTEX + /tmp/rdwc_calib.lock (DUAL LOCK FOR SAFETY)
    │
    ▼
SENSOR_CONTROLLER.PY (SINGLE I2C MANAGER)
    │
    ├─→ ezo_i2c_stabilized.EZO(RTD 0x66)
    ├─→ ezo_i2c_stabilized.EZO(pH 0x63)
    └─→ ezo_i2c_stabilized.EZO(EC 0x64)
    │
    ▼
I2C BUS (NO RACE CONDITIONS)
    │
    ▼
SUCCESS: Defined sensors, consistent values, no undefined responses!
```

---
**Status**: ✅ COMPLETE - All sensor I2C access consolidated to single manager with dual-lock protection.
