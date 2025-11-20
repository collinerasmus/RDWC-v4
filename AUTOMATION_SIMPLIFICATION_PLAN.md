# RDWC v4 - Full Automation Simplification Plan

## Vision
Create a reliable, always-on automated hydroponic system that follows schedules and targets without complex mode management. The system should "just work" with minimal user intervention.

## Core Principles
1. **Automation by default** - All controllers run continuously
2. **Single control point** - One "Hold Automation" button for maintenance
3. **Schedule-driven** - Lights, pH, EC follow database-backed schedules
4. **Always-on pumps** - Chiller and circulation run continuously when powered
5. **Database persistence** - All settings survive power failures/reboots

## Current Problems to Eliminate
- ❌ Multiple mode buttons across 7+ tabs causing confusion
- ❌ Mode synchronization issues and state desync
- ❌ Complex Auto/Manual/Maintenance logic (~150+ lines per controller)
- ❌ Chiller and circulation not defaulting to auto
- ❌ Overview page not correctly reporting controller statuses

## Proposed Architecture

### 1. Remove All Mode Buttons
**Files to modify:**
- `app/static/index.html` - Remove mode buttons from all controller tabs:
  - pH tab (lines ~1585-1587)
  - EC tab (lines ~1854-1856)
  - Chiller/Environment tab (lines ~1070-1072)
  - Lights tab (lines ~1180-1182)
  - Circulation tab (lines ~1241-1243)
  - Sensors tab (lines ~1305-1307)
  - Schedule tab (lines ~714-716)

**Files to simplify:**
- `app/static/js/ph.js` - Remove mode UI logic
- `app/static/js/ec.js` - Remove mode UI logic
- `app/static/js/chiller.js` - Remove mode UI logic
- `app/static/js/lights_v2.js` - Remove mode UI logic
- `app/static/js/circulation.js` - Remove mode UI logic
- `app/static/js/sensors.js` - Remove mode UI logic
- `app/static/js/schedule.js` - Remove mode UI logic

### 2. Backend: Always-On Automation
**Files to modify:**
- `app/controller_modes.py` - Remove or simplify to always return "auto"
- `app/system_mode.py` - Simplify or remove
- `app/ph_control.py` - Remove mode checks, always run automation
- `app/ec_control.py` - Remove mode checks, always run automation
- `app/chiller.py` - Always run control logic
- `app/sensors_mode.py` - Always enable sensor polling

### 3. Single "Hold Automation" Control
**Add to System Settings tab:**
```html
<div class="hold-automation-control">
  <button id="hold-automation-toggle" class="btn-primary">
    Hold Automation
  </button>
  <span id="hold-status">Automation Active</span>
</div>
```

**Backend implementation:**
- New endpoint: `/api/automation/hold` (POST to toggle)
- New setting: `automation.hold` (boolean in settings table)
- Controllers check this single flag before executing automation
- E-STOP remains separate and takes priority

### 4. Editable Schedule UI
**New Schedule Tab Features:**
```
┌─────────────────────────────────────────────────────┐
│ Grow Schedule Editor                                │
├─────────────────────────────────────────────────────┤
│ Day │ pH Min │ pH Max │ EC Min │ EC Max │ Light Hrs│
├─────┼────────┼────────┼────────┼────────┼──────────┤
│ 1-7 │  5.8   │  6.2   │  0.8   │  1.2   │    18    │
│ 8-14│  5.8   │  6.2   │  1.0   │  1.4   │    18    │
│ ...                                                  │
│ [Add Row] [Delete Row] [Load Default] [Save]        │
└─────────────────────────────────────────────────────┘
```

**Database schema:**
```sql
CREATE TABLE IF NOT EXISTS grow_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_start INTEGER NOT NULL,
    day_end INTEGER NOT NULL,
    ph_min REAL NOT NULL,
    ph_max REAL NOT NULL,
    ec_min_mscm REAL NOT NULL,
    ec_max_mscm REAL NOT NULL,
    light_hours REAL NOT NULL,
    notes TEXT
);
```

**Default schedule (based on best practices):**
- Weeks 1-2 (Seedling): pH 5.8-6.2, EC 0.8-1.2 mS/cm, 18h light
- Weeks 3-4 (Early Veg): pH 5.8-6.2, EC 1.0-1.4 mS/cm, 18h light
- Weeks 5-6 (Late Veg): pH 5.8-6.2, EC 1.2-1.6 mS/cm, 18h light
- Weeks 7-14 (Flower): pH 5.8-6.3, EC 1.4-1.8 mS/cm, 12h light
- Weeks 15-16 (Flush): pH 5.8-6.2, EC 0.4-0.8 mS/cm, 12h light

### 5. Always-On Pumps
**Chiller:**
- Remove all mode checks
- Run temperature control loop continuously
- Only stop when automation hold is active or E-STOP

**Circulation:**
- Main pump runs continuously (except during dosing or E-STOP)
- No mode control needed
- Hardware failsafe via relay guards

### 6. Overview Page Status Display
**Fix status reporting to show:**
- pH: Current value, target range, "Auto Running" or "On Hold"
- EC: Current value, target range, "Auto Running" or "On Hold"
- Chiller: Current temp, target temp, "Running" or "On Hold"
- Lights: "On" or "Off", schedule status
- Circulation: "Running" or "On Hold"
- Sensors: Online/Offline status
- Schedule: Current day, active parameters

