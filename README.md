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

## Headless Sensor Poller (24/7 Logging)

**Design Philosophy**: Sensors log continuously whether or not a browser is open.

### Architecture
- **Standalone Module**: `app/sensor_poller.py` — runs independently with PID lock
- **Systemd Service**: `rdwc-sensors.service` — headless background polling
- **Watchdog Timer**: Monitors heartbeat, auto-restarts if stale (>30s)
- **Poll Interval**: 5 seconds (configurable via `RDWC_SENSOR_POLL_INTERVAL`)
- **Database**: Direct writes to `readings` table (same as UI Trends)
- **Safety**: No relay operations, read-only I2C access

### Single-Instance Guard
- **PID Lock**: `/run/rdwc_sensors.lock` (fallback: `/tmp/rdwc_sensors.lock`)
- **Behavior**: Only one poller can run at a time; prevents I2C bus conflicts
- **Heartbeat**: Updates `sensor_poller_heartbeat_ts` in `system_state` table every cycle

### API Endpoints
```bash
# Get poller status
curl -s http://192.168.88.49:8000/api/sensors/status | jq .
# Returns: running, last_sample_ts, last_heartbeat_ts, interval_sec, lock_pid, poll_count

# Comprehensive health check
curl -s http://192.168.88.49:8000/api/health | jq .
# Returns: ok, app_version, git_commit, uptime_seconds, sensor_poller, database
```

### Deployment
```bash
# Deploy to Pi (from dev machine)
cd c:\Users\USER-PC\OneDrive\Documents\GitHub\RDWC-v4
.\deploy\deploy_sensor_poller.ps1

# Manual deployment
ssh pi@192.168.88.49
cd /home/pi/RDWC-v4
sudo cp deploy/systemd/rdwc-sensors* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rdwc-sensors.service
sudo systemctl enable --now rdwc-sensors-watchdog.timer
```

### Verify Headless Operation
```bash
# 1. Check service status
systemctl status rdwc-sensors.service --no-pager

# 2. View logs
journalctl -u rdwc-sensors.service -n 50 --no-pager

# 3. Verify poller is running
curl -s http://192.168.88.49:8000/api/sensors/status | jq '.running, .poll_count'

# 4. Confirm data is being written
sqlite3 /home/pi/RDWC-v4/data/rdwc.db \
  "SELECT datetime(ts, 'unixepoch', 'localtime'), temp_c, ph, ec_ms_cm 
   FROM readings ORDER BY ts DESC LIMIT 10"
```

### Cleanup Legacy Pollers
```bash
# Audit and remove ghost/duplicate readers
ssh pi@192.168.88.49
cd /home/pi/RDWC-v4
bash deploy/audit_sensor_readers.sh        # Dry-run (shows issues)
bash deploy/audit_sensor_readers.sh --kill # Cleanup mode (kills strays)

# Check for legacy systemd units
systemctl list-units --all | grep -Ei 'rdwc|hydro|sensor|atlas|ezo'

# Check for legacy cron jobs
crontab -l | grep -Ei 'sensor|rdwc'

# Verify only one process owns I2C bus
sudo lsof /dev/i2c-1
```

### UI Indicator
The **Overview** tab shows a live sensor poller status badge:
- **🟢 Online**: Last sample <30s ago
- **🔴 Offline**: No samples or stale heartbeat
- **Tooltip**: Shows last sample age, poll count

### Troubleshooting
```bash
# Poller not running?
sudo systemctl restart rdwc-sensors.service

# Stale lock file?
sudo rm /run/rdwc_sensors.lock
sudo systemctl restart rdwc-sensors.service

# I2C bus conflicts?
sudo lsof /dev/i2c-1  # Should show only rdwc-sensors.service process

# View watchdog timer status
systemctl list-timers rdwc-sensors-watchdog.timer --no-pager
```

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