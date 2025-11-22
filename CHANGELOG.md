# Changelog

## v4.3.0 (2025-11-22)

**Phase 5: Schedule Controller - 12-Week Grow Timeline**

### Added
- 12-week grow schedule with phase tracking (seedling → veg → preflower → flower → flush)
- Calendar-style 4x3 grid timeline UI (no horizontal scroll)
- Per-week targets: EC, pH band (low/high), temperature, nutrients (Grow/Micro/Bloom ml/10L), lights schedule
- Current week KPI display (week number, phase, grow start date, day-in-grow)
- AUTO_DEFAULTS optimized for RDWC autoflowers based on industry best practices
- Schedule endpoints:
  - `GET /api/nutrient_schedule` - Retrieve full 12-week schedule with metadata
  - `PUT /api/nutrient_schedule/week/{n}` - Update specific week parameters
  - `POST /api/nutrient_schedule/reset` - Reset to AUTO_DEFAULTS
  - `GET /api/schedule/current_week` - Current week info with targets
  - `GET /api/schedule/plan` - Preview upcoming controller actions (48h dry-run)
- Schedule rendering with phase-specific colors and icons (🌱🌿🌸🌺💧)
- "Seed Defaults" workflow for first-time setup
- Prompt-based week editing (inline grid editing deferred to Phase 6+)

### Database Schema
- `nutrient_schedule` table with columns: week, phase, grow_ml10, micro_ml10, bloom_ml10, ec_target, ph_low, ph_high, temp_target, lights, notes
- Auto-migration for new columns (ph_low, ph_high, temp_target) on existing installs
- Current week calculation from `general.grow_start_date` setting

### UI Layout
- Grid-based timeline (4 columns × 3 rows) replacing horizontal scroll
- Week selector chips (W1-W12) for quick navigation
- Targets panel showing selected week details with Edit/Reset buttons
- Plan preview (upcoming 48h actions)
- Status badges (water-only mode, automation state, EC interval)

### Technical Details
- Backend: `app/schedule_api.py` with SQLite persistence
- Frontend: `app/static/js/schedule.js` with calendar-style rendering
- Phase support: seedling (W1-2), veg (W3-6), preflower (W7-8), flower (W9-10), flush (W11-12)
- Deployed to Pi at commit de7b073

### Documentation
- Research completed for future Grow Diary feature (not part of PR #72 roadmap): `docs/GROW_DIARY_RESEARCH.md`

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
