# RDWC-v4 Deployment Instructions to Raspberry Pi

## Overview

This guide provides step-by-step instructions for deploying the RDWC-v4 system to a Raspberry Pi for testing and production use.

---

## Prerequisites

### Hardware Requirements
- Raspberry Pi 4 (4GB+ RAM recommended)
- MicroSD card (32GB+ recommended)
- Power supply (5V 3A minimum)
- Network connection (Ethernet or WiFi)
- Atlas Scientific EZO sensors (RTD, pH, EC)
- Relay board for actuator control
- Assembled RDWC system hardware

### Software Requirements on Development Machine
- Git
- SSH client
- Text editor (VS Code recommended)

---

## Deployment Methods

### Method 1: Direct Git Pull on Pi (Recommended for Testing)

This is the simplest method for development and testing.

#### Step 1: Prepare the Raspberry Pi

```bash
# SSH into your Pi
ssh pi@<pi-ip-address>

# Update system
sudo apt update && sudo apt upgrade -y

# Install required system packages
sudo apt install -y python3-pip python3-venv git i2c-tools

# Enable I2C interface
sudo raspi-config nonint do_i2c 0

# Reboot to apply I2C changes
sudo reboot
```

#### Step 2: Clone the Repository

```bash
# SSH back in after reboot
ssh pi@<pi-ip-address>

# Clone the repository
cd /home/pi
git clone https://github.com/collinerasmus/RDWC-v4.git
cd RDWC-v4

# Check out the specific branch (if not main)
git checkout copilot/remove-duplicate-pump-calibrations
```

#### Step 3: Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
pip install -r requirements-dev.txt  # if running tests
```

#### Step 4: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit configuration
nano .env

# Set at minimum:
# - SENSOR_POLL_INTERVAL=10
# - DATABASE_PATH=data/rdwc.db
# - I2C_BUS=1
# - CALIB_ENABLE=0  (set to 1 only during calibration)
```

#### Step 5: Initialize Database

```bash
# Create data directory if it doesn't exist
mkdir -p data

# Initialize database (automatic on first run, but can be forced)
python -m app.main --init-db
```

#### Step 6: Test I2C Sensors

```bash
# Verify I2C devices are detected
sudo i2cdetect -y 1

# Expected output should show devices at:
# - 0x63 (pH sensor)
# - 0x64 (EC sensor)  
# - 0x66 (RTD temperature sensor)

# Test sensor communication
python -c "
from app.sensors_core import read_all_sensors
data = read_all_sensors()
print('Sensors:', data)
"
```

#### Step 7: Start Services

```bash
# Option A: Manual start for testing
# Terminal 1: Start API server
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080

# Terminal 2: Start sensor poller
source venv/bin/activate
python app/sensor_poller.py

# Option B: Use systemd (production)
sudo cp deploy/systemd/rdwc-api.service /etc/systemd/system/
sudo cp deploy/systemd/rdwc-sensors.service /etc/systemd/system/

# Edit service files to point to your installation
sudo nano /etc/systemd/system/rdwc-api.service
# Update paths: /home/pi/RDWC-v4/venv/bin/...

sudo nano /etc/systemd/system/rdwc-sensors.service
# Update paths: /home/pi/RDWC-v4/venv/bin/...

# Reload systemd and start services
sudo systemctl daemon-reload
sudo systemctl enable rdwc-api
sudo systemctl enable rdwc-sensors
sudo systemctl start rdwc-api
sudo systemctl start rdwc-sensors

# Check status
sudo systemctl status rdwc-api
sudo systemctl status rdwc-sensors
```

#### Step 8: Access Web UI

```bash
# From your development machine, open browser:
http://<pi-ip-address>:8080

# You should see the RDWC v4 Dashboard
```

---

### Method 2: Deployment Script (Automated)

Use the included deployment script for automated setup.

```bash
# On your development machine
cd /path/to/RDWC-v4

# Run deployment script
./deploy/deploy_pi.sh pi@<pi-ip-address>

# This will:
# - Copy files to Pi
# - Install dependencies
# - Configure services
# - Start the system

# Follow prompts for configuration
```

---

## Verification Steps

### 1. Check API Health

```bash
# From Pi or development machine
curl http://<pi-ip-address>:8080/health

# Expected response:
# {
#   "status": "healthy",
#   "timestamp": "2025-11-21T19:00:00",
#   "services": {
#     "api": "running",
#     "sensor_poller": "running"
#   }
# }
```

### 2. Check Sensor Data

```bash
curl http://<pi-ip-address>:8080/api/sensors

# Expected response:
# {
#   "temperature_c": 22.5,
#   "ph": 6.1,
#   "ec_mscm": 1.45,
#   "online": true,
#   "ts": 1732214400,
#   "errors": []
# }
```

### 3. Check Relay Status

```bash
curl http://<pi-ip-address>:8080/api/relays/status

# Expected response showing all relay states
```

### 4. Verify Web UI Functions

