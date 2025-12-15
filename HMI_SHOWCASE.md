# RDWC-v4 HMI Showcase — System Dashboard

## 🎨 User Interface Overview

The RDWC-v4 system provides a modern, responsive web-based HMI (Human-Machine Interface) for monitoring and controlling the entire hydroponic system. Built with **React** and **Chart.js**, the interface runs directly on the Raspberry Pi and is accessible from any browser on the network.

**Access**: `http://<pi-ip>:8080` (default `http://192.168.88.49:8080`)

---

## 📑 Dashboard Tabs

### 1. **Overview Tab** — System Health & Status
- 🔴 **Status Indicators**: Global AUTO mode, E-STOP state, sensor freshness
- 📊 **Quick KPIs**: Latest temperature, pH, EC readings
- ⚡ **Controller Status**: pH auto, EC auto, chiller, circulation, lights state
- 🎛️ **Mode Selector**: Switch between AUTO / MANUAL (with safety guards)

*Purpose*: Get a bird's-eye view of system health before diving into details

---

### 2. **Sensors Tab** — Real-Time & Historical Data
- 🌡️ **Live Readings**: Temperature (°C), pH, EC (mS/cm), freshness age
- 📈 **Trend Chart**: 24-hour history of all three parameters
- 🔄 **Poller Status**: Polling interval, last read timestamp, online/offline indicator
- 📡 **Diagnostics**: Sensor address, I²C status, calibration age

*Purpose*: Monitor sensor health and verify calibrations are fresh

---

### 3. **pH Tab** — pH Control & Dosing
- 📍 **Current Value**: Live pH reading + target band (5.8–6.2)
- 🎯 **Targets**: pH low/high sliders, auto-enable toggle
- 💧 **Manual Dose Button**: One-press pH_UP (0.5s default, customizable)
- 📊 **Dose Log**: Recent pH_UP events with timestamps, volumes, pre/post values
- 🛡️ **Safety Status**: 
  - pH guard active (blocks pH_UP if pH ≥ 6.2)
  - Daily cap remaining (seconds used / max)
  - Last dose timestamp

*Purpose*: Manually adjust pH or monitor auto dosing behavior

---

### 4. **EC Tab** — Nutrient Control & Dosing
- 📍 **Current Value**: Live EC reading + target band (0.4–0.6 low, 1.8 ideal)
- 🎯 **Targets**: EC low/high sliders, nutrient mix ratio (G:M:B)
- 💧 **Manual Dose Buttons**:
  - Grow nutrient (customizable seconds)
  - Micro nutrient (customizable seconds)
  - Bloom nutrient (customizable seconds)
  - Sequential mix (all three in ratio)
- 📊 **Dose Log**: Recent nutrient doses with pump, volume, mix ratio
- 📈 **Learning Curve**: Estimated ml/mS·cm response from prior doses
- 🛡️ **Safety Status**:
  - EC guard active (blocks nutrients if EC ≥ 0.6 + threshold)
  - Daily cap remaining
  - Last dose timestamp

*Purpose*: Manage nutrient levels and observe auto-dosing learning curve

---

### 5. **Dosing Tab** — Unified Dose Event Log
- 📋 **Event Stream**: All dose events (pH_UP, grow/micro/bloom, nutrient mix)
- 🟢 **Successful Doses**: Logged with pump, seconds, delta (ph/ec before/after)
- 🔴 **Blocked Doses**: Shown with reason (ph_guard, ec_guard, daily_cap, press_cap, stale, estop, etc.)
- ⏱️ **Timestamps**: ISO format with age indicator
- 📊 **Statistics**: Total events, success rate, most common blocker

*Purpose*: Deep dive into why doses succeeded or were blocked; validate safety guards

---

### 6. **Chiller Tab** — Temperature Control
- 🌡️ **Current Water Temp**: Live RTD reading (°C)
- 🎯 **Target Temperature**: Setpoint (default 19°C)
- 🔄 **Chiller Mode**: 
  - **OFF**: Disabled
  - **AUTO**: Turns ON when temp > target + 1°C, OFF when temp < target
  - **HOLD ON**: Manual override (for manual tests)
- ⏱️ **Cooldown**: Min on/off times to prevent rapid cycling
- 📊 **Stage Display**: Current stage (IDLE, ACTIVE, COOLING, HOLD)
- 📈 **Relay Event Log**: Recent chiller toggles with reasons (temp, manual, etc.)

*Purpose*: Monitor and control water temperature for optimal plant health

---

### 7. **Lights Tab** — Grow Cycle & Schedule
- 🕐 **Schedule Configuration**:
  - Light ON time (HH:MM)
  - Light OFF time (HH:MM)
  - Duration (calculated)
