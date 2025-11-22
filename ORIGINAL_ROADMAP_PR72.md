# Original Roadmap from PR #72

**Source**: GitHub Issue/PR #72 Original Prompt  
**Date Retrieved**: 2025-11-22

## Complete Phase Plan from Original Request

### Phase 1 & 2: UI Cleanup ✅ COMPLETED
- Remove mode selection buttons from Overview, Sensors, Scheduler tabs (keep only in System tab)
- Remove duplicate calibration sections from Sensors tab (pH Pump, EC Pumps)
- Ensure correct calibration sections remain in pH and EC tabs

**Status**: Completed in branch `copilot/remove-duplicate-pump-calibrations`

---

### Phase 3: Circulation Safety Interlock ✅ COMPLETED
**User Requirements**:
> "if the chiller is running the chiller pump must be running. if the chiller pump cannot run then the chiller must not run, but it is most important that the chiller must run so the chiller pump must be started if not running and the chiller must run."

**Implementation**:
- Three-layer safety system (Main Pump → Chiller Pump → Chiller Power)
- Backend safety logic in `app/relays_core.py`:
  - `set_chiller_power()` checks main pump and auto-starts chiller pump
  - `set_chiller_pump()` prevents OFF while chiller running
  - Returns detailed interlock status
- Frontend UI in `app/static/index.html` and `app/static/js/circulation.js`:
  - Visual sections with green (main) and blue (chiller) styling
  - Real-time interlock status banner (violation/active/standby)
  - Chiller status indicator
  - Disabled pump OFF button when chiller running
- Centralized E-STOP store (`app/static/js/estop_store.js`) for consistent UI state
- Fixed POST endpoint timeouts (middleware body consumption issue)

**Status**: Completed after 4 bug fixes (state monitoring, error handling, middleware, E-STOP UI consolidation)

---

### Phase 4: Lights Schedule Midnight Fix ⚠️ HIGH PRIORITY
**User Report**:
> "with the previous observations it seemed the control got confused with the 'on' cycle spreading over the next day and the lights would go off at 00:00 instead of 12:00."

**Problem**: 
- Backend scheduler window calculation doesn't handle midnight crossover correctly
- Example: ON at 20:00, OFF at 08:00 (next day) → lights turn off at wrong time

**Required Changes**:
- Fix window calculation in `app/scheduler.py` or `app/settings.py`
- Handle day-boundary transitions (today's cycle vs yesterday's cycle)
- Add unit tests for various schedule configurations
- Test on hardware with real schedule crossing midnight

**Estimated Effort**: 3-4 hours  
**Status**: Not yet implemented

---

### Phase 5: Complete 12-Week Grow Schedule ✅ COMPLETED
**User Requirements**:
> "the schedluer seems incomplete. please finish it and populate it according to EHC guidelines and make sure there guidelines are witing best growth parimiters for auto canabis plants."

**Implementation**:
- 12-week timeline with 5 phases (seedling 1-2, veg 3-6, preflower 7-8, flower 9-10, flush 11-12)
- AUTO_DEFAULTS with per-week targets: EC, pH band, temp, nutrients (Grow/Micro/Bloom), lights, notes
- Calendar-style 4×3 grid UI (no horizontal scroll)
- Current week KPI display (week/phase/start date/day-in-grow)
- SQLite `nutrient_schedule` table with auto-migration
- Backend: `app/schedule_api.py` with GET/PUT/POST endpoints
- Frontend: `app/static/js/schedule.js` with grid rendering and phase icons

**Status**: Completed, deployed to Pi at commit de7b073 → 70fc0c0

---

### Phase 6: System Tab Enhancements
**User Requirements**:
> "there are 6 subtabs that i would like to see. change this page to no hidden information. it must be a colomn style with all information sorted by group or type or section."

**Goal**: Replace System tab subtabs with comprehensive single-column information display

**Sections to Include**:
1. **Raspberry Pi Information**
   - CPU usage, temperature, clock speed
   - RAM usage (total, used, free, %)
   - Disk usage (total, used, free, %)
   - Uptime, load average

2. **Software Information**
   - RDWC version, build date
   - Python version
   - FastAPI version
   - Service status (API, sensor poller)
   - Git commit hash, branch

3. **Environment Information**
   - Sensor addresses (I²C)
   - Relay GPIO pin mappings
   - Connected devices
   - I²C bus status

4. **Database Information**
   - Database file size
   - Record counts (readings, doses, logs)
   - Last vacuum/analyze
   - Oldest/newest record timestamps

5. **Network Information**
   - IP address(es)
   - Hostname
   - Network interfaces
   - DNS servers

