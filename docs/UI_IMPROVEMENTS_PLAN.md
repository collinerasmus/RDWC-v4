# RDWC-v4 UI Improvements & System Refinement Plan

## Status: In Progress
**Created**: 2025-11-21  
**Last Updated**: 2025-11-21

This document outlines the comprehensive UI improvements and system refinements needed to bring RDWC-v4 to production-ready, "As-Built" status.

---

## Summary of Work Completed

### Phase 1: Mode Selection Cleanup ✅ COMPLETED
- ✅ Removed mode selection buttons from Overview tab
- ✅ Removed mode selection buttons from Sensors tab
- ✅ Removed mode selection buttons from Scheduler tab
- ✅ Mode selection buttons remain only in System tab (correct location)

### Phase 2: Sensors Tab Cleanup ✅ COMPLETED
- ✅ Removed duplicate "pH Pump Calibration" section from Sensors tab
- ✅ Removed duplicate "EC Pumps Calibration" section from Sensors tab

---

## Remaining High-Priority Work

### Phase 3: Circulation Tab Redesign ⚠️ REQUIRES BACKEND WORK

**Problem**: User requests better visual separation and critical safety interlock:
> "if the chiller is running the chiller pump must be running. if the chiller pump cannot run then the chiller must not run, but it is most important that the chiller must run so the chiller pump must be started if not running and the chiller must run."

**Required Changes**:
1. Enhanced visual layout with distinct sections for each pump
2. Backend safety interlock preventing chiller operation without pump
3. Auto-start chiller pump when chiller activates
4. UI indicators showing interlock status
5. Prevent chiller pump shutdown while chiller is active

**Implementation Notes**:
- Backend logic needed in `app/relays_core.py` or new `app/circulation_controller.py`
- Frontend updates in `app/static/js/circulation.js` and `app/static/index.html`
- Comprehensive testing required for safety-critical functionality

### Phase 4: Lights Controller Improvements ⚠️ REQUIRES BACKEND WORK

**Problem**: User reports lights schedule confusion with cycles spanning midnight:
> "the control got confused with the 'on' cycle spreading over the next day and the lights would go off at 00:00 instead of 12:00."

**Root Cause**: Window calculation doesn't properly handle midnight crossover (e.g., ON at 20:00, OFF at 08:00 next day)

**Required Fixes**:
- Fix backend scheduler window calculation logic
- Handle day-boundary transitions correctly
- Test various schedule configurations (same-day, midnight-crossing, long cycles)
- Add better UI feedback showing current cycle state

**Files to Modify**:
- `app/scheduler.py` or `app/settings.py` (window calculation)
- Unit tests for various schedule scenarios

### Phase 5: Scheduler Completion ⚠️ MAJOR FEATURE

**Goal**: Implement complete 12-week grow schedule with EHC guidelines for autoflower cannabis

**Scope**:
- Research and implement horticultural best practices
- Create database schema for grow schedules
- Seed default 12-week schedule (veg → bloom → flush)
- Weekly targets for pH, EC, temperature, light hours
- Unified timeline view
- User-editable schedule with validation
- Auto-application of weekly targets to controllers

**Implementation Size**: Large (multiple days of work)

### Phase 6: System Tab Transformation ⚠️ MEDIUM EFFORT

**Goal**: Replace subtab structure with comprehensive single-column system information display

**Sections to Add**:
1. Raspberry Pi info (CPU, RAM, disk, temperature, uptime)
2. Software info (version, build, Python, services)
3. Environment info (sensors, relays, devices)
4. Database info (size, record counts)
5. Network info (IP, hostname, interfaces)
6. Process info (running services, PIDs)

**Implementation**:
- New backend API endpoint: `/api/system/info`
- Frontend layout redesign
- Real-time updates every 10 seconds

---

## Lower Priority Items

### Phase 7: UI Theme Unification
- Audit and standardize color schemes across all tabs
- Unify button styles, card layouts, typography
- Consistent status indicators
- Polish hover/active states

### Phase 8: Backend Verification
- Run full test suite
- Add tests for new features
- Integration testing
- Performance testing

### Phase 9: As-Built Documentation 📝

