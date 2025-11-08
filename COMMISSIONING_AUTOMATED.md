# Automated Commissioning Status

**Date:** November 8, 2025  
**Status:** ✅ **READY FOR HARDWARE VALIDATION**

## Overview
Commissioning automation completed with cross-platform test coverage enabling agent-driven hardware validation workflows.

## Components Delivered

### 1. Agent Instructions (`.github/copilot-instructions.md`)
- Architecture overview: FastAPI app, sensor poller, relay control, dosing controllers
- Commissioning endpoint catalog with safety guards
- Acceptance criteria patterns (pH stability ±0.05, EC calibration flags, dosing rates >0, sensor freshness <60s)
- Agent escalation rules (retry → power cycle → minimal patch → test)
- Project conventions (active-low relays, centralized GPIO, edge-only scheduler, namespaced settings)

### 2. PowerShell Automation Script (`tools/commission.ps1`)
Sections A–F automated:
- **A:** Hardware revalidation (`/api/relays/status`, `/fix_ezo`)
- **B:** Sensor recovery (`/api/sensors/power_cycle` if configured)
- **C:** pH verification (`/calib/ph/read`, `/calib/ph/read_stable`, `/calib/ph/status`)
- **D:** EC calibration (`/api/ec/cal/clear`, `/api/ec/cal/low`, `/api/ec/cal/status`)
- **E:** Dosing pump calibration (`/calib/dose/pumps`, `/calib/dose/run`, `/calib/dose/commit`)
- **F:** Finalization (reservoir volume update, E-STOP check, sensor freshness validation)

Returns JSON summary matching acceptance criteria format.

### 3. Simulation Test Suite (`tests/test_commissioning_sim.py`)
- Cross-platform test using FastAPI TestClient
- Environment shims for Windows (GPIO, smbus2, fcntl) enable non-Pi execution
- Mimics commissioning endpoint flow: relay status → sensors → pH read → EC calibration → dosing → settings update
- Produces acceptance JSON snapshot: `{relays_mode, estop, sensor_online, ph_status, ec_status, pumps, settings_updated}`
- **Status:** ✅ **PASSING** (1 test, 0 failures, 9.5s runtime)

### 4. Code Quality Improvements
- Fixed datetime deprecation warnings in `sensors_api.py` (migrated `utcnow()` → `datetime.now(datetime.UTC)`)
- Remaining warnings: FastAPI `on_event` deprecation (low priority; future lifespan migration)

## Test Results

```
tests/test_commissioning_sim.py::test_commissioning_flow PASSED [100%]
1 passed, 4 warnings in 9.50s
```

### Warnings Remaining (Non-Blocking)
- FastAPI `on_event` decorators (startup/shutdown) deprecated → migrate to lifespan handlers when convenient
- No functional impact; purely forward-compatibility notices

## Hardware Readiness Checklist

### Prerequisites
- [ ] Raspberry Pi with I²C enabled (`/dev/i2c-1`)
- [ ] Atlas EZO sensors connected: RTD 0x66, pH 0x63, EC 0x64
- [ ] Relay board wired (active-low, pins per `config.py`)
- [ ] Dosing pumps connected to peristaltic pump relays
- [ ] Calibration solutions ready: pH 7.0, pH 4.0, EC 1413 µS/cm
- [ ] SQLite database initialized (`data/rdwc.db`)
- [ ] Sensor poller service deployed (`deploy/systemd/rdwc-sensors.*`)
- [ ] Environment variable `CALIB_ENABLE=1` for pH calibration endpoints

### Validation Workflow (Agent Executes, User Observes UI)
1. Start API: `uvicorn app.main:app --host 0.0.0.0 --port 8080`
2. Verify sensor poller running: `GET /api/sensors/status` → `{"running": true, "pid": ...}`
3. Execute `tools/commission.ps1` (PowerShell) or manual endpoint sequence via API
4. Monitor Web UI tabs:
   - **Calibration Tab:** pH status flags (mid_accepted, pH value stable)
   - **EC Tab:** Low point accepted after 1413 calibration
   - **Relays Panel:** E-STOP false, cooldown reasons present if blocked
   - **Sensors Panel:** Timestamp age <60s, online=true, values in expected ranges
5. Review JSON output from script or `/api/sensors` + `/calib/ph/status` + `/api/ec/cal/status`

### Acceptance Criteria (Automated JSON Summary)
```json
{
  "relays_mode": "auto",
  "estop": false,
  "sensor_online": true,
  "sensor_age_seconds": <60,
  "ph": {
    "value": 6.8–7.2 (buffer) or 5.8–6.2 (reservoir),
    "stable": true,
    "mid_accepted": true
  },
  "ec": {
    "low_accepted": true,
    "k_value": 1.0
  },
  "pumps": [
    {"name": "ph_down", "ml_per_sec": ">0"},
    {"name": "ph_up", "ml_per_sec": ">0"},
    {"name": "nutrient_a", "ml_per_sec": ">0"},
    {"name": "nutrient_b", "ml_per_sec": ">0"}
  ],
  "settings_updated": true,
  "reservoir_liters": 100
}
```

## Next Steps
1. **Hardware Commissioning:** Run `tools/commission.ps1` on Raspberry Pi with live sensors
2. **Manual Fallback:** Use endpoint sequence from `.github/copilot-instructions.md` if script needs adjustment
3. **UI Validation:** Confirm calibration flags, relay states, sensor freshness in web interface
4. **Dosing Test:** Execute manual dose via `/api/ph/dose` or `/api/ec/dose` → verify pump activation and log entry
5. **Production Monitoring:** Deploy systemd services, enable scheduler, observe 24h telemetry for stability

## Support Resources
- **Agent Instructions:** `.github/copilot-instructions.md` (architecture, endpoints, conventions)
- **Quick Reference:** `QUICK_REFERENCE.md` (endpoint index)
- **API Documentation:** FastAPI auto-docs at `/docs` when running
- **Deployment Scripts:** `deploy/` directory (Pi setup, systemd units, database migrations)

## Known Limitations
- pH calibration endpoints require Linux `fcntl` for lock file handling (Windows test uses shim)
- Sensor power cycling requires `RDWC_SENSOR_POWER_PIN` configured in environment
- EC high-point calibration (12,880 µS/cm) not included in automation (optional two-point setup)

## Maintenance Notes
- Update sensor poller config if I²C addresses change (see `app/config.py`)
- Calibration data persists in EZO modules; re-cal only when probe replaced or accuracy drifts
- Dosing pump rates stored in `settings` table; recalibrate if tubing/pump replaced
- Review `CHANGELOG.md` for recent feature additions or API changes

---
**Automated testing complete. Hardware commissioning ready to proceed.**
