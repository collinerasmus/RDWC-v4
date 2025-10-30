# Changelog

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
