# RDWC Operating Philosophy

**Document**: OP-001  
**System**: RDWC v4 Control Strategy  
**Date**: 2025-11-23  
**Revision**: As-Built v1.0  

---

## Purpose

This document describes the high-level control philosophy, safety hierarchy, and operating strategies for the RDWC-v4 system. It serves as the authoritative reference for understanding system behavior and decision-making logic.

---

## Control Strategy Overview

The RDWC system uses a **layered control architecture** with multiple independent controllers working in coordination:

### 1. Sensor Layer (Monitoring)
- **Continuous polling** (10-second intervals via background service)
- **Temperature compensation** (RTD feeds pH/EC with throttling: ΔT ≥ 0.2°C or ≥ 60s)
- **Staleness detection** (readings older than 120s trigger automation freeze)
- **Database archival** (all readings stored in SQLite for historical analysis)

### 2. Controller Layer (Autonomous Control)
Five independent controllers, each with auto/manual/maintenance modes:

| Controller | Purpose | Control Method | Setpoints |
|------------|---------|----------------|-----------|
| **pH** | Maintain pH 5.5-6.3 | Adaptive dosing (learned ml/pH ratio) | `targets.ph_low`, `targets.ph_high` |
| **EC** | Maintain EC 800-2000 µS | Recipe-based nutrient dosing | `targets.ec_low`, `targets.ec_high` |
| **Chiller** | Maintain temp 18-24°C | Hysteresis-based ON/OFF | `targets.temp_low`, `targets.temp_high` |
| **Lights** | 18/6 veg, 12/12 flower | Schedule-based (edge-only) | `lights_on_time`, `lights_duration_hours` |
| **Circulation** | Continuous flow | Interlock protection | Always ON (except E-STOP) |

### 3. Safety Layer (Interlocks & Guards)
- **E-STOP**: Ultimate override, all relays OFF
- **Circulation interlock**: Chiller system requires main pump running
- **Dosing guards**: Daily caps, press caps, staleness checks, EC baseline
- **Sensor validation**: Automation freezes if readings stale (>120s old)

### 4. Persistence Layer (State Management)
- **Relay states**: Saved to `~/.rdwc/relay_state.json`, restored on boot (safe relays only)
- **Settings**: Saved to SQLite `settings` table, loaded on startup
- **Modes**: Persisted per controller, survive restarts
- **Dose logs**: Full audit trail in SQLite (ph_dose_log, ec_dose_log, dose_events)

---

## Safety System Hierarchy

The safety system operates with strict priority levels:

```
┌─────────────────────────────────────────────────┐
│  LEVEL 1: E-STOP (Emergency Stop)               │ ← HIGHEST PRIORITY
│  - Software flag: estop_active = true           │
│  - ALL relays forced OFF immediately            │
│  - No automation, manual control blocked        │
│  - Requires manual reset via /api/relays/estop  │
└─────────────────────────────────────────────────┘
                      ↓ (if estop = false)
┌─────────────────────────────────────────────────┐
│  LEVEL 2: Interlocks                            │
│  - Circulation interlock: P-301 must run        │
│    before P-302/C-401 can start                 │
│  - Cannot be bypassed except by maintenance     │
│    mode (and even then, main pump must run)     │
└─────────────────────────────────────────────────┘
                      ↓ (if interlocks OK)
┌─────────────────────────────────────────────────┐
│  LEVEL 3: Mode Control                          │
│  - auto: Full automation enabled                │
│  - manual: User control only, automation OFF    │
│  - maintenance: User control + interlock bypass │
└─────────────────────────────────────────────────┘
                      ↓ (if mode = auto)
┌─────────────────────────────────────────────────┐
│  LEVEL 4: Dosing Guards                         │
│  - Sensor staleness: >120s old → block dosing   │
│  - Daily caps: 120s pH, 300s nutrients          │
│  - Press caps: 60s pH, 120s nutrients           │
│  - EC baseline: pH blocked if EC <500 µS        │
└─────────────────────────────────────────────────┘
                      ↓ (if all guards pass)
┌─────────────────────────────────────────────────┐
│  LEVEL 5: Automation Logic                      │ ← LOWEST PRIORITY
│  - pH auto-dosing (adaptive learning)           │
│  - EC auto-dosing (recipe-based)                │
│  - Chiller control (hysteresis)                 │
│  - Lights schedule (edge-only)                  │
└─────────────────────────────────────────────────┘
```

**Key Principle**: Higher levels always override lower levels. E-STOP overrides everything.

---

## Dosing Strategy

