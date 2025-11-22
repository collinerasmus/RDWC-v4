# Changelog

## v4.3.0 (2025-11-22) - Session #72 GA Release

**Chiller Circulation Safety + UI Consolidation**

### Added
- **Chiller Circulation Interlock System**
  - Three-way safety validation: main pump, chiller pump, and chiller state
  - Real-time interlock status banner in Chiller tab UI (green when safe, red with details on violations)
  - API endpoint `/api/chiller/status` returns interlock status with detailed violation information
  - Continuous 30-second validation loop with auto-remediation
  - Emergency chiller shutdown on circulation loss
  - AUTO mode enforcement: automatically enables chiller_pump when main_pump is ON

- **Auto-Remediation System**
  - Detects and corrects interlock violations automatically
  - Forces chiller_pump ON in AUTO mode when main_pump is running
  - Emergency shutdown of chiller when pumps fail during operation
  - Comprehensive logging of all remediation actions

- **Comprehensive Test Coverage**
  - 8 pytest cases in `tests/test_chiller_interlock.py`
  - Covers all interlock scenarios: pump failures, mode mismatches, auto-remediation
  - Validates emergency shutdown behavior
  - Tests chiller power-ON blocking when prerequisites not met

### Changed
- **UI Consolidation and Cleanup**
  - Single global E-STOP button in header (top-right, next to build info)
  - Removed duplicate E-STOP buttons from tab navigation
  - Mode control buttons (Auto/Manual/Maintenance/E-STOP) now only appear on System tab
  - Clean tab headers across all controller tabs (pH, EC, Chiller, Circulation, Lights, Schedule)
  - Consistent UI experience across all tabs

- **Chiller Controller Enhancement**
  - Chiller cannot start without both main pump and chiller pump running
  - Interlock status continuously monitored and displayed
  - Improved safety with circulation prerequisite enforcement

### Fixed
- UI navigation clutter with redundant control buttons
- Missing safety interlock for chiller operation without circulation
- Potential for silent chiller-without-circulation operation (safety hazard)
- Inconsistent mode control placement across tabs

### Technical Details
- **Interlock Logic** (`app/chiller_control.py`):
  - Violation types: `main_pump_off`, `chiller_pump_off`, `auto_mode_mismatch`
  - 30-second control loop with auto-remediation
  - Emergency shutdown protocol on circulation loss
  
- **UI Implementation** (`app/static/js/chiller.js`):
  - Real-time banner updates from API
  - Green banner: "🟢 INTERLOCK ACTIVE: Chiller running with circulated pumps"
  - Red banner: "⚠️ INTERLOCK VIOLATION: [specific violation]"

- **API Enhancements**:
  - `interlock_ok` boolean field in `/api/chiller/status`
  - `interlock_details` object with pump states and violation messages
  - Compatible with existing monitoring tools

### Known Limitations
- **Relay POST Timeout**: `/relay/set` endpoint experiencing delays on feature branch (UI controls functional, deferred to Phase 8)
- **Remediation Latency**: 30-second validation loop (future enhancement: event-driven model for <1s latency)

### Deployment Notes
- Production validated on reference system
- Services: rdwc.service + rdwc-sensors.service (both active)
- See `SESSION_72_GA_HANDOFF.md` for full deployment details and validation evidence

### Safety Impact
This release significantly improves system safety by preventing chiller operation without proper water circulation, which could lead to equipment damage or unsafe temperature conditions. The auto-remediation system provides additional reliability by automatically correcting common operational issues.

**Status**: APPROVED FOR GA MERGE - All acceptance criteria met, production validated.

See `SESSION_72_GA_HANDOFF.md` for detailed implementation notes, screenshots, and merge instructions.

---

## v4.2.0 (2025-11-20)

**UI Simplification - Backend-First Focus**

### Removed
- Complex temperature chart implementation (`temp_chart.js`, 359 lines)
- Temperature & chiller history chart from Chiller tab
- Dose history chart wrappers from pH and EC tabs
- `docs/CHILLER_CHART_GUIDE.md` documentation

### Kept
- Sensors tab chart remains intact (temperature, pH, EC trends with timeline controls)
- All backend controller functionality unchanged
- All database action tracking unchanged
- All historical data preserved in `/data/rdwc.db`

### Rationale
- Focus on backend controller reliability before UI complexity
- Reduce code that needs debugging and maintenance
- Keep essential visualization (Sensors chart) for monitoring
- Simplify UI to match Overview tab pattern (status displays, manual controls)

