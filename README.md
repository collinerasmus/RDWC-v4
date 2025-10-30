# RDWC v4.0.0 — simple & reliable

Single FastAPI service with one control loop for RDWC.
- Sensors: Atlas EZO on I²C (pH=0x63, EC=0x64, RTD=0x66)
- Relays (BCM): 5,6,13,19,26,16,20,21 per your wiring
- Target pH ~5.8–6.2; weekly res maintenance
See `.env.example` for configuration. Start minimal, expand in tiny phases.

> Version: `v4.0.0` — see CHANGELOG.md

## How it works

- One FastAPI app under systemd, using a Python venv.
- Central relay core enforces idempotency, active-low driving, cooldowns (MIN_ON/OFF), and anti-flap.
- Lights scheduling is edge-only: exactly two edges per day (ON at start, OFF after duration) with small guards; no periodic catch-up loops.
- Sensors use an RTD-first read and throttle temperature-compensation writes to pH/EC (ΔT ≥ 0.2°C or ≥ 60s).
- Chiller override has explicit modes (auto | force_on | force_off). AUTO does not thermostat in software; hardware thermostat remains in control.
- Alerts are OFF by default (opt-in via .env).

## Endpoints (overview)

- `/health` — readiness and service summary (DB/I2C/camera/relays/sensors heartbeat)
- `/relay/status` — states, reasons, timers per relay
- `/relay/set` — POST+GET manual control via relay core (respects cooldowns)
- `/sensors/read` — RTD/pH/EC with temp-comp throttle info
- `/settings` — GET/PUT system settings (lights schedule, volume) with immediate scheduler recompute
- `/chiller/override` — GET/PUT chiller mode (auto | force_on | force_off)
- `/debug/relay_requests` — recent relay requests ring buffer (for diagnostics)
- `/debug/lights_log` — lights event log (summary + recent events)

## Settings

The system supports configurable settings via the web dashboard or API:

### System Volume
- **Default**: 25.0 litres
- **Range**: 0.1+ litres  
- **Usage**: Used for nutrient dosing calculations

### Lights Schedule
- **Start Time**: Default 20:00 (configurable HH:MM format)
- **Duration**: Default 16 hours (range: 1-24 hours)
- **Behavior**:
  - Exactly two edges per day: ON at start time, OFF after duration
  - ±5s guards after each edge to re-assert intended state (idempotent)
  - Recomputes at startup, midnight, and after PUT /settings
  - No minute “catch-up” loop (prevents periodic dips)

### Configuration Methods

#### Web Dashboard
1. Navigate to http://192.168.88.49:8080
2. Find the "Settings" section
3. Adjust values as needed
4. Click "Save Settings"

#### API Endpoints
```bash
# Get current settings
curl http://192.168.88.49:8080/settings

# Update settings
curl -X PUT http://192.168.88.49:8080/settings \
  -H "Content-Type: application/json" \
  -d '{
    "system_volume_liters": 30.0,
    "lights_on_time": "20:00", 
    "lights_duration_hours": 18
  }'
```

#### Health & Debug Endpoints
```bash
# Health (readiness) summary
curl -s http://192.168.88.49:8080/health | jq .

# Relay status (per-relay state, reasons, timers)
curl -s http://192.168.88.49:8080/relay/status | jq .

# Last 50 relay toggle attempts (ts/name/on/via/result)
curl -s http://192.168.88.49:8080/debug/relay_requests | jq .
```

### Chiller Override

Explicit 3-mode control with no surprise thermostat behavior in software:

- Modes: `auto` | `force_on` | `force_off`
- In `auto`, the service does not thermostat the chiller; relays remain as they are until a user or schedule changes them. Hardware thermostats continue to operate.
- All changes go through the relay core (active-low, idempotent, MIN_ON/OFF, anti-flap). Cooldowns are respected.

API:
```bash
# Get current override
curl -s http://192.168.88.49:8080/chiller/override

# Force ON (both power and pump), subject to cooldowns
curl -s -X PUT -H "Content-Type: application/json" \
  -d '{"override":"force_on"}' http://192.168.88.49:8080/chiller/override

# Force OFF (both), subject to cooldowns
curl -s -X PUT -H "Content-Type: application/json" \
  -d '{"override":"force_off"}' http://192.168.88.49:8080/chiller/override

# Back to AUTO (no thermostat; holds current states)
curl -s -X PUT -H "Content-Type: application/json" \
  -d '{"override":"auto"}' http://192.168.88.49:8080/chiller/override

# Inspect relay states and cooldowns
curl -s http://192.168.88.49:8080/relay/status | jq '.chiller_power, .chiller_pump'
```

UI: A small card can present a 3-state selector and two live indicators for `chiller_power` and `chiller_pump`.

#### Alerts

Alerts (Telegram/Email) are OFF by default and only activate if configured via `.env`.
See `docs/alerts.md` for setup and testing instructions.

#### Database Migration
Settings are stored in SQLite. Run migration once:
```bash
sudo python3 /home/pi/RDWC-v4/scripts/migrate_settings.py
```

### Examples

**Evening Light Schedule** (avoids day heat):
- Start Time: `20:00` 
- Duration: `16` hours
- Result: Lights on 20:00 → 12:00 next day

**Large System Dosing**:
- System Volume: `50.0` litres
- Effect: Nutrient doses automatically scale to 2× standard amounts

**Seedling Schedule**:
- Start Time: `08:00`
- Duration: `14` hours  
- Result: Gentler 14-hour photoperiod for young plants