### pH Control (Adaptive Learning)
**Philosophy**: Learn from past doses to predict future needs, minimizing overshooting.

**Algorithm**:
1. **Check conditions**: mode=auto, pH < target_low, all guards pass
2. **Estimate dose**: Query learned ml/pH ratios from database (filtered by EC range ±15%)
3. **Calculate volume**: `ml = (target_pH - current_pH) * ml_per_pH * reservoir_liters`
4. **Apply safety cap**: `ml = min(ml, press_cap_ml, daily_remaining_ml)`
5. **Execute dose**: Turn on pH UP pump (PP-201) for calculated seconds
6. **Log event**: Record before/after pH, duration, volume to `ph_dose_log`
7. **Update learner**: After observing pH response, store actual ml/pH ratio

**Learning Filters**:
- Only learn from doses where pH actually changed (delta >0.05 pH)
- Filter by EC range (±15% of current EC) to account for buffer capacity
- Rolling window: use recent 50 doses per EC range
- Fallback: 10 mL/pH if no learned data (conservative default)

**Safety Guards**:
- `press_cap`: 60s max per press (prevents runaway single dose)
- `daily_cap`: 120s max per day (prevents excessive daily dosing)
- `ec_guard`: pH dosing blocked if EC <500 µS (insufficient buffer capacity)
- `stale_guard`: pH dosing blocked if sensor reading >120s old
- `estop_guard`: pH dosing blocked if E-STOP active

### EC Control (Recipe-Based)
**Philosophy**: Dose nutrients in fixed ratios according to grow stage recipe.

**Algorithm**:
1. **Check conditions**: mode=auto, EC < target_low, all guards pass
2. **Determine stage**: Read grow_stage and grow_day from settings
3. **Lookup recipe**: Get ml/L for micro/grow/bloom per stage
4. **Calculate volume**: `ml = ml_per_L * reservoir_liters`
5. **Apply safety cap**: `ml = min(ml, press_cap_ml, daily_remaining_ml)`
6. **Execute doses**: Turn on each pump sequentially (PP-202, PP-203, PP-204)
7. **Log events**: Record before/after EC, duration, volume per pump to `ec_dose_log`

**Recipes** (ml/L per stage):
- **Seedling** (days 1-7): Micro 1, Grow 0.5, Bloom 0
- **Vegetative** (days 8-35): Micro 1, Grow 2, Bloom 0.5
- **Early Flower** (days 36-56): Micro 1, Grow 1, Bloom 2
- **Mid Flower** (days 57-70): Micro 0.5, Grow 0.5, Bloom 3
- **Late Flower** (days 71-84): Micro 0.5, Grow 0, Bloom 2 (flush)

**Safety Guards**:
- `press_cap`: 120s max per press per pump
- `daily_cap`: 300s max per day per pump
- `stale_guard`: EC dosing blocked if sensor reading >120s old
- `estop_guard`: EC dosing blocked if E-STOP active

---

## Temperature Control Strategy

**Philosophy**: Hysteresis-based ON/OFF control to prevent rapid cycling, protect compressor.

**Control Logic**:
```
IF temp > (target_high + hysteresis):
    START chiller_pump (P-302) [if main_pump running]
    START water_chiller (C-401) [if main_pump running]
    
IF temp < target_low:
    STOP water_chiller (C-401)
    WAIT min_on_seconds (300s)
    STOP chiller_pump (P-302)
```

**Parameters**:
- `target_low`: 18°C (configurable)
- `target_high`: 24°C (configurable)
- `hysteresis`: 1°C (prevents oscillation at boundary)
- `min_on`: 300s (compressor protection, prevents short-cycling)
- `min_off`: 300s (compressor protection, cooldown before restart)

**Interlock Enforcement**:
- Chiller pump (P-302) CANNOT start unless main pump (P-301) is running
- Water chiller (C-401) CANNOT start unless main pump (P-301) is running
- If main pump stops, chiller system forced OFF immediately

**Rationale**: Prevents chiller operation without flow through main reservoir, which would damage chiller heat exchanger.

---

## Lights Schedule Strategy

**Philosophy**: Edge-only control for maximum simplicity and reliability.

**Control Logic**:
```
AT lights_on_time:
    SET grow_lights (L-501) = ON
    LOG event: lights_on
    
AT lights_off_time:
    SET grow_lights (L-501) = OFF
    LOG event: lights_off
```

**Key Features**:
- **No periodic catch-up**: Lights remain in last commanded state until next edge
- **Midnight crossover**: Correctly handles ON 20:00, OFF 08:00 (next day)
  - `is_within_window(now, on, off)` returns true if `now >= on OR now < off` when `on > off`
