# RDWC-v4 Status At A Glance

## Current Snapshot

- State: Production operation
- Backend: FastAPI in app/main.py
- Sensor Poller: rdwc-sensors.service (headless, systemd)
- Runtime DB: data/rdwc.db
- UI: Server-rendered dashboard (non-React)
- Tabs: Overview, Camera, pH, EC, Temperature, Circulation, Lights, Schedule, Settings
- Pi Host: 192.168.88.55:8080
- Last Verified Commit: 9c62ae1

## Controllers

- pH control: enabled with guard rails
- EC control: enabled with guard rails
- Temperature/chiller control: enabled with hysteresis and compressor protection
- Lights scheduler: edge-only transitions
- Circulation control: interlock-aware

## Safety Model

- E-STOP available globally
- Active-low relays (HIGH=OFF)
- Cooldown and anti-flap protections
- Dosing guard rails (interval, caps, stale-read protection)
- Sensor freshness checks gate automation decisions

## Scheduler Truth Model

The scheduler is the source of truth for week-based targets.

- Week/day rollover is anchored to lights_on_time.
- Rollover does not depend on uninterrupted runtime.
- If power is down during the benchmark, week advances on next startup once local time is past the benchmark.

Runtime diagnostics are exposed via:

- GET /api/schedule/current_week

Important fields:

- week
- ec_target
- lights_on_time
- now_local
- next_rollover_local
- benchmark_passed_today

## Operational Verification

Use these checks when validating live behavior:

```bash
curl http://192.168.88.55:8080/api/schedule/current_week
curl http://192.168.88.55:8080/api/nutrient_schedule
curl http://192.168.88.55:8080/api/ec/status
curl http://192.168.88.55:8080/api/auto/status
```

Expected consistency:

- current_week in schedule endpoints matches controller target selection
- ec_target for current week matches EC status target band midpoint
- benchmark_passed_today flips to true after lights_on_time

## Notes

- Commissioning orchestration script tools/commission_all.py is not present; run individual commissioning scripts.
- Use deploy/refresh_api.ps1 and deploy/refresh_poller.ps1 for service refresh workflows.
- For canonical architecture and workflow details, see README.md and SYSTEM_ARCHITECTURE.md.
