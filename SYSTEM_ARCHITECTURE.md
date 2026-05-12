# RDWC v4 - System Architecture & Logic Diagrams

**Generated:** 2025-11-19 | **Updated:** 2026-05-12  
**Status:** Production-Ready — Phase 1 Complete  
**Test Suite:** 209/209 PASSING ✅  
**Code Quality:** Zero duplication, single-source-of-truth architecture ✅  
**Security:** 0 CodeQL Alerts ✅

---

## 1. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Web UI (Browser)                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ Overview │ │ Sensors  │ │ pH/EC    │ │ Chiller  │          │
│  │  Tab     │ │   Tab    │ │  Tabs    │ │  Tab     │          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
│       │            │             │             │                 │
│       └────────────┴─────────────┴─────────────┘                 │
│                           │                                      │
│                    JavaScript API Calls                          │
│                           │                                      │
└───────────────────────────┼──────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (main.py)                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              RESTful API Endpoints                        │  │
│  │  • /api/controllers/status  (consolidated)               │  │
│  │  • /api/system_mode         (mode management)            │  │
│  │  • /api/relays/*            (relay control)              │  │
│  │  • /api/sensors             (cached readings)            │  │
│  │  • /api/ph/*                (pH controller)              │  │
│  │  • /api/ec/*                (EC controller)              │  │
│  │  • /api/chiller/*           (chiller controller)         │  │
│  └──────────────┬───────────────────────────────────────────┘  │
│                 │                                               │
│  ┌──────────────┴───────────────────────────────────────────┐  │
│  │           Controller Layer                                │  │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐        │  │
│  │  │   pH   │  │   EC   │  │Chiller │  │ Lights │        │  │
│  │  │Control │  │Control │  │Control │  │Schedule│        │  │
│  │  └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘        │  │
│  └──────┼───────────┼───────────┼───────────┼─────────────┘  │
│         │           │           │           │                  │
│  ┌──────┴───────────┴───────────┴───────────┴─────────────┐  │
│  │           System Mode Manager                           │  │
│  │  • Propagates mode changes to all controllers          │  │
│  │  • Modes: Auto / Manual / Maintenance                   │  │
│  └─────────────────────┬───────────────────────────────────┘  │
│                        │                                       │
│  ┌─────────────────────┴───────────────────────────────────┐  │
│  │              Relay Core (relay_core.py)                 │  │
│  │  • Centralized GPIO control                             │  │
│  │  • Active-low relay logic                               │  │
│  │  • Safety guards (cooldowns, E-STOP)                    │  │
│  │  • Min ON/OFF enforcement                               │  │
│  └─────────────────────┬───────────────────────────────────┘  │
└────────────────────────┼─────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Hardware Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  GPIO Relays │  │  I²C Sensors │  │  Pumps       │         │
│  │  (BCM pins)  │  │  (EZO Atlas) │  │  (Dosing)    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│       │                   │                   │                  │
│  ┌────┴───────────────────┴───────────────────┴────┐           │
│  │  Lights  Chiller  Main Pump  pH/EC/Temp Probes  │           │
│  │  Dosing Pumps (pH Up, Grow, Micro, Bloom)       │           │
│  └──────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SQLite Database (rdwc.db)                     │
│  • settings        (configuration key-value store)              │
│  • readings        (sensor history)                             │
│  • system_state    (relay states, controller modes)            │
│  • ph_dose_log     (pH dosing events)                          │
│  • ec_dose_log     (EC dosing events)                          │
│  • dose_events     (pump calibration events)                   │
│  • chiller_events  (state transitions)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Controller Mode Synchronization Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                   User Action: Change Mode                       │
│              (Via UI Header Chips or API Call)                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│          POST /api/system_mode {"mode": "auto"}                 │
│                    (main.py endpoint)                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│         system_mode.set_system_mode(mode)                       │
│         • Validates mode (auto/manual/maintenance)              │
│         • Updates database: settings.system_mode                │
│         • Propagates to all controllers ──┐                     │
└────────────────────────────────────────────┼────────────────────┘
                                             │
                         ┌───────────────────┴───────────────────┐
                         │                                       │
                         ▼                                       ▼
┌────────────────────────────────────┐  ┌────────────────────────────────────┐
│  controller_modes.set_mode("ph")   │  │  controller_modes.set_mode("ec")   │
│  controller_modes.set_mode("ec")   │  │  controller_modes.set_mode("chiller")│
│  controller_modes.set_mode("chiller")│  │  controller_modes.set_mode("lights")│
│  controller_modes.set_mode("lights")│  │  controller_modes.set_mode("circ") │
│  controller_modes.set_mode("circ") │  │  controller_modes.set_mode("sensors")│
│  controller_modes.set_mode("sensors")│  │                                    │
└────────────────┬───────────────────┘  └────────────────────┬───────────────┘
                 │                                            │
                 └────────────────┬───────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│            All Controllers Updated in Database                  │
│         controller_modes table: {name: mode, ts}                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  UI Polling (every 5 seconds)                   │
│           GET /api/controllers/status                           │
│           • Returns consolidated controller states              │
│           • UI updates all tabs automatically                   │
└─────────────────────────────────────────────────────────────────┘
```

**Key Features:**
- **Single source of truth**: Database-backed mode storage
- **Atomic propagation**: All controllers updated in one transaction
- **< 5 second UI reflection**: Polling ensures UI stays synchronized
- **Thread-safe**: Uses database locks for concurrency control

---

## 3. pH Control Logic Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    pH Controller Workflow                        │
└─────────────────────────────────────────────────────────────────┘

                    ┌──────────────┐
                    │  pH Reading  │
                    │  from Sensor │
                    └──────┬───────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ Is Controller in AUTO? │
              └────────┬───────────────┘
                       │
           ┌───────────┴───────────┐
           │                       │
          YES                     NO
           │                       │
           ▼                       ▼
┌──────────────────────┐  ┌──────────────────┐
│  Auto Mode Active    │  │  Manual/Maint    │
│                      │  │  User controls   │
└──────┬───────────────┘  └──────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│      Safety Checks (all must pass)       │
│  1. E-STOP not active                    │
│  2. Sensor reading not stale (< 120s)    │
│  3. EC baseline established              │
│  4. Min dose interval elapsed (30s)      │
│  5. Daily dose cap not exceeded          │
│  6. pH not already in target range       │
└──────┬───────────────────────────────────┘
       │
       ├─ FAIL ─► Block dose, set holding_reason
       │
       ▼ PASS
┌──────────────────────────────────────────┐
│       Calculate Dose Amount              │
│  • Check if learned value exists         │
│  • Use learned: dose = Δ_pH × learned_ml │
│  • No learned: use conservative default  │
│  • Apply safety cap (max 5ml per dose)   │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│         Execute Dose                      │
│  1. Acquire non-blocking lock             │
│  2. Activate pH Up pump (relay)           │
│  3. Run for calculated duration (ms)      │
│  4. Log to ph_dose_log table              │
│  5. Release lock                          │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│       Update Learner (if enabled)        │
│  • Track doses and pH changes            │
│  • Calculate ml_per_pH when enough data  │
│  • Store learned value in database       │
└──────────────────────────────────────────┘
```

**Safety Guards:**
- `press_cap`: Max 5ml per single dose
- `daily_cap`: Configurable daily limit (e.g., 100ml/day)
- `interval`: Minimum 30 seconds between doses
- `stale`: Won't dose if sensor reading > 120 seconds old
- `ec_guard`: Won't dose if EC baseline not established
- `estop`: Blocks all dosing when E-STOP active

---

## 4. Chiller Control Logic (Thermostat)

```
┌─────────────────────────────────────────────────────────────────┐
│              Chiller Thermostat Control Loop                    │
│              (Compressor-Safe Implementation)                   │
└─────────────────────────────────────────────────────────────────┘

                    ┌──────────────┐
                    │  Temperature │
                    │   Reading    │
                    └──────┬───────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ Is Chiller in AUTO?    │
              └────────┬───────────────┘
                       │
           ┌───────────┴───────────┐
           │                       │
          YES                     NO
           │                       │
           ▼                       ▼
┌──────────────────────┐  ┌──────────────────┐
│  Auto Mode Active    │  │  Manual Override │
│  (Thermostat Logic)  │  │  (force_on/off)  │
└──────┬───────────────┘  └──────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│      Determine Target Action              │
│  Target Temp: 19.0°C (configurable)      │
│  Hysteresis: 0.7°C (configurable)        │
│                                           │
│  IF temp > target + hysteresis/2:        │
│     desired_state = ON                    │
│  ELSE IF temp < target - hysteresis/2:   │
│     desired_state = OFF                   │
│  ELSE:                                    │
│     desired_state = maintain current      │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│      Compressor Protection Checks         │
│  1. Min ON time: 60 seconds              │
│     • Don't turn OFF if ON < 60s         │
│  2. Min OFF time: 300 seconds (5 min)    │
│     • Don't turn ON if OFF < 300s        │
│  3. Max 8 cycles per hour                │
└──────┬───────────────────────────────────┘
       │
       ├─ Protection Active ─► Maintain current state
       │                       (wait for timer)
       ▼ Protection OK
┌──────────────────────────────────────────┐
│         Change Chiller State              │
│  1. Set chiller_power relay               │
│  2. Set chiller_pump relay                │
│  3. Log event to chiller_events table     │
│  4. Update internal state tracking        │
└──────────────────────────────────────────┘
```

**Compressor Protection:**
- **min_on_seconds**: 60s - Prevents short-cycling damage
- **min_off_seconds**: 300s - Allows compressor to equalize pressure
- **hysteresis**: 0.7°C - Prevents rapid on/off oscillation
- **Events logging**: All state transitions logged for diagnostics

**Temperature Ranges (Cannabis-optimized):**
- Optimal: 18.0-20.0°C
- Acceptable: 16.0-24.0°C
- Critical: < 14.0°C or > 26.0°C

---

## 5. Relay Control Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Relay Control Flow                           │
│               (Centralized in relays_core.py)                   │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│  API Request         │
│  (any controller)    │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│    set_relay(name, on, reason, actor)    │
│         (relays_core.py)                 │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│      Pre-Flight Checks                    │
│  1. E-STOP check                         │
│  2. Reason whitelist (for protected)     │
│  3. Min OFF cooldown check               │
│  4. Min ON runtime check                 │
│  5. Idempotency (already in state?)      │
└──────┬───────────────────────────────────┘
       │
       ├─ BLOCKED ─► Return {changed: false, reason}
       │
       ▼ PASS
┌──────────────────────────────────────────┐
│         GPIO Operation                    │
│  1. Write to BCM pin (active-low)        │
│     • HIGH = relay OFF                    │
│     • LOW = relay ON                      │
│  2. Update shadow state (in-memory)      │
│  3. Persist to database (relay_state)    │
│  4. Log event (relay_guard)              │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│    Return Success                         │
│    {changed: true, state, cooldown, ...} │
└──────────────────────────────────────────┘
```

**Protected Relays:**
- `lights`: Requires whitelisted reason (schedule, manual, maintenance)
- `chiller_power`: Enforces min ON/OFF times

**Relay Mapping (BCM pins):**
```
main_pump:      BCM 12
chiller_pump:   BCM 16
chiller_power:  BCM 20
lights:         BCM 21
ph_up:          BCM 17
grow:           BCM 27
micro:          BCM 22
bloom:          BCM 23
sensor_power:   BCM 24 (optional)
```

---

## 6. Sensor Reading Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                 Sensor Reading Architecture                      │
└─────────────────────────────────────────────────────────────────┘

Background Process (sensor_poller.py - systemd service)
═══════════════════════════════════════════════════════
                    │
                    ▼
        ┌───────────────────────┐
        │  Every 10 seconds     │
        └───────┬───────────────┘
                │
                ▼
    ┌───────────────────────────┐
    │  Acquire I²C Lock         │
    │  (/tmp/rdwc_calib.lock)   │
    └───────┬───────────────────┘
            │
            ▼
    ┌───────────────────────────────────┐
    │  Read EZO Sensors via I²C         │
    │  • RTD (Temp): addr 0x66          │
    │  • pH Probe:   addr 0x63          │
    │  • EC Probe:   addr 0x64          │
    └───────┬───────────────────────────┘
            │
            ▼
    ┌───────────────────────────────────┐
    │  Temperature Compensation         │
    │  • Send temp to pH probe (if Δ≥0.2°C)│
    │  • Send temp to EC probe (if Δ≥0.2°C)│
    │  • Throttle to prevent I²C spam   │
    └───────┬───────────────────────────┘
            │
            ▼
    ┌───────────────────────────────────┐
    │  Store to Database                │
    │  • Table: readings                │
    │  • Columns: ts, temp_c, ph, ec_ms │
    └───────┬───────────────────────────┘
            │
            ▼
    ┌───────────────────────────────────┐
    │  Update In-Memory Cache           │
    │  (_last, _last_t in main.py)      │
    └───────────────────────────────────┘

Web UI Request (on-demand)
═══════════════════════════
                    │
                    ▼
        ┌───────────────────────┐
        │  GET /api/sensors     │
        └───────┬───────────────┘
                │
                ▼
    ┌───────────────────────────────────┐
    │  Return Cached Reading            │
    │  • From in-memory cache           │
    │  • Falls back to DB if cache old  │
    │  • Age shown in response          │
    └───────────────────────────────────┘

Manual Read (calibration/diagnostics)
════════════════════════════════════════
                    │
                    ▼
        ┌───────────────────────┐
        │  POST /read_now       │
        │  GET /diag/sensors/once│
        └───────┬───────────────┘
                │
                ▼
    ┌───────────────────────────────────┐
    │  Acquire Calibration Lock         │
    │  (blocks background poller)       │
    └───────┬───────────────────────────┘
            │
            ▼
    ┌───────────────────────────────────┐
    │  Direct I²C Read                  │
    │  • One-time reading               │
    │  • Does NOT update cache          │
    │  • Returns immediately             │
    └───────────────────────────────────┘
```

**Key Features:**
- **Separate poller**: Background service prevents UI from blocking on I²C
- **Cached API**: Web UI gets fast responses from cache
- **Lock mechanism**: Prevents I²C contention between poller and calibration
- **Temperature compensation**: Automated with throttling to prevent spam

---

## 7. Data Flow Summary

```
Hardware Sensors → Background Poller → SQLite DB → Web API → Browser UI
      ↓                                    ↓
   I²C Bus                           In-Memory Cache
   (0x63, 0x64, 0x66)                (_last, _last_t)

User Actions → Browser UI → API Endpoints → Controllers → Relay Core → GPIO
                                   ↓                          ↓
                              SQLite DB                  Hardware Relays
                              (modes, events)            (BCM pins)
```

**Database Tables:**
- `settings`: Configuration key-value store
- `readings`: Sensor history (temp, pH, EC)
- `controller_modes`: Current mode for each controller
- `relay_state`: Last known relay states
- `ph_dose_log`: pH dosing history
- `ec_dose_log`: EC dosing history
- `dose_events`: Pump calibration events
- `chiller_events`: Chiller state transitions

---

## 8. API Endpoints Summary

### Core System
- `GET /health` - System health check
- `GET /api/version` - Asset version for cache busting
- `GET /api/system_mode` - Get current system mode
- `POST /api/system_mode` - Set system mode (auto/manual/maintenance)

### Controller Status
- `GET /api/controllers/status` - **Consolidated status** (all controllers, one call)

### Relays
- `GET /api/relays/status` - All relay states
- `POST /api/relays/mode` - Change relay control mode
- `POST /api/relays/estop/toggle` - Toggle E-STOP

### Sensors
- `GET /api/sensors` - Cached sensor readings
- `POST /read_now` - Force immediate sensor read
- `GET /diag/sensors/once` - Diagnostic sensor read

### pH Control
- `GET /api/ph/status` - pH controller status
- `POST /api/ph/dose` - Manual pH dose
- `GET /api/ph/auto/status` - Auto dosing status
- `POST /api/ph/auto/learn/reset` - Reset learned value

### EC Control
- `GET /api/ec/status` - EC controller status
- `POST /api/ec/dose` - Manual EC dose (grow/micro/bloom)
- `GET /api/ec/auto/status` - Auto dosing status
- `POST /api/ec/auto/learn/reset` - Reset learned value

### Chiller
- `GET /api/chiller/status` - Chiller state
- `POST /api/controller/chiller/mode` - Set chiller mode
- `GET /api/chiller/events` - State transition history

### Calibration
- `GET /calib/ph/status` - pH probe calibration status
- `POST /calib/ph/{mid|low|high}` - Calibrate pH probe
- `GET /calib/dose/pumps` - Pump calibration status
- `POST /calib/dose/run` - Run pump calibration
- `POST /calib/dose/commit` - Commit pump calibration

---

## 9. UI Component Architecture

```
Index.html (Single Page Application)
═════════════════════════════════════

Tab-Based Navigation
────────────────────
┌─────────────────────────────────────────────────────────────┐
│  [Overview] [Sensors] [pH] [EC] [Chiller] [Lights] [...]   │
└─────────────────────────────────────────────────────────────┘

Each Tab Structure:
───────────────────
┌─────────────────────────────────────┐
│ Header                              │
│  • Title                            │
│  • Mode Chips (Auto/Manual/Maint)  │ ← **Single source of truth**
│  • Status indicators                │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│ Readings Section                    │
│  • Current values                   │
│  • Learned value KPI (pH/EC only)  │
│  • Timestamps                       │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│ Graph Section                       │
│  • Historical chart                 │
│  • Time range selector              │
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│ Settings Section (collapsible)      │
│  • Parameters (targets, thresholds) │
│  • Manual controls                  │
│  • Automation settings              │
│  • Pump calibration (pH/EC only)   │
└─────────────────────────────────────┘

JavaScript Modules:
───────────────────
• overview.js - Dashboard, consolidated status polling
• sensors.js - Sensor display and manual read
• sensors_calib.js - **NEW** Pump calibration workflow
• ph.js - pH control, learned value display
• ec.js - EC control, learned value display
• chiller.js - Chiller control (cleaned up)
• relays_v2.js - Relay status and mode sync
• schedule.js - Lights scheduling
```

**Key UI Improvements (PR #63):**
1. **Accordion Independence**: Sensors Settings accordions can now open multiple at once
2. **Pump Calibration Moved**: pH pump in pH tab, EC pumps in EC tab (no longer in Sensors)
3. **Mode Chips Only**: Redundant automation buttons removed, mode chips are sole control
4. **Learned Value KPIs**: Visible in readings row for quick reference
5. **Clear Learned Buttons**: In Settings > Automation with confirmation dialogs

---

## 10. Deployment Architecture

```
Raspberry Pi (Production)
═════════════════════════

Systemd Services:
─────────────────
• rdwc.service           - Main FastAPI application (port 8080)
• rdwc-sensors.service   - Background sensor poller (separate process)

File Structure:
───────────────
/opt/rdwc/ (or ~/RDWC-v4/)
├── app/                 - Python application
│   ├── main.py          - FastAPI app entry
│   ├── *_control.py     - Controller modules
│   └── static/          - Frontend assets
├── data/
│   └── rdwc.db          - SQLite database
├── tests/               - Test suite (156 tests)
├── deploy/              - Deployment scripts
└── systemd/             - Service definitions

Environment:
────────────
• RDWC_DB=/opt/rdwc/data/rdwc.db
• PYTHONPATH=/opt/rdwc:$PYTHONPATH
• Hardware: Raspberry Pi 4 (or compatible)
• Python: 3.9+
• I²C enabled, GPIO accessible
```

---

## 11. Testing Strategy

```
Test Coverage: 156 Tests (All Passing ✅)
═════════════════════════════════════════

Unit Tests:
───────────
• test_config_basic.py - Configuration parsing
• test_dosing_math_basic.py - Dosing calculations
• test_sensors_core_basic.py - Sensor reading logic
• test_relay_guard_basic.py - Relay protection logic

Integration Tests:
──────────────────
• test_mode_integration.py - Mode propagation
• test_controller_modes.py - Controller mode management
• test_ph_automation_production.py - pH auto dosing
• test_ec_control.py - EC control logic

API Tests:
──────────
• test_controllers_status_api.py - **NEW** Consolidated status endpoint (10 tests)
• test_relays_status_api.py - Relay status API
• test_mode_api.py - Mode change API

Controller Logic Tests:
───────────────────────
• test_chiller_control_logic.py - **NEW** Compressor protection (3 tests)
• test_chiller_events_api.py - **NEW** Events logging (3 tests)

End-to-End Tests:
─────────────────
• test_mode_system_e2e.py - Complete mode workflow
• test_commissioning_snapshot_api.py - System snapshot

Running Tests:
──────────────
$ cd /opt/rdwc
$ PYTHONPATH=/opt/rdwc:$PYTHONPATH python3 -m pytest tests/ -v
```

---

## 12. Security & Safety

**Hardware Safety:**
- E-STOP functionality (blocks all dosing and protected relays)
- Min ON/OFF times prevent compressor damage
- Cooldown periods prevent relay damage
- Dose caps (per-press, daily limits)

**Software Safety:**
- Non-blocking locks prevent deadlocks
- Stale sensor detection (won't dose on old readings)
- Active-low relay logic (fail-safe)
- Idempotent operations

**Security:**
- CodeQL: 0 alerts ✅
- Input validation on all API endpoints
- Database timeouts prevent hung connections
- No direct hardware access from web process (sensor poller is separate)

---

## 13. System State Diagram

```
System Operating Modes
══════════════════════

        ┌──────────────────┐
        │     MANUAL       │
        │   (User Control) │
        └────┬────────┬────┘
             │        │
    ┌────────┘        └────────┐
    │                          │
    │                          │
    ▼                          ▼
┌────────────┐          ┌────────────┐
│    AUTO    │          │MAINTENANCE │
│ (Automated)│          │  (Testing) │
└────────────┘          └────────────┘

Mode Transitions:
─────────────────
• Any mode → Any mode (instant, via API)
• Propagates to all 6 controllers
• UI reflects change within 5 seconds
• Database-persisted (survives restart)

Controller States per Mode:
────────────────────────────
AUTO:
  • pH: Auto dosing enabled
  • EC: Auto dosing enabled
  • Chiller: Thermostat active
  • Lights: Schedule active
  • Circulation: Always on
  • Sensors: Background polling

MANUAL:
  • All: User must control manually
  • Safety guards still active
  • Sensors: Background polling continues

MAINTENANCE:
  • All: Manual control with reduced safety
  • E-STOP still enforced
  • Dosing available with looser caps
  • Sensors: Manual reads available
```

---

## Document Version

**Version:** 1.0  
**Generated:** 2025-11-19  
**Commit:** ba2d680  
**Branch:** copilot/finish-task-session-63  
**Status:** ✅ Production Ready Checkpoint

**Next Steps:**
1. Review this architecture document
2. Verify system matches expected behavior
3. Proceed with UI enhancements if satisfied
4. Bookmark this document as the current system baseline