- **Protected relay**: Manual override requires whitelisted reason
- **Schedule update**: Recalculated daily from `lights_on_time` + `lights_duration_hours`

**Grow Stage Schedules**:
- **Vegetative**: 18/6 (18 hours on, 6 hours off)
- **Flowering**: 12/12 (12 hours on, 12 hours off)
- **Late Flower**: 10/14 (10 hours on, 14 hours off) - optional stress

**Rationale**: Edge-based control is deterministic, avoids "catch-up" loops that can cause unexpected state changes. Lights state is always predictable from schedule.

---

## Circulation Strategy

**Philosophy**: Main pump runs continuously (24/7) for nutrient circulation and oxygenation.

**Operating Principle**:
- Main pump (P-301) should always be ON except during:
  - E-STOP activation
  - Manual maintenance (mode=maintenance)
  - Intentional shutdown (user override)

**Interlock Role**:
- Main pump state gates chiller system operation
- Chiller pump (P-302) and water chiller (C-401) physically cannot start unless main pump running

**Fail-Safe**:
- On power loss or system crash, relays default to OFF (active-low design)
- On boot, main pump state can be restored from `relay_state.json` if saved
- User must manually restart if E-STOP was triggered

**Rationale**: Continuous circulation prevents stratification, ensures uniform pH/EC/temp, and delivers oxygen to roots.

---

## Alarm Management

### Priority Levels

**CRITICAL** (Immediate action required):
- E-STOP triggered
- Main pump fault (OFF unintentionally)
- Sensor offline >5 minutes
- Database corruption detected

**HIGH** (Action required within 1 hour):
- pH out of range (<5.0 or >7.0)
- EC out of range (<500 or >2500 µS/cm)
- Temperature out of range (<15°C or >28°C)
- Daily dose cap exceeded

**MEDIUM** (Investigate within 24 hours):
- Calibration stale (pH slope <95% or >105%)
- Dosing pump flow rate changed >10%
- Chiller runtime excessive (>12 hrs/day)
- Sensor reading variance high (instability)

**LOW** (Informational):
- Settings updated
- Mode changed
- Schedule updated
- Relay state changed

### Alarm Actions

| Alarm | Action | Auto-Recovery | Manual Reset Required |
|-------|--------|---------------|----------------------|
| E-STOP | All relays OFF, block automation | No | Yes (toggle E-STOP) |
| Main pump fault | Force chiller OFF (interlock) | No | Yes (restart main pump) |
| Sensor stale | Freeze automation, use last good value | Yes (fresh reading) | No |
| pH/EC out of range | Hold auto-dosing | Yes (return to range) | No |
| Daily cap | Block further dosing | Yes (midnight rollover) | No |

### Notification Channels
- **Telegram**: Configurable via `ALERT_ENABLE_TELEGRAM`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- **Email**: Configurable via `ALERT_ENABLE_EMAIL`, `SMTP_*` settings
- **Web UI**: Real-time status on all tabs, red badges for critical issues
- **Database Logs**: All events logged to `chiller_events`, `dose_events`, `frontend_logs` tables

---

## Mode Logic

Each controller operates in one of three modes:

### Auto Mode
- **Purpose**: Normal automated operation
- **Behavior**: Controller executes its control strategy autonomously
- **User Control**: Setpoints adjustable, but controller makes dosing/switching decisions
- **Safety**: All guards active (daily caps, press caps, staleness, interlocks)

### Manual Mode
- **Purpose**: User takes direct control, automation disabled
- **Behavior**: Controller does nothing unless user presses buttons
- **User Control**: Full control via web UI (dose, pump on/off, chiller on/off, lights on/off)
- **Safety**: Interlocks still enforced (circulation interlock), daily caps still active

### Maintenance Mode
- **Purpose**: System testing, troubleshooting, calibration
- **Behavior**: User control + relaxed some safety checks
- **User Control**: Full control via web UI or API
- **Safety**: Interlocks can be bypassed (e.g., run chiller pump without main pump for testing), but daily caps still enforced

**Mode Persistence**: Modes are saved to database, survive restarts. System always boots into last known mode per controller.

**Mode Independence**: Each controller has its own mode. Example:
- pH: auto (dosing automatically)
- EC: manual (user controls nutrient doses)
- Chiller: auto (temperature control active)
- Lights: auto (schedule running)
- Circulation: manual (user testing pump)

---

## Setpoint Management

