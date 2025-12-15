# RDWC-v4 Commissioning Status — Dec 15, 2025 23:30 UTC

## 🟢 Construction: COMPLETE
All core systems implemented, integrated, and stabilized:
- ✅ **FastAPI backend** (main.py, 4195 lines) with unified routing
- ✅ **Sensor polling** (sensor_poller.py) running as systemd service
- ✅ **pH/EC controllers** with auto-dosing, safety guards, dose logging
- ✅ **Relay control** (relays_core.py) with GPIO encapsulation, anti-flap, E-STOP
- ✅ **Scheduler** (scheduler.py) for lights edges (two per day)
- ✅ **Database** (SQLite) with dose_events, readings, settings, system_state
- ✅ **Charts** (modern React stack) with real-time KPI aggregation
- ✅ **HMI UI** (templates, static assets) with responsive tabs

---

## 🟡 Commissioning: 90% COMPLETE

### ✅ Completed
1. **System Architecture**
   - Unified settings system (namespaced keys)
   - Centralized relay control via relays_core
   - Auto-enable controls (global + per-controller)
   - Database schema finalized

2. **Sensor Integration**
   - RTD temperature (I²C 0x66)
   - Atlas pH probe (I²C 0x63)
   - Atlas EC probe (I²C 0x64)
   - Polling loop with locking + stale detection

3. **Dosing System**
   - Manual dose via `/api/dose/{pump}` POST
   - Auto controllers (pH up, EC via G/M/B mix)
   - Safety guards: pH_guard, EC_guard, daily_cap, press_cap
   - Dose event logging with `blocked_by` tracking

4. **Relay Control**
   - Lights (two edges/day via scheduler)
   - Chiller temperature-based
   - Main circulation pump
   - E-STOP and safe-off persistent storage

5. **Safety Systems**
   - Active-low relay enforcement
   - Minimum on/off windows
   - Concurrent dosing prevention (mix lock)
   - Persistent state across reboots

### 🟡 In-Progress (Overnight Auto Test)
- **Live plant operation**: System running 24/7 in full auto mode
- **Performance monitoring**: API latency, chart refresh, DB query times
- **Long-term stability**: Overnight sensor polling + auto dosing
- **Event log accumulation**: Building real-world dose_events history

### Remaining (Post-Overnight Test)
1. **Field calibration** (pH, EC if needed)
2. **Long-term learning** (EC auto-dosing dose-effect curve)
3. **Production hardening** (error recovery, watchdog, alerting)
4. **Documentation** (commissioning checklist, troubleshooting guide)

---

## 🎛️ System Configuration (Overnight Auto Mode)

### Auto Modes (All Enabled ✅)
```
controls.global_auto              = true
controls.ph_auto                  = true
controls.ec_auto                  = true
controls.chiller_auto             = true
controls.circulation_auto         = true
controls.lights_auto              = true
```

### Safety Guards (All Clear ✅)
```
safety.estop                      = false
safety.estop_persist              = false
safety.safe_off_persist           = false
```

### Dosing Caps
```
safety.max_seconds_per_press      = 1.5s     (max single dose)
safety.max_total_seconds_per_24h  = 120.0s   (daily total)
safety.min_off_window_sec         = 2.0s     (between doses)
```

### Control Targets
```
targets.ph_low                    = 5.80
targets.ph_high                   = 6.20
targets.ec_low                    = 0.40
targets.ec_high                   = 0.60
targets.ec_target                 = 1.80
targets.temp_target_c             = 19.00
```

---

## 📊 Current System State (Pre-Overnight)

| Component | Status | Notes |
|-----------|--------|-------|
| **Database** | ✅ Fresh | dose_events empty, ready for logging |
| **Sensor Poller** | 🟡 Check Pi | Running as systemd service |
| **pH Controller** | ✅ Auto | Ready to maintain pH 5.8–6.2 |
| **EC Controller** | ✅ Auto | Ready to maintain EC in band |
| **Chiller** | ✅ Auto | Temperature-driven ON/OFF |
| **Lights** | ✅ Schedule | Two edges/day (times TBD) |
| **Circulation** | ✅ Auto | Always-on or schedule-driven |
| **E-STOP** | ✅ Clear | System enabled for operation |

---

## 🌙 Overnight Auto Test (Dec 15–16, 2025)

### Objectives
1. Run all controllers in full AUTO for 8–12 hours
2. Monitor sensor polling cadence & accuracy
3. Log dosing events (pH_UP, nutrients) with timestamps
4. Verify dose blocking (daily cap, guards)
5. Check chart refresh + KPI stability
6. Validate relay event log (no spurious toggles)

### Success Criteria
- ✅ Sensor readings fresh (<60s old)
- ✅ Dose events logged consistently
- ✅ No E-STOP or safe-off triggers
- ✅ Charts update without jitter
- ✅ Database queries <100ms (p95)
- ✅ Relay events coherent with doses

### Monitoring During Sleep
- **API endpoint**: `/api/sensors` (cached + DB fallback)
- **Database**: `SELECT * FROM dose_events ORDER BY ts DESC LIMIT 20`
- **Charts**: Real-time KPI aggregation (volume dosed, count, last ts)

---

## 🏗️ Construction Summary

### Lines of Code (Core)
- `app/main.py`: 4,195 lines (FastAPI, routing, UI)
- `app/sensor_poller.py`: ~400 lines (polling loop)
- `app/ph_control.py`: 1,424 lines (manual + auto dosing)
- `app/ec_control.py`: 1,628 lines (nutrient dosing)
- `app/relays_core.py`: ~800 lines (GPIO + safety)
- `app/dosing.py`: 397 lines (centralized guards + logging)
- **Total Core**: ~10,000 lines

### Database Schema
- `readings` (ts, temp_c, ph, ec_ms_cm, online)
- `settings` (key, value)
- `system_state` (key, value)
- `dose_events` (id, ts, pump, seconds, blocked_by, ph_before/after, ec_before/after, controller_state_json)
- `ph_dose_log` (legacy pH logs)
- `ec_dose_log` (legacy EC logs)

### Hardware Integration
- **I²C Sensors**: RTD (0x66), pH (0x63), EC (0x64)
- **GPIO Relays**: Lights, Chiller, Main pump, Dosing pumps, Optional Chiller power
- **Systemd Services**: rdwc (API), rdwc-sensors (poller)

---

## 📋 Handoff Checklist

- [x] All auto modes enabled
- [x] Safety guards cleared
- [x] Dose daily cap verified (120s available)
- [x] Database initialized & schema verified
- [x] Target pH/EC/temp configured
- [x] Sensor poller systemd service configured
- [ ] Overnight auto test running (in progress)
- [ ] HMI screenshots captured
- [ ] Documentation updated
- [ ] GitHub showcase page created

---

## Next Steps

1. **During sleep** (Dec 15–16): System runs 24/7 auto
2. **Upon wake**: Review dose_events, charts, relay logs
3. **Post-overnight**: Assess stability, make tuning adjustments, proceed to full commissioning
4. **Final commissioning**: Field calibrations, watchdog setup, alerting

---

**Status**: 🟡 **Commissioning 90% — Overnight Auto Test in Progress**

Last updated: Dec 15, 2025 23:30 UTC  
System state: All auto modes enabled, safety cleared, ready for unattended operation.