**Critical Documents Needed**:
1. P&ID (Piping & Instrumentation Diagram)
2. Electrical schematics (GPIO, I²C, power)
3. IO List (all sensors, actuators, signals)
4. Signal List (control signals, interlocks, alarms)
5. Equipment List (specs, manufacturers, part numbers)
6. Operating Philosophy (control strategy, safety systems)
7. Operating Manual (startup, normal operation, shutdown, emergencies)
8. Maintenance Manual (calibration, PM schedule, troubleshooting)

### Phase 10: Version Control & Release
- Tag as "v1.0.0-as-built"
- Create comprehensive release notes
- Update CHANGELOG.md
- Document deployment and rollback procedures

### Phase 11: Deployment & Testing
- Test on clean Raspberry Pi installation
- Verify all services start correctly
- End-to-end functional tests
- UI accessibility validation
- Control loop testing

---

## Priority Ranking

1. **CRITICAL**: Circulation safety interlock (equipment protection)
2. **HIGH**: Lights schedule midnight fix (functional correctness)
3. **MEDIUM**: System tab information display (usability)
4. **MEDIUM**: Scheduler completion (feature completeness)
5. **LOW**: UI theme unification (polish)
6. **ONGOING**: As-Built documentation (professional readiness)

---

## Next Steps for Implementation

1. Address mode button and calibration duplicate cleanup (✅ DONE)
2. Implement circulation safety interlock (backend + frontend)
3. Fix lights scheduler midnight logic (backend)
4. Create system info API endpoint and UI
5. Begin scheduler implementation (incremental)
6. Start documentation creation
7. UI theme audit and standardization
8. Comprehensive testing
9. Deploy and validate on target hardware

---

## Estimated Effort

- ✅ **Phases 1-2**: 2 hours (COMPLETED)
- **Phase 3** (Circulation): 4-6 hours (backend safety logic + frontend + testing)
- **Phase 4** (Lights): 3-4 hours (scheduler fix + testing)
- **Phase 5** (Scheduler): 12-16 hours (full feature implementation)
- **Phase 6** (System Tab): 4-6 hours (API + UI)
- **Phase 7** (UI Theme): 6-8 hours (audit + standardization)
- **Phase 8** (Testing): 4-6 hours
- **Phase 9** (Documentation): 16-20 hours (technical drawings + manuals)
- **Phase 10-11** (Release & Deploy): 4-6 hours

**Total Estimated**: 55-75 hours remaining

---

## Technical Notes

### Circulation Safety Interlock Logic

```python
# Pseudo-code for interlock
def set_chiller(on: bool):
    if on:
        # Start pump first
        pump_result = set_chiller_pump(True, "AUTO")
        if not pump_result['success']:
            return {'error': 'Cannot start chiller without pump'}
    return set_relay('chiller', on, reason)

def set_chiller_pump(on: bool):
    if not on:
        # Check if chiller is running
        if get_relay_state('chiller')['is_on']:
            return {'error': 'Cannot stop pump while chiller is running', 'blocked': True}
    return set_relay('chiller_pump', on, reason)
```

### Lights Schedule Fix

```python
# Correct window calculation for midnight crossover
def calculate_light_window(on_time_str: str, duration_hours: int):
    on_dt = parse_time_today(on_time_str)
    off_dt = on_dt + timedelta(hours=duration_hours)
    crosses_midnight = (off_dt.date() > on_dt.date())
    
    now = datetime.now()
    if crosses_midnight:
        # Check if we're in today's or yesterday's cycle
        if now.time() >= on_dt.time():
            in_window = True  # After ON time today
        elif now.time() < off_dt.time():
            # Before OFF time - must be yesterday's cycle
            on_dt = on_dt - timedelta(days=1)
            off_dt = off_dt - timedelta(days=1)
            in_window = True
        else:
            in_window = False
    else:
        in_window = (on_dt <= now < off_dt)
    
    return {'on': on_dt, 'off': off_dt, 'in_window': in_window, 'crosses_midnight': crosses_midnight}
```

---

## Conclusion

This plan provides a comprehensive roadmap for completing the RDWC-v4 system refinement. The work has been organized by priority, with critical safety features (circulation interlock) at the top and polish items (UI theme) at the lower priority levels.

The project is now ready for continued implementation following this plan. Each phase can be tackled incrementally with proper testing and validation at each step.