- 🔄 **Mode**: SCHEDULE (automated) or MANUAL (override)
- 💡 **Current State**: ON / OFF with timestamp
- 📅 **Next Edge**: Countdown to next ON or OFF event
- 📊 **Relay Event Log**: Recent light toggles with schedule times
- ⚙️ **Advanced**:
  - Guard times (e.g., don't toggle for 60s after startup)
  - Reason tracking (schedule, manual, startup, etc.)

*Purpose*: Automate and monitor plant photoperiod

---

### 8. **Circulation Tab** — Pump Control
- 💨 **Current State**: ON / OFF with duration
- 🔄 **Mode**: 
  - **SCHEDULE**: Automated via time-based schedule (if configured)
  - **ALWAYS ON**: Continuous operation
  - **MANUAL**: User control
- ⏱️ **Cooldown Times**: Min on/off windows for pump protection
- 📊 **Relay Event Log**: Recent toggles with reasons
- ⚙️ **Status**: Healthy / Offline / Error

*Purpose*: Ensure consistent water circulation through system

---

### 9. **Relays Tab** — Hardware Control Panel
- 🎛️ **Relay Status**: Lights, chiller, main pump, dosing pumps
- 🔴 **State Indicators**: Visual ON/OFF state per relay
- 🚨 **E-STOP Button**: 
  - **Current State**: ARMED or TRIGGERED
  - **Toggle**: Emergency stop / Resume (manually toggle)
- 📊 **Cooldown Remaining**: Time before each relay can toggle again
- 📈 **Event Log**: Last 20 relay changes with timestamps and reasons
- ⚙️ **Advanced**: 
  - Force override toggle (requires safety.allow_force = true)
  - Reason tracking (schedule, auto, manual, E-STOP, etc.)

*Purpose*: Direct hardware control and emergency stop management

---

### 10. **System Tab** — Global Settings & Configuration
- ⚙️ **Safety Limits**:
  - Max seconds per press (single dose cap)
  - Max total seconds per 24h (daily dosing cap)
  - Min off window (seconds between doses)
  - Temperature min on/off windows
  - Chiller min on/off windows
- 🎯 **Target Values**:
  - pH low/high/band
  - EC low/high/target/tolerance
  - Temperature target
  - Reservoir size (liters)
- 📡 **Sensor Configuration**:
  - I²C addresses (RTD, pH, EC)
  - Polling interval (seconds)
  - Temperature compensation settings
- 💾 **Database Management**:
  - Export settings (JSON download)
  - Import settings (JSON upload)
  - Reset to defaults

*Purpose*: Tune and monitor system-wide parameters without touching code

---

## 📊 Real-Time Charts

### Sensor Trend Chart (Sensors Tab)
- **X-axis**: Time (last 24 hours)
- **Y-axis 1 (left)**: Temperature °C, pH
- **Y-axis 2 (right)**: EC mS/cm
- **Data Points**: Updated every 10–30 seconds (poller dependent)
- **Features**: Zoom, pan, export to CSV

*Purpose*: Visualize long-term sensor stability and trends

---

## 🔐 Safety & Access Control

- **No Authentication**: System assumes trusted local network (LAN only)
- **E-STOP**: Physical override button on UI (always available)
- **Safe Off**: Persisted across reboots
- **Manual Override Guard**: Dose + relay actions logged with user intent
- **Rate Limiting**: API endpoints have basic rate limits to prevent abuse

---

## 🎨 Design Principles

1. **Simple & Clear**: Minimal clutter, focus on critical info
2. **Real-Time**: All controls and charts update live
3. **Autonomous**: UI is optional; system runs 24/7 even if browser closed
4. **Logged**: Every action (dose, relay toggle, override) recorded to SQLite
5. **Safe Defaults**: All settings have backend defaults, system works without UI

---

## 📷 Screenshots

### Coming Soon
Screenshots of each tab will be added to this page. For now, you can:

1. **Run the system locally**:
   ```bash
   pip install -r requirements.txt
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
   ```

2. **Access the UI**:
   - http://localhost:8080 (from dev machine)
   - http://<pi-ip>:8080 (from Pi on network)

3. **Explore Tabs**: Click through each tab to see the interface

---

## 🔧 Browser Compatibility

- **Chrome/Chromium**: Fully supported (primary development target)
- **Firefox**: Fully supported
- **Safari**: Fully supported (mobile-optimized)
- **IE/Edge (legacy)**: Not supported

**Recommended**: Modern browser (Chrome 90+, Firefox 88+, Safari 14+) on desktop or tablet

---

## 📱 Mobile Support

The HMI is designed to be responsive and works on tablets and phones, though some controls are best used on larger screens. For overnight monitoring, you can keep the page open on a tablet or phone and watch dose events stream in real-time.

---

## 🚀 Future Enhancements

- Alarm & alerting UI (push notifications, email)
- Historical reports (weekly/monthly summaries)
- Photo gallery integration (camera feeds)
- Dark mode support
- Multi-user roles & permissions

---

**Last Updated**: December 15, 2025  
**Version**: v4.0.0  
**Status**: 🟢 Production (90% Commissioning)