6. **Process Information**
   - Running services (systemd)
   - PIDs for RDWC processes
   - Open file descriptors
   - Memory per process

**Implementation Plan**:
- Backend: New API endpoint `/api/system/info` in `app/main.py`
- Frontend: Redesign System tab with single-column layout
- Real-time updates every 10 seconds
- Use `psutil` for system metrics
- Parse systemd status for service info

**Estimated Effort**: 4-6 hours  
**Status**: Not yet implemented

---

### Phase 7: UI Theme Unification
**User Requirements**:
> "please make the theme and look and feel of the ui unified accross all tabs on the entire ui. this will be our final ui change now."

**Goal**: Standardize visual design across all tabs for professional appearance

**Tasks**:
1. **Color Scheme Audit**
   - Document current colors used
   - Define primary, secondary, accent, success, warning, danger colors
   - Create CSS variable system

2. **Button Standardization**
   - Consistent sizing (height, padding)
   - Unified hover/active states
   - Disabled state styling
   - Icon alignment

3. **Card Layout Consistency**
   - Standard padding, margins, border-radius
   - Header styling (title, subtitle, actions)
   - Body content spacing
   - Footer alignment

4. **Typography System**
   - Heading sizes (h1-h6)
   - Body text sizes
   - Monospace for values
   - Line heights, letter spacing

5. **Status Indicators**
   - Badges (success, warning, error, neutral)
   - Icons (consistent emoji or font-awesome)
   - Spinner/loading states
   - Tooltips

6. **Form Elements**
   - Input fields (text, number, select)
   - Checkbox/radio buttons
   - Labels and help text
   - Validation states

**Implementation**:
- Create `app/static/css/theme.css` with CSS variables
- Refactor inline styles to classes
- Update all tabs to use theme classes
- Test dark mode consistency

**Estimated Effort**: 6-8 hours  
**Status**: Not yet implemented

---

### Phase 8: Backend Verification
**Goal**: Ensure all backend functionality is stable and tested before documentation phase

**Tasks**:
1. **Run Full Test Suite**
   - All pytest tests pass
   - Code coverage > 80%
   - No skipped tests without reason

2. **Add Missing Tests**
   - Scheduler midnight crossover scenarios
   - Circulation interlock edge cases
   - Schedule API validation

3. **Integration Testing**
   - End-to-end workflows (calibration, dosing, control loops)
   - Multi-controller interactions
   - Database migrations

4. **Performance Testing**
   - API response times < 100ms
   - Sensor polling cycle time < 10s
   - Database query optimization

**Estimated Effort**: 4-6 hours  
**Status**: Not yet implemented

---

### Phase 9: As-Built Documentation 📝
**User Requirements**:
> "once everything is 100% i want us to hard benchmak the point as 'As-Built' then you update all documents and do proper housekeeping and make everyhting commissioning ready. create any outstanding engineering documentation like flow sheets and P&ID's and operating philosophy and operating manual and maintenance manual and equipment list and io list and signal list and all those i missed and update the ones that already excist."

**Goal**: Create professional engineering-standard documentation package

**Critical Documents Needed**:

1. **P&ID (Piping & Instrumentation Diagram)**
   - Schematic drawing of RDWC system
   - Sensors, actuators, plumbing, electrical
   - Control logic symbols (interlocks, alarms)
   - Industry-standard symbology (ISA-5.1)

2. **Electrical Schematics**
   - Raspberry Pi GPIO pinout
   - Relay board wiring (active-low configuration)
   - I²C bus connections (Atlas EZO sensors)
   - Power distribution (5V, 12V, 120VAC)
   - Fusing and protection

3. **IO List (Input/Output List)**
   - All sensors (address, type, range, units)
   - All actuators (GPIO pin, type, power rating)
   - Signal types (analog/digital, voltage/current)
   - Fail-safe states

4. **Signal List**
   - Control signals (relay commands, dosing triggers)
   - Interlocks (circulation safety, E-STOP)
   - Alarms (pH out of range, EC drift, temperature)
   - Status indicators (online, calibrated, error)

5. **Equipment List**
   - Manufacturer, model number, part number
   - Specifications (flow rate, accuracy, power)
   - Installation date, warranty
   - Replacement sources

6. **Operating Philosophy**
   - Control strategy overview (cascading loops, setpoint tracking)
   - Safety system hierarchy (E-STOP > interlocks > manual > auto)
   - Alarm management (priorities, escalation)
   - Mode logic (auto/manual/maintenance)

7. **Operating Manual**
   - Startup sequence
   - Normal operation procedures
   - Shutdown sequence
   - Emergency procedures (E-STOP, power loss, leak detection)
   - Troubleshooting guide

