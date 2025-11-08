# RDWC‑v4 — Copilot instructions for coding agents

Purpose: make you productive fast on this Raspberry‑Pi FastAPI + hardware project. Agents execute commissioning, tests, and safe API calls autonomously; the human operator only observes UI/telemetry for confirmation. Keep edits small, safe, and verifiable with API calls and tests.

## Architecture you must know
- Single FastAPI app in `app/main.py`; feature modules in `app/` (pH/EC control, relays, settings, scheduler, dosing).
- Background sensor poller is separate: `app/sensor_poller.py` run via systemd. UI/API should NOT directly contend with it. Use cached endpoints or the diag/read_now paths that honor locks.
- GPIO is centralized in `app/relays_core.py` (the ONLY file that touches pins). All relay actions go through helpers: `set_lights`, `set_chiller_power`, `set_dosing_*`, etc. It enforces active‑low, idempotency, MIN_ON/OFF, anti‑flap, E‑STOP, and persistence.
- Settings live in SQLite via `app/settings.py` using namespaced keys (e.g., `targets.ph_high`). Thin legacy `/settings` views still exist for UI compatibility.
- pH/EC controllers: `app/ph_control.py`, `app/ec_control.py` provide manual and auto dosing, with DB‑backed dose logs and safety guards.
- Scheduler (`app/scheduler.py`) is edge‑only: two lights edges/day with small guards; no periodic catch‑up loops.
- EZO I²C access: stabilized helpers in `app/ezo_i2c_stabilized.py` and higher‑level `app/sensors_core.py`; contention is mitigated by locks and temperature‑comp throttling.

## Key endpoints used during commissioning (safe)
- Relays: `GET /api/relays/status`, `POST /api/relays/estop/toggle`, `POST /api/relays/mode`.
- Sensors: `GET /api/sensors` (cached/DB fallback), `GET /diag/sensors/once`, `POST /read_now`, `POST /fix_ezo`.
- pH Calibration: `GET /calib/ph/caps`, `GET /calib/ph/read`, `GET /calib/ph/read_stable`, `GET /calib/ph/status`, `POST /calib/ph/{mid|low|high}`, `POST /calib/ph/clear` (needs `CALIB_ENABLE=1`).
- EC Calibration: `POST /api/ec/cal/{clear|low|high}`, `POST /api/ec/k`, `GET /api/ec/cal/status`.
- Dosing pumps: `GET /calib/dose/pumps`, `POST /calib/dose/{prime|run|commit}`.
- Optional: `POST /api/sensors/power_cycle?off_ms=2000&post_wait_ms=4000&validate=1` to GPIO power‑cycle the sensor rail when `RDWC_SENSOR_POWER_PIN` is configured.

## Project‑specific conventions
- Active‑low relays (HIGH=OFF). Treat lights/chiller as protected; reasons must be whitelisted (`relays_core.WHITELIST_LIGHTS`).
- All relay mutations flow through `relays_core.set_relay` or specific wrappers; never write GPIO directly. Provide a reason and honor cooldowns unless `force=True` is explicitly warranted.
- Avoid I²C collisions. Calibration and one‑shot reads honor `/tmp/rdwc_calib.lock`; background poller runs continuously. Prefer `/api/sensors` for UI polling, and use `/calib/ph/*` or diag endpoints for locked operations.
- Temperature compensation to pH/EC is throttled (ΔT ≥ 0.2°C or ≥ 60s) — see `sensors_core.py`.
- Dose safety: centralized caps/guards in `app/dosing.py` and controller modules; logs are written to SQLite tables (`ph_dose_log`, `ec_dose_log`, `dose_events`).