### Action Tracking (Unchanged)
All controller actions continue logging to database:
- `ph_dose_log` / `ec_dose_log` - Dosing events with volume, duration, blocked reasons
- `relay_events` - Chiller, pumps, lights state changes with reasons
- `readings` - Sensor data (temperature, pH, EC) every 10 seconds
- `system_state` - System mode/status changes

### Backend Controllers (Unchanged)
All working independently of UI:
- Sensor poller: Continuous data logging
- pH controller: Auto dosing to targets (5.8-6.2)
- EC controller: Auto dosing to targets
- Chiller controller: Hysteresis-based temperature control (19°C ±0.7°C)
- Circulation controller: Main pump + chiller pump coordination
- Lights controller: Schedule-based operation
- Scheduler: Default and custom schedules
- Mode controller: Auto/Manual/Maintenance state management

### Technical Details
- UI now minimal and functional like Overview tab
- No frontend logic for control decisions
- All settings have backend defaults (system works without UI)
- Controllers work independently, UI displays backend state only

## v4.1.0 (2025-11-16)

**Mode Controller System Implementation**

### Added
- Comprehensive mode controller system for pH, EC, Lights, Chiller, and Circulation subsystems
- Three operational modes per controller: `auto` (automation enabled), `manual` (automation disabled), `maintenance` (diagnostics mode)
- Mode persistence via SQLite settings table (`controller.<name>.mode` keys)
- UI mode selector buttons for each controller tab with real-time status indicators
- Backend synchronization: JavaScript controllers fetch mode from API on page load
- API endpoints:
  - `GET /api/controller/modes` - Retrieve all controller modes
  - `GET /api/controller/{name}/mode` - Get specific controller mode
  - `POST /api/controller/{name}/mode` - Set controller mode with validation
- Comprehensive test suite: 35 tests covering integration, API, and end-to-end scenarios
- Documentation: `MODE_CONTROLLER_IMPLEMENTATION.md`

### Changed
- Refactored pH, EC, chiller, and scheduler automation workers to check mode before executing
- Enhanced JavaScript controllers (ph.js, ec.js, lights_v2.js, chiller.js, circulation.js) with `syncModeFromBackend()` functions
- Improved UI layout and visual consistency across controller tabs
- Mode state now syncs between localStorage and database, preventing divergence

### Fixed
- Browser cache issues preventing UI updates after deployments
- Mode persistence across service restarts
- Race conditions between localStorage and backend state

### Technical Details
- Backend: `app/controller_modes.py` provides centralized mode management
- Controllers check: `if get_mode("controller_name") != "auto": hold_automation()`
- UI sync flow: page load → fetch `/api/controller/{name}/mode` → update UI state → fallback to localStorage
- All changes backward compatible (defaults to `auto` mode)

## v4.0.1 (2025-11-10)

**UI Health Alignment & Stability**
- Aligned Overview summary dot with per-tab controller dots using unified severity precedence (bad > offline > warn > ok)
- Added explicit `offline` state for sensors (gray) to distinguish from critical failures (red)
- Overview chips now classify pH/EC guards into HARD (danger/red), SOFT (warning/amber), NONE (success/green) for accurate operational awareness
- Tooltips display active guards list; mode chips remain unchanged
- Removed lingering TODO from scheduler; clarified midnight lights span behavior
- UI shows consistent statuses across navigation dots and Overview summary after each 6s poll cycle

**Deployment**
- Updated `global_health.js` and `overview.js` with alignment logic
- All controller scripts present and loading correctly (overview, sensors, ph, ec, chiller, circulation, lights, schedule, system)
- No syntax errors; production verified on Pi (192.168.88.49)

## v4.0.0 (2025-10-30)

Highlights:
- Systemd-stable app using Python venv; quick restart and watchdog-ready
- Central relay core: active-low GPIO, idempotent control, MIN_ON/OFF cooldowns, anti-flap protection
- Lights: edge-only scheduler (two edges/day) with guards; no periodic catch-up loops
- Settings: DB-backed, GET/PUT API with UI; lights window preview computed on GET
- Sensors: RTD-first reads with throttled temperature compensation (ΔT ≥ 0.2°C or ≥ 60s)
- Chiller override modes: `auto | force_on | force_off` (AUTO does not thermostat in software)
- Debug endpoints: relay status, relay requests, lights log with summaries
- UI: compact dashboard including sensors, relays, scheduler, chiller control; lights log viewer
- Tools: 30-second smoke script for quick health verification

Thanks to small, atomic changes and strict guardrails, v4 favors predictable, debuggable operations.
