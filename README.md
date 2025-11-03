# RDWC v4.0.0 — simple & reliable

Automated RDWC (Recirculating Deep Water Culture) hydroponic controller with pH/EC dosing, temperature control, and grow cycle management.

**Hardware**: Raspberry Pi 4 + Atlas Scientific EZO sensors + Peristaltic pumps + Active-low relays  
**Software**: FastAPI + SQLite + Python 3.9+  
**Safety-First**: Active-low relays (HIGH=OFF), safe-off on boot, guard rails, alerts

## Quick Start

1. **Hardware Setup**: Connect sensors and relays per hardware map below
2. **Install**: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
3. **Configure**: Copy `.env.example` to `.env`, set Pi IP, sensor addresses
4. **Deploy**: `./deploy_pi.sh` (from dev machine) or `systemctl start rdwc.service` (on Pi)
5. **Access**: http://192.168.88.49:8080

## Hardware Map

### I²C Sensors (Atlas Scientific EZO)
- **pH**: 0x63 (EZO-pH circuit)
- **EC**: 0x64 (EZO-EC circuit)
- **RTD**: 0x66 (PT-1000 temperature probe)

### Relays (BCM GPIO, Active-Low: HIGH=OFF)
- **pH Up Pump**: BCM 5
- **Grow Pump**: BCM 6
- **Micro Pump**: BCM 13
- **Bloom Pump**: BCM 19
- **Main Circulation**: BCM 26
- **Chiller Pump**: BCM 16
- **Chiller**: BCM 20
- **Grow Lights**: BCM 21

### Power & Safety
- All relays default HIGH (OFF) at boot
- E-STOP via `safety.estop` setting
- Watchdog timer monitors sensor loop

## Dashboard Tabs

Web UI organized by function (http://192.168.88.49:8080):

1. **Overview**: System at-a-glance, health indicators, grow day counter
2. **pH Control**: Manual dosing, automation, dose history, settings
3. **EC Control**: G/M/B nutrient dosing, mix ratios, auto-raise, CSV export
4. **Temperature**: Chiller control, min ON/OFF protections
5. **Lights**: Schedule (start time, duration), manual override
6. **Sensors**: Live readings, export, calibration status
7. **Trends**: Multi-day charts (pH, EC, temp) with date pickers
8. **Relays**: Manual relay control, state viewer, cooldown timers
9. **Settings**: General (reservoir size, grow start), Alerts (email/Telegram), Calibration

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

### Camera

Live MJPEG streaming using **Picamera2** (Raspberry Pi native camera stack, Bookworm compatible).

#### Requirements
- Raspberry Pi camera module (v1, v2, v3, or HQ)
- Camera interface enabled via `raspi-config`
- System packages:
  ```bash
  sudo apt update
  sudo apt install -y python3-picamera2 libcamera-apps
  ```
- User in `video` group: `sudo usermod -aG video pi` (reboot after)

#### Endpoints
- `GET /camera/status` — Returns camera availability and mode
  ```json
  {
    "available": true,
    "mode": "picamera2",
    "note": "Camera ready"
  }
  ```
- `GET /camera/stream` — MJPEG stream at ~5 fps, 640×480, JPEG quality 70
  - Returns `404` with JSON error if camera unavailable
  - Media type: `multipart/x-mixed-replace; boundary=frame`

#### Configuration
Optional environment variables:
- `CAM_FPS` — Frame rate (default: 5)
- `CAM_QUALITY` — JPEG quality 1-100 (default: 70)
- `LIBCAMERA_LOG_LEVELS` — Set to `*:2` to reduce log noise

#### Troubleshooting
```bash
# Test camera detection
libcamera-hello -n -t 2000

# Check user permissions
groups pi  # should include 'video'

# View service logs for camera errors
sudo journalctl -u rdwc.service -n 50 --no-pager | grep -i camera
```

#### Notes
- No OpenCV dependency — uses PIL for JPEG encoding (lighter CPU usage)
- Graceful fallback: if Picamera2 unavailable, endpoints return safe error responses
- Camera automatically initialized on first stream request
- Clean shutdown on service stop

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