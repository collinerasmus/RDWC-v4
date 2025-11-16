# RDWC v4.0.0 — simple & reliable

Automated RDWC (Recirculating Deep Water Culture) hydroponic controller with pH/EC dosing, temperature control, and grow cycle management.

**Hardware**: Raspberry Pi 4 + Atlas Scientific EZO sensors + Peristaltic pumps + Active-low relays  
**Software**: FastAPI + SQLite + Python 3.9+  
**Safety-First**: Active-low relays (HIGH=OFF), safe-off on boot, guard rails, alerts

## Quick Start

1. **Hardware Setup**: Connect sensors and relays per hardware map below
2. **Install**: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
  - Dev tools (optional): `pip install -r requirements-dev.txt`
3. **Configure**: Copy `.env.example` to `.env`, set Pi IP, sensor addresses
4. **Deploy**: `./deploy_pi.sh` (from dev machine) or `sudo systemctl start rdwc.service` (on Pi)
5. **Access**: http://192.168.88.49:8080
6. **Important**: After deployment, clear browser cache (Ctrl+Shift+R) to load new assets

## Development Workflow

### Environment Setup

**1. Clone the Repository**
```bash
git clone https://github.com/collinerasmus/RDWC-v4.git
cd RDWC-v4
```

**2. Create Virtual Environment**

*Linux/macOS/Raspberry Pi:*
```bash
python3 -m venv .venv
source .venv/bin/activate
```

*Windows (PowerShell):*
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**3. Install Dependencies**

*Runtime dependencies:*
```bash
pip install -r requirements.txt
```

*Development tools (testing, coverage):*
```bash
pip install -r requirements-dev.txt
```

**Key Dependencies:**
- `fastapi` - Web framework
- `uvicorn[standard]` - ASGI server
- `smbus2` - I²C communication with Atlas EZO sensors
- `gpiozero` - GPIO control for relays
- `httpx==0.23.3` - HTTP client (pinned for Starlette TestClient compatibility)
- `pytest>=8.0.0` - Testing framework
- `coverage>=7.6` - Code coverage reporting
- `playwright>=1.55` - Browser automation for E2E tests

**4. Configure Environment Variables**

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` to set your Pi's IP address and sensor I²C addresses:
```env
PI_HOST=192.168.88.49
PI_USER=pi
RDWC_PH_ADDR=0x63
RDWC_EC_ADDR=0x64
RDWC_RTD_ADDR=0x66
```

### Running Tests

**Run All Tests:**
```bash
pytest
```

**Run Specific Test File:**
```bash
pytest tests/test_ph_control.py
```

**Run with Coverage:**
```bash
pytest --cov=app --cov-report=html
# View coverage report: open htmlcov/index.html
```

**Run Specific Test Function:**
```bash
pytest tests/test_dosing_math_basic.py::test_calculate_dose_ml
```

**Run Tests with Verbose Output:**
```bash
pytest -v
```

**Run Tests with Output (show print statements):**
```bash
pytest -s
```

**Key Test Files:**
- `test_commissioning_sim.py` - Simulated commissioning workflow
- `test_relay_guard_basic.py` - Relay safety guards
- `test_ph_control.py` - pH dosing logic
- `test_ec_control.py` - EC/nutrient dosing
- `test_mode_system_e2e.py` - Mode controller E2E tests
- `test_frontend_logs_retention.py` - Frontend logs auto-trim

**Note:** VS Code test discovery is disabled in this workspace to reduce noise. Use the command-line pytest commands above.

### Running the Development Server

**On Windows (dev machine):**
```powershell
# Activate virtual environment first
.\venv\Scripts\Activate.ps1

# Start FastAPI with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

**On Linux/macOS/Raspberry Pi:**
```bash
# Activate virtual environment first
source .venv/bin/activate

# Start FastAPI with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

**Access the UI:**
- Local: http://localhost:8080
- Network: http://YOUR_IP:8080

**API Documentation:**
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

**Development Features:**
- `--reload` flag enables auto-restart on code changes
- SQLite database at `data/rdwc.db` (created automatically)
- Logs output to console in development mode

### Code Quality Tools

This project follows Python best practices with minimal tooling overhead:

**Manual Code Review:**
- Follow existing code style (4-space indentation, clear naming)
- Keep functions focused and testable
- Add docstrings for complex logic
- Comment non-obvious safety guards

**Automated Checks:**
- Pytest for unit/integration tests (see above)
- Coverage tracking via `pytest --cov`
- Dependabot for dependency updates (weekly)

**VS Code Configuration:**
- Test discovery disabled (use CLI pytest)
- Python extension configured for workspace
- Recommended: Install Pylance, Python extensions

### Deployment

**Quick Deploy (from dev machine to Pi):**
```powershell
# Deploy main API + controllers
.\deploy\deploy_controllers.ps1

# Deploy sensor poller service
.\deploy\deploy_sensor_poller.ps1

# Refresh running services (quick restart)
.\deploy\refresh_api.ps1 -Host $env:PI_HOST -User $env:PI_USER
.\deploy\refresh_poller.ps1 -Host $env:PI_HOST -User $env:PI_USER
```

**Full Deploy (Bash script):**
```bash
./deploy_pi.sh
```

**Manual Systemd Setup on Pi:**
```bash
# Main API service
sudo cp systemd/rdwc.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rdwc.service
sudo systemctl start rdwc.service

# Sensor poller service
sudo cp deploy/systemd/rdwc-sensors* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rdwc-sensors.service

