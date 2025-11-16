# Changelog

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