8. **Maintenance Manual**
   - Calibration procedures (pH, EC, dosing pumps)
   - Preventive maintenance schedule (weekly, monthly, quarterly)
   - Sensor cleaning (probes, RTD)
   - Database maintenance (vacuum, backup)
   - Software updates (deployment, rollback)

9. **Commissioning Checklist**
   - Pre-startup inspection
   - Initial calibration
   - Loop tuning (if PID implemented)
   - Functional testing (all modes, interlocks)
   - Performance verification (accuracy, repeatability)
   - Documentation review

**Documentation Tools**:
- Markdown for text documents
- Mermaid diagrams for flowcharts
- Draw.io or LibreCAD for schematics
- Sphinx or MkDocs for compiled documentation site

**Estimated Effort**: 16-20 hours  
**Status**: Not yet implemented

---

### Phase 10: Version Control & Release
**Goal**: Tag stable "As-Built" version for production deployment

**Tasks**:
1. **Git Tagging**
   - Tag as `v1.0.0-as-built`
   - Create annotated tag with detailed message
   - Push tag to GitHub

2. **Release Notes**
   - Comprehensive changelog
   - Known limitations
   - Hardware requirements
   - Installation instructions
   - Upgrade path from previous versions

3. **CHANGELOG.md Update**
   - Finalize all phase entries
   - Add version history
   - Link to GitHub releases

4. **Deployment Procedures**
   - Step-by-step Pi setup
   - Service configuration (systemd)
   - Database initialization
   - First-time calibration workflow

5. **Rollback Procedures**
   - How to revert to previous version
   - Database backup/restore
   - Service troubleshooting

**Estimated Effort**: 2-3 hours  
**Status**: Not yet implemented

---

### Phase 11: Deployment & Final Testing
**Goal**: Validate complete system on clean Raspberry Pi installation

**Tasks**:
1. **Clean Pi Installation**
   - Fresh Raspberry Pi OS
   - Follow deployment instructions exactly
   - Document any missing steps

2. **Service Verification**
   - API starts correctly
   - Sensor poller runs without errors
   - Database initializes properly
   - Web UI loads all tabs

3. **Functional Tests**
   - Sensor readings displayed
   - Relay controls work
   - pH/EC dosing functional
   - Schedule updates apply
   - Modes switch correctly
   - E-STOP operates as expected

4. **UI Accessibility**
   - All tabs load without errors
   - Buttons responsive
   - Forms validate correctly
   - Error messages helpful

5. **Control Loop Testing**
   - pH auto-dosing maintains setpoint
   - EC auto-dosing maintains setpoint
   - Lights follow schedule
   - Chiller maintains temperature
   - Circulation interlock functions

6. **48-Hour Soak Test**
   - System runs unattended
   - No crashes or hangs
   - Logs reviewed for errors
   - Database grows appropriately

**Estimated Effort**: 2-3 hours setup + 48h monitoring  
**Status**: Not yet implemented

---

## Effort Summary

- ✅ **Phase 1-2**: 2 hours (COMPLETED)
- ✅ **Phase 3**: 8 hours total with bug fixes (COMPLETED)
- ⚠️ **Phase 4**: 3-4 hours (NOT STARTED)
- ✅ **Phase 5**: 12-16 hours (COMPLETED)
- ⚠️ **Phase 6**: 4-6 hours (NOT STARTED)
- ⚠️ **Phase 7**: 6-8 hours (NOT STARTED)
- ⚠️ **Phase 8**: 4-6 hours (NOT STARTED)
- ⚠️ **Phase 9**: 16-20 hours (NOT STARTED)
- ⚠️ **Phase 10**: 2-3 hours (NOT STARTED)
- ⚠️ **Phase 11**: 2-3 hours + 48h monitoring (NOT STARTED)

**Total Estimated**: 59-84 hours  
**Completed**: ~22 hours (Phases 1-3, 5)  
**Remaining**: 37-62 hours

---

## Notes

- **Grow Diary Feature**: This is a NEW proposal not part of the original Phase 6-8 plan. Research documented in `docs/GROW_DIARY_RESEARCH.md` but not yet scheduled for implementation. Could be considered for Phase 12+ or separate track.

- **Current Focus**: Phase 5 (Schedule Controller) is complete and deployed. Phase 4 (Lights Midnight Fix) is the next high-priority item.

- **Critical Path**: Phase 4 → Phase 6 → Phase 7 → Phase 8 → Phase 9 (documentation) → Phase 10-11 (release & testing)

---

*Last Updated: 2025-11-22*  
*Source: GitHub Issue #72 body and original prompt*