Open the UI in a browser and verify:
- [ ] All tabs load without errors
- [ ] Overview shows system status
- [ ] Sensors tab displays current readings
- [ ] pH and EC tabs load controllers
- [ ] Chiller tab shows temperature control
- [ ] Circulation tab shows pump controls
- [ ] Lights tab shows schedule
- [ ] Scheduler tab loads timeline
- [ ] System tab shows settings

### 5. Test Mode Button Removal

Verify the recent changes:
- [ ] Overview tab has NO mode buttons (only E-STOP)
- [ ] Sensors tab has NO mode buttons (only E-STOP)
- [ ] Scheduler tab has NO mode buttons (only E-STOP)
- [ ] System tab DOES have mode buttons (correct location)

### 6. Test Calibration Sections

Verify duplicate removal:
- [ ] Sensors tab has NO "pH Pump Calibration" section
- [ ] Sensors tab has NO "EC Pumps Calibration" section
- [ ] pH tab HAS "Pump Calibration" section
- [ ] EC tab HAS "Pumps Calibration" section

---

## Testing Workflows

### Sensor Calibration Workflow

```bash
# 1. Enable calibration mode
nano .env  # Set CALIB_ENABLE=1
sudo systemctl restart rdwc-api

# 2. Access UI and navigate to pH tab
# 3. Use "Pump Calibration" section to calibrate pH pump
# 4. Navigate to EC tab
# 5. Use "Pumps Calibration" section to calibrate EC pumps

# 6. Disable calibration mode when done
nano .env  # Set CALIB_ENABLE=0
sudo systemctl restart rdwc-api
```

### Manual Dosing Test

```bash
# From pH tab in UI:
# - Click "+1 ml" button
# - Verify pump activates
# - Check dose is logged

# Verify via API:
curl http://<pi-ip-address>:8080/api/ph/dose_log | jq
```

### Relay Control Test

```bash
# From System tab → Relays section:
# - Toggle each relay
# - Verify relay state changes
# - Check cooldown timers work

# Verify via API:
curl http://<pi-ip-address>:8080/api/relays/status | jq
```

### E-STOP Test

```bash
# From any tab:
# - Click E-STOP button
# - Verify all relays turn OFF
# - Verify no relays can be turned ON
# - Click E-STOP again to release
# - Verify relays can now be controlled

# Verify via API:
curl http://<pi-ip-address>:8080/api/relays/status | jq '.estop'
```

---

## Troubleshooting

### Services Not Starting

```bash
# Check logs
sudo journalctl -u rdwc-api -f
sudo journalctl -u rdwc-sensors -f

# Check service status
sudo systemctl status rdwc-api
sudo systemctl status rdwc-sensors

# Restart services
sudo systemctl restart rdwc-api
sudo systemctl restart rdwc-sensors
```

### Sensors Not Detected

```bash
# Verify I2C is enabled
ls /dev/i2c*

# Scan for devices
sudo i2cdetect -y 1

# If sensors not found:
# - Check wiring
# - Verify power to sensors
# - Check I2C pullup resistors
# - Try different I2C addresses
```

### Web UI Not Loading

```bash
# Check API is running
curl http://localhost:8080/health

# Check firewall
sudo ufw status
sudo ufw allow 8080

# Check port binding
sudo netstat -tulpn | grep 8080

# Check nginx (if used)
sudo systemctl status nginx
```

### Database Errors

```bash
# Check database exists
ls -l data/rdwc.db

# Check permissions
chmod 644 data/rdwc.db

# Backup and recreate if corrupted
mv data/rdwc.db data/rdwc.db.bak
python -m app.main --init-db
```

---

## Performance Optimization

### For Production Use

```bash
# 1. Disable debug logging
nano .env
# Set LOG_LEVEL=INFO

# 2. Optimize database
sqlite3 data/rdwc.db "VACUUM;"
sqlite3 data/rdwc.db "ANALYZE;"

# 3. Set up log rotation
sudo nano /etc/logrotate.d/rdwc
# Add:
# /var/log/rdwc/*.log {
#     daily
#     rotate 7
#     compress
#     delaycompress
#     missingok
#     notifempty
# }

# 4. Monitor system resources
htop
# Watch CPU, memory, disk I/O
```

---

## Updating the System

### Git Pull Method

```bash
# SSH to Pi
ssh pi@<pi-ip-address>
cd /home/pi/RDWC-v4

# Stop services
sudo systemctl stop rdwc-api
sudo systemctl stop rdwc-sensors

# Pull latest changes
git pull origin copilot/remove-duplicate-pump-calibrations

# Update dependencies if needed
source venv/bin/activate
pip install -r requirements.txt

# Restart services
sudo systemctl start rdwc-api
sudo systemctl start rdwc-sensors

# Verify
sudo systemctl status rdwc-api
sudo systemctl status rdwc-sensors
```

---

## Backup and Restore

### Backup