**Remove:**
- All mode indicators (MANUAL, AUTO, MAINTENANCE badges)
- Mode-related health checks

## Implementation Checklist

### Phase 1: Backend Cleanup
- [ ] Remove mode checks from ph_control.py automation loop
- [ ] Remove mode checks from ec_control.py automation loop
- [ ] Simplify chiller.py to always-on control
- [ ] Remove controller_modes.py or stub it
- [ ] Add automation.hold setting support
- [ ] Create /api/automation/hold endpoint

### Phase 2: Frontend Cleanup
- [ ] Remove all mode buttons from HTML tabs
- [ ] Remove mode UI logic from ph.js
- [ ] Remove mode UI logic from ec.js
- [ ] Remove mode UI logic from chiller.js
- [ ] Remove mode UI logic from lights_v2.js
- [ ] Remove mode UI logic from circulation.js
- [ ] Remove mode UI logic from sensors.js
- [ ] Remove mode UI logic from schedule.js

### Phase 3: Hold Automation Feature
- [ ] Add Hold Automation button to System Settings
- [ ] Wire up toggle handler in JavaScript
- [ ] Update Overview to show hold status
- [ ] Test: Hold → manual relay control works
- [ ] Test: Release → automation resumes

### Phase 4: Schedule UI
- [ ] Create grow_schedule database table
- [ ] Add default schedule data
- [ ] Build editable table UI in schedule.js
- [ ] Implement save/load endpoints
- [ ] Controllers read schedule based on grow day
- [ ] Test: Schedule persists across reboots

### Phase 5: Overview Status Display
- [ ] Update overview.js to remove mode badges
- [ ] Add "Auto Running" / "On Hold" indicators
- [ ] Show current values vs targets clearly
- [ ] Test: Status updates in real-time

### Phase 6: Testing & Deployment
- [ ] Test full automation flow on Pi
- [ ] Test hold automation → manual control
- [ ] Test schedule modifications persist
- [ ] Test power cycle recovery
- [ ] Verify no mode-related errors in logs
- [ ] Document new simplified workflow

## Files That Will Be Modified

### Backend (Python)
1. `app/ph_control.py` - Remove mode checks
2. `app/ec_control.py` - Remove mode checks
3. `app/chiller.py` - Remove mode checks
4. `app/sensors_mode.py` - Always enable
5. `app/controller_modes.py` - Remove or stub
6. `app/system_mode.py` - Add automation.hold support
7. `app/main.py` - Add /api/automation/hold endpoint, schedule CRUD
8. `app/settings.py` - Ensure automation.hold setting

### Frontend (JavaScript)
1. `app/static/js/ph.js` - Remove mode UI (~50 lines)
2. `app/static/js/ec.js` - Remove mode UI (~50 lines)
3. `app/static/js/chiller.js` - Remove mode UI (~30 lines)
4. `app/static/js/lights_v2.js` - Remove mode UI (~30 lines)
5. `app/static/js/circulation.js` - Remove mode UI (~30 lines)
6. `app/static/js/sensors.js` - Remove mode UI (~30 lines)
7. `app/static/js/schedule.js` - Add schedule editor UI (~200 lines)
8. `app/static/js/overview.js` - Update status display (~100 lines)
9. `app/static/js/system.js` - Add hold automation toggle (~50 lines)

### Frontend (HTML)
1. `app/static/index.html` - Remove mode buttons, add hold button, schedule table

### Database
1. `app/database.py` or migration script - Create grow_schedule table

## Expected Outcomes

### What Users Will See
1. **Overview Tab**: Clean status display, no mode buttons
2. **Individual Tabs**: Configuration only, no mode controls
3. **System Settings**: Single "Hold Automation" button
4. **Schedule Tab**: Editable grow schedule table

### What Will Always Run
- Sensor polling (continuous)
- pH dosing automation (when needed)
- EC dosing automation (when needed)
- Chiller control loop (continuous)
- Circulation pump (continuous)
- Lights following schedule

### What Can Be Controlled
- Hold Automation button → Pause all automation
- Manual relay switches → Direct GPIO control
- E-STOP → Emergency shutdown
- Schedule parameters → Edit targets/times

## Success Criteria
1. ✅ No mode buttons visible anywhere in UI
2. ✅ All automation runs by default on system startup
3. ✅ Hold Automation stops all automated actions
4. ✅ Schedule edits persist in database
5. ✅ Chiller and circulation run continuously
6. ✅ Overview shows clear "Running" / "On Hold" status
7. ✅ System recovers properly after power cycle
8. ✅ No mode-related errors in console or logs

## Estimated Effort
- Backend changes: 10-12 files, ~500 lines removed, ~200 added
- Frontend changes: 10 files, ~300 lines removed, ~400 added
- Testing: 2-3 hours on Pi
- Total: 1 focused session of 4-6 hours

## Next Steps for New Session
1. Start fresh session with this plan as context
2. Implement Phase 1 (Backend Cleanup) first
3. Test each phase on Pi before moving to next
4. Use feature flags if needed for gradual rollout
5. Document any deviations from plan
6. Create deployment guide for Pi

## Important Notes
- Keep E-STOP completely separate (hardware safety)
- Maintain relay guards and cooldowns
- Don't break calibration workflows
- Preserve dose logging
- Keep manual relay panel functional
- Back up database before major changes

---
**Document Version:** 1.0  
**Created:** 2025-11-20  
**For Session:** RDWC v4 Full Automation Simplification  
**Author:** GitHub Copilot  