### pH Targets
- **Default**: 5.8-6.2 pH
- **Range**: 5.5-6.3 pH (typical for most hydroponic crops)
- **Hysteresis**: 0.05 pH (prevents oscillation)
- **Adjustable via**: Web UI Settings tab or `/api/settings/import`

### EC Targets
- **Default**: 800-1600 µS/cm (varies by grow stage)
- **Seedling**: 400-800 µS/cm
- **Vegetative**: 800-1200 µS/cm
- **Flowering**: 1200-1800 µS/cm
- **Late Flower**: 600-1000 µS/cm (flush)
- **Adjustable via**: Web UI Settings tab or `/api/settings/import`

### Temperature Targets
- **Default**: 18-24°C
- **Optimal**: 20-22°C (most hydroponic crops)
- **Critical Low**: <15°C (slow growth, nutrient uptake impaired)
- **Critical High**: >28°C (dissolved oxygen drops, root disease risk)
- **Adjustable via**: Web UI Settings tab or `/api/settings/import`

### Lights Schedule
- **Default**: 18/6 (vegetative)
- **Flowering**: 12/12 (trigger flowering response)
- **Adjustable via**: Web UI Schedule tab or `/api/schedule`

---

## Data Management Philosophy

### Real-Time Data
- **Polling**: Frontend polls `/api/sensors` every 10 seconds
- **Caching**: API returns cached values (from background poller) to avoid I²C contention
- **Freshness**: Timestamp included, UI shows "stale" if >120s old

### Historical Data
- **Archival**: All sensor readings saved to `readings` table (timestamp, temp_c, ph, ec_mscm, online)
- **Retention**: Indefinite (manual vacuum/cleanup as needed)
- **Query**: `/api/sensors` (cached, with DB fallback) or query SQLite `readings` table directly for historical analysis
- **Dose Logs**: Permanent record in `ph_dose_log`, `ec_dose_log`, `dose_events` tables

### Settings Persistence
- **Storage**: SQLite `settings` table (key-value pairs, namespaced)
- **Backup**: Export via `/api/settings/export` (JSON)
- **Restore**: Import via `/api/settings/import` (JSON)
- **Validation**: Bounds-checked on import (reject invalid values)

### Database Maintenance
- **Vacuum**: Run `VACUUM` monthly to reclaim space
- **Analyze**: Run `ANALYZE` monthly to update query planner statistics
- **Backup**: Copy `data/rdwc.db` weekly (automated via cron or manual)
- **Corruption Recovery**: Restore from last known good backup

---

## Performance Philosophy

### Response Times
- **Sensor Polling**: 10s cycle (background service)
- **API Response**: <100ms (target), <500ms (acceptable)
- **Dosing Response**: <5s from dose command to pump activation
- **UI Update**: 10s polling interval (adjustable if needed)

### Resource Management
- **CPU**: <25% average utilization (Pi 4 is overpowered for this task)
- **Memory**: <500MB RSS (Python + FastAPI + SQLite)
- **Disk I/O**: Minimize writes (batch sensor readings, log rotation)
- **Network**: <1 Mbps (API traffic negligible)

### Scalability
- **Sensors**: I²C bus supports up to 128 devices (currently 3)
- **Relays**: 8 channels used, expandable to 16/32 via I²C relay boards
- **Database**: SQLite suitable for millions of rows (decades of sensor data)
- **API**: Single-user design (no authentication/rate-limiting needed)

---

## Operational Principles

### KISS (Keep It Simple, Stupid)
- Edge-only lights control (no periodic catch-up)
- Active-low relays (fail-safe on power loss)
- Single database file (no distributed systems)
- Polling model (no WebSockets/push complexity)

### Idempotency
- Relay commands are idempotent (setting ON when already ON is safe)
- Sensor reads are idempotent (reading same value twice is safe)
- Settings updates are idempotent (overwriting with same value is safe)

### Observability
- All state changes logged to database
- All dose events logged with before/after values
- All relay actions logged with reason and cooldown
- Frontend logs errors to database for debugging

### Fail-Safe Design
- Active-low relays (default to OFF on power loss)
- Circulation interlock (chiller can't run without flow)
- Daily dose caps (prevent runaway dosing)
- Sensor staleness checks (freeze automation if sensors fail)
- E-STOP (ultimate kill switch)

---

## Document Control

**Revision History**:
- v1.0 (2025-11-23): Initial operating philosophy documented from as-built codebase

**Approval**:
- [ ] User review and approval
- [ ] Validation against actual operational experience

---

**End of Operating Philosophy Document**