# Verify services
systemctl status rdwc.service --no-pager
systemctl status rdwc-sensors.service --no-pager
```

**Deployment Best Practices:**
- Always test changes locally first
- Run pytest before deploying
- Deploy sensor poller independently (separate service)
- Clear browser cache after deployment (Ctrl+Shift+R)
- Check logs after deployment: `journalctl -u rdwc.service -f`

**Deployment Documentation:**
- `deploy/DEPLOYMENT_SUMMARY.md` - Detailed deployment guide
- `COMMISSIONING_RUNBOOK.md` - First-time hardware setup
- `REFRESH_RUNBOOK.md` - Quick service refresh procedures

### Project Structure

**Key Directories:**
- `app/` - FastAPI application code
  - `main.py` - Main application entry point
  - `relays_core.py` - GPIO relay control (ONLY file touching pins)
  - `sensors_core.py` - Sensor reading logic
  - `ph_control.py`, `ec_control.py` - Dosing controllers
  - `scheduler.py` - Lights schedule management
  - `sensor_poller.py` - Background sensor polling service
  - `blueprints/` - UI route handlers
  - `templates/` - Jinja2 HTML templates
  - `static/` - CSS, JavaScript, images
- `tests/` - Pytest test files
- `deploy/` - Deployment scripts and systemd configs
- `tools/` - Utility scripts (commissioning, health checks)
- `data/` - SQLite database (auto-created)
- `docs/` - Additional documentation

**Important Files:**
- `requirements.txt` - Production dependencies
- `requirements-dev.txt` - Development/testing dependencies
- `pytest.ini` - Pytest configuration
- `conftest.py` - Shared pytest fixtures
- `.env.example` - Environment variable template
- `VERSION` - Current version string
- `CHANGELOG.md` - Version history

### Troubleshooting

**Port 8080 already in use:**
```powershell
# Windows: Find and kill process
Get-Process -Id (Get-NetTCPConnection -LocalPort 8080).OwningProcess | Stop-Process
```

**Import errors:**
```bash
# Ensure virtual environment is activated
# Reinstall dependencies
pip install -r requirements.txt
```

**GPIO errors on non-Pi:**
- GPIO operations are mocked in tests
- Use `RDWC_GPIO_MOCK=1` environment variable for testing

**I²C errors:**
- Only run sensor code on Raspberry Pi hardware
- Tests use mocked sensor responses

**Database locked:**
```bash
# Check for stale locks
rm -f data/rdwc.db-journal
```

## Ops: No-Pytest Health Checks

- Refresh services on the Pi and view logs:
  - `./deploy/refresh_poller.ps1 -Host $env:PI_HOST -User $env:PI_USER`
- Verify sensors are fresh (<60s):
  - `./tools/sensor_health.ps1 -Host $env:PI_HOST`

VS Code is configured to disable local test discovery to reduce noise. Use the scripts above for runtime checks.
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

## Mode Controller System

**NEW in v4.1.0**: Independent mode control for each subsystem.

Each controller supports three operational modes:
- **Auto**: Automation enabled (pH/EC dosing, temperature control, scheduled lights)
- **Manual**: Automation disabled, manual operations only
- **Maintenance**: Diagnostics mode with relaxed guards

**Controllers**: pH, EC, Lights, Chiller, Circulation

**Mode Persistence**: Modes are stored in SQLite and survive restarts. UI syncs with backend on page load.

**API Access**:
```bash
# Get all controller modes
curl http://192.168.88.49:8080/api/controller/modes

# Get specific controller mode
curl http://192.168.88.49:8080/api/controller/ph/mode

# Set controller to manual mode
curl -X POST http://192.168.88.49:8080/api/controller/ph/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "manual"}'
```

See `MODE_CONTROLLER_IMPLEMENTATION.md` for detailed documentation.

## Dashboard Tabs

Web UI organized by function (http://192.168.88.49:8080):

1. **Overview**: System at-a-glance, health indicators, grow day counter
2. **pH Control**: Manual dosing, automation, dose history, settings, **mode selector**
3. **EC Control**: G/M/B nutrient dosing, mix ratios, auto-raise, CSV export, **mode selector**
4. **Temperature**: Chiller control, min ON/OFF protections, **mode selector**
5. **Lights**: Schedule (start time, duration), manual override, **mode selector**
6. **Sensors**: Live readings, export, calibration status
7. **Trends**: Multi-day charts (pH, EC, temp) with date pickers
8. **Relays**: Manual relay control, state viewer, cooldown timers
9. **Settings**: General (reservoir size, grow start), Alerts (email/Telegram), Calibration

> Version: `v4.1.0` — see CHANGELOG.md

## How it works


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
# Sensor poller + watchdog
sudo cp deploy/systemd/rdwc-sensors* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rdwc-sensors.service
sudo systemctl enable --now rdwc-sensors-watchdog.timer

# DB maintenance (weekly export + vacuum)
sudo cp deploy/systemd/rdwc-db-maint.* /etc/systemd/system/
sudo install -m 0755 deploy/db_maint.sh /usr/local/bin/rdwc_db_maint.sh
sudo systemctl daemon-reload
sudo systemctl enable --now rdwc-db-maint.timer
```

### DB Maintenance (weekly)
- Purpose: Export last 24h CSV to /home/pi/backups and VACUUM the SQLite DB.
- Files:
  - deploy/db_maint.sh -> installed to /usr/local/bin/rdwc_db_maint.sh
  - deploy/systemd/rdwc-db-maint.service (oneshot)
  - deploy/systemd/rdwc-db-maint.timer (Sun 03:30)
- Check status:
```bash
systemctl list-timers rdwc-db-maint.timer --no-pager
journalctl -u rdwc-db-maint.service -n 20 --no-pager
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