```bash
# Backup database
cp data/rdwc.db backups/rdwc_backup_$(date +%Y%m%d_%H%M%S).db

# Backup settings
cp .env backups/.env_backup_$(date +%Y%m%d_%H%M%S)

# Full system backup (optional)
tar -czf ~/rdwc_full_backup_$(date +%Y%m%d).tar.gz \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  /home/pi/RDWC-v4
```

### Restore

```bash
# Restore database
cp backups/rdwc_backup_YYYYMMDD_HHMMSS.db data/rdwc.db

# Restore settings
cp backups/.env_backup_YYYYMMDD_HHMMSS .env

# Restart services
sudo systemctl restart rdwc-api
sudo systemctl restart rdwc-sensors
```

---

## Security Recommendations

1. **Change Default Passwords**
   ```bash
   passwd  # Change pi user password
   ```

2. **Set Up Firewall**
   ```bash
   sudo apt install ufw
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow ssh
   sudo ufw allow 8080  # RDWC API
   sudo ufw enable
   ```

3. **Use SSH Keys**
   ```bash
   # On your dev machine:
   ssh-copy-id pi@<pi-ip-address>
   
   # On Pi, disable password auth:
   sudo nano /etc/ssh/sshd_config
   # Set: PasswordAuthentication no
   sudo systemctl restart sshd
   ```

4. **Regular Updates**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

---

## VS Code Remote Development (Optional)

For easier development and testing:

1. Install "Remote - SSH" extension in VS Code
2. Configure SSH connection to Pi
3. Open RDWC-v4 folder remotely
4. Edit files directly on Pi
5. Use integrated terminal for commands

---

## Support and Feedback

### GitHub Comments

To provide feedback or request changes through GitHub Copilot:

1. Go to the Pull Request on GitHub
2. Add a comment with your observations:
   ```
   @copilot I tested the deployment and found:
   - ✅ Mode buttons removed successfully
   - ✅ Calibration sections in correct locations
   - ⚠️ Issue: [describe any problems]
   - 💡 Suggestion: [describe improvements]
   ```

3. Copilot will respond with:
   - Confirmation of successful changes
   - Fixes for identified issues
   - Implementation of suggestions

### Verification Checklist for User

After deployment, please verify and comment on GitHub:

- [ ] System deployed successfully to Pi
- [ ] All services running (API + sensor poller)
- [ ] Web UI accessible at http://<pi-ip>:8080
- [ ] Mode buttons removed from Overview, Sensors, Scheduler tabs
- [ ] Mode buttons present only in System tab
- [ ] Duplicate calibration sections removed from Sensors tab
- [ ] pH calibration available in pH tab
- [ ] EC calibration available in EC tab
- [ ] All tabs load without errors
- [ ] Sensor readings displayed correctly
- [ ] Relay controls functional
- [ ] E-STOP works as expected

---

## Next Steps

After successful deployment and verification:

1. Test system functionality thoroughly
2. Report any issues on GitHub PR
3. Request additional features if needed
4. Proceed with remaining phases:
   - Circulation safety interlock
   - Lights schedule midnight fix
   - Scheduler completion
   - System tab enhancements
   - Documentation creation

---

## Quick Reference Commands

```bash
# Service management
sudo systemctl status rdwc-api
sudo systemctl restart rdwc-api
sudo systemctl stop rdwc-api
sudo journalctl -u rdwc-api -f

# Check sensors
sudo i2cdetect -y 1
curl http://localhost:8080/api/sensors

# Check system health
curl http://localhost:8080/health

# View logs
tail -f /var/log/rdwc/api.log
tail -f /var/log/rdwc/sensors.log

# Database query
sqlite3 data/rdwc.db "SELECT * FROM readings ORDER BY ts DESC LIMIT 10;"

# Update code
cd /home/pi/RDWC-v4
git pull
sudo systemctl restart rdwc-api rdwc-sensors
```

---

## Appendix: System Architecture

```
┌─────────────────────────────────────────────┐
│          Web Browser (User)                 │
└──────────────────┬──────────────────────────┘
                   │ HTTP :8080
                   │
┌──────────────────▼──────────────────────────┐
│         FastAPI Application                 │
│         (app/main.py)                       │
│                                             │
│  ├─ API Endpoints (/api/*)                 │
│  ├─ Static Files (/static/*)               │
│  └─ Health Check (/health)                 │
└───┬─────────────┬────────────────┬──────────┘
    │             │                │
    │             │                │
┌───▼─────┐   ┌───▼────┐      ┌───▼──────┐
│ SQLite  │   │ GPIO   │      │ Sensor   │
│Database │   │Relays  │      │ Poller   │
│         │   │        │      │ Service  │
│ ├─readings  │ ├─lights     │ (separate │
│ ├─settings  │ ├─pumps      │ process)  │
│ └─doses     │ └─valves     │           │
└─────────┘   └────────┘      └───┬───────┘
                                  │
                               ┌──▼──────┐
                               │ I²C Bus │
                               │         │
                               │ ├─ RTD  │
                               │ ├─ pH   │
                               │ └─ EC   │
                               └─────────┘
```

---

*Last Updated: 2025-11-21*
