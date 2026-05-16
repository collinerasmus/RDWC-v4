# Ops Runbook — RDWC v4 (one page)

## Service control

- Restart: `sudo systemctl restart rdwc.service`
- Status:  `sudo systemctl status rdwc.service --no-pager`

## Quick smoke (30s)

- `python tools/commissioning_readiness.py --compact`

## Key endpoints

- `/health` — readiness (DB/I2C/camera/relays/sensors heartbeat)
- `/relay/status` — per-relay state, last reason, timers
- `/relay/set` — POST+GET manual control (respects cooldowns)
- `/sensors/read` — RTD/pH/EC + temp-comp throttle info
- `/settings` — GET/PUT settings (lights schedule, volume)
- `/chiller/override` — GET/PUT `auto|force_on|force_off`
- `/debug/relay_requests` — recent relay requests
- `/debug/lights_log` — lights events list + summary

## Lights — Edge-only schedule

- Exactly two edges per day (ON at start time, OFF after duration)
- Small guard after each edge to re-assert (idempotent)
- No minute catch-up loop (prevents periodic dips)
- Change via `PUT /settings`

## Chiller — Override modes

- Modes: `auto | force_on | force_off`
- AUTO does not thermostat in software; relays remain until changed by user/schedule. Hardware thermostat continues to operate.

## Sensors — Behavior

- RTD-first read; temp compensation sent to pH/EC only if ΔT ≥ 0.2°C or ≥ 60s have elapsed
- Errors are surfaced via `/sensors/read.errors[]` and UI red-dot indicator

## Cooldowns and protection

- Active-low GPIO board
- MIN_ON / MIN_OFF (seconds):
  - `chiller_power`: 300 / 300
  - `chiller_pump`: 120 / 5
  - `lights`: 10 / 5
  - `main_pump`: 5 / 5
- Anti-flap: back-off when too many changes in a window

## BCM pin mapping

```
lights:        21
chiller_pump:  16
chiller_power: 20
main_pump:     26
dosing_grow:    6
dosing_micro:  13
dosing_bloom:  19
dosing_ph_up:   5
```

## Common fixes

- Button didn’t change relay: check `/debug/relay_requests` for `reason` and `cooldown_remaining` (may be cooldown/antiflap)
- Sensors stale: `i2cdetect -y 1` should show `0x63, 0x64, 0x66`
- Service flapping: `journalctl -u rdwc.service -n 100 --no-pager`

## Alerts

- OFF by default (Telegram/Email require `.env`)
- See `docs/alerts.md` when enabling