## Common workflows (agent executes; user observes UI)
- Install (dev): Python 3.9+, `pip install -r requirements.txt`.
- Run API (dev): `uvicorn app.main:app --reload --host 0.0.0.0 --port 8080`.
- Sensor poller service: see `deploy/systemd/rdwc-sensors.*`; status via `GET /api/sensors/status` in `app/main.py`.
- Tests: run pytest files at repo root (e.g., `test_ec_dose.py`, `test_relay_system.py`, etc.). Some rely on GPIO mocks; run on non‑Pi is fine.
- Deployment: scripts in `deploy/` and PowerShell helpers (e.g., `deploy/deploy_controllers.ps1`, `deploy_pi.sh`). Systemd units in `systemd/` and `deploy/systemd/`.
 - Commissioning automation: `tools/commission.ps1` (agent may extend). User only checks web UI: Calibration tab (pH flags), EC tab (low accepted), Relays panel (cooldowns, estop), Sensors (fresh ts <60s).

## Patterns and examples
- Relay action:
  ```python
  from app.relays_core import set_lights, REASON_OVERRIDE
  res = set_lights(True, REASON_OVERRIDE)  # returns {changed,state,reason,cooldown_remaining}
  ```
- Safe sensor read (deadline aware):
  ```python
  from app.sensors_core import read_all_sensors
  payload = read_all_sensors()  # {temperature_c, ph, ec_mscm, online, ts, errors}
  ```
- Write settings (namespaced):
  ```python
  from app.settings import upsert_settings
  upsert_settings({"general.reservoir_liters": 100, "targets.ph_high": 6.2})
  ```

## Integration points
- Hardware I²C: `/dev/i2c-1` via Atlas EZO modules (RTD 0x66, pH 0x63, EC 0x64).
- GPIO via gpiozero; all access is encapsulated by `relays_core`.
- SQLite DB at `data/rdwc.db`: tables `readings`, `settings`, `dose_events`, `ph_dose_log`, `ec_dose_log`, `system_state`, etc.
- Camera (optional): Picamera2 endpoints in `app/main.py` (`/camera/*`).

## Guardrails for agents
- Don’t bypass `relays_core` or touch GPIO directly.
- Don’t add periodic “catch‑up” loops; the scheduler is edge‑only by design.
- Respect calibration lock `/tmp/rdwc_calib.lock` and poller PID lock `/run/rdwc_sensors.lock`.
- Prefer additive changes with tiny patches and verify via the provided endpoints.
 - Agent-driven commissioning: when user says “proceed” assume you run endpoint flows (or simulate via TestClient) and return JSON diffs + success criteria. Ask for physical intervention only when essential (e.g., moving probe to buffer).

## Acceptance criteria patterns to report (succinct JSON)
- pH: single + stabilized value; within targets.ph_low..targets.ph_high OR buffer ±0.05 when calibrating.
- EC calibration: status includes `low` (and `high` if two-point) after operations.
- Dosing: each pump ml/s > 0 after commit; safety blocks identified by code (press_cap, daily_cap, ph_guard, ec_guard, stale, estop).
- Relays: estop=false unless intentionally toggled; lights edges only at schedule times; cooldown reasons present when blocked.
- Sensors: `/api/sensors` online=true and `ts` age <60s; temp_comp throttling fields sensible.

## Agent escalation rules
1. Retry idempotent read/calibration once before proposing code change.
2. If persistent sensor failure: attempt `/api/sensors/power_cycle` (only if `sensor_power` relay exists) then retry.
3. Only patch code after two failing retries and include <20 line diff localized to failing function.
4. After patch, run relevant pytest(s) and (if feasible) a synthetic TestClient call sequence mirroring the user workflow.

## Minimal commissioning sequence (internal reference)
1. `/api/relays/status` (capture estop/mode + sensor_power presence).
2. `/api/sensors/status` & `/api/sensors` (freshness check).
3. `/fix_ezo` → verify addresses.
4. pH: `/calib/ph/read`, `/calib/ph/status`, `/calib/ph/read_stable`.
5. EC (if requested): clear → low (1413) → status.
6. Dosing calibration: `/calib/dose/run` + `/calib/dose/commit` → verify rate.
7. Settings update (reservoir liters) via `/api/settings/import`.
8. Final snapshot: summarize acceptance criteria.

If anything here is unclear or missing (e.g., exact deploy steps on your Pi variant), tell us and we’ll refine this doc quickly.