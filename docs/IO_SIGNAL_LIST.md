# RDWC I/O & Signal List

**Document**: IO-001  
**System**: RDWC v4 Input/Output Specification  
**Date**: 2025-11-22  
**Revision**: As-Built v1.0  

---

## Input Signals (Sensors)

| Tag | Description | Type | Address/Pin | Range | Units | Accuracy | Fail-Safe |
|-----|-------------|------|-------------|-------|-------|----------|-----------|
| TI-101 | RTD Temperature | I²C Analog | 0x66 | 0-100 | °C | ±0.1°C | Last good value |
| AI-102 | pH Measurement | I²C Analog | 0x63 | 0-14 | pH | ±0.02 pH | Last good value |
| AI-103 | EC Measurement | I²C Analog | 0x64 | 0-10000 | µS/cm | ±2% | Last good value |

### Sensor Details

#### TI-101: RTD Temperature Sensor
- **Device**: Atlas Scientific RTD EZO
- **Probe Type**: PT-1000 RTD
- **Response Time**: <1 second
- **Calibration**: Factory calibrated (1-point field verification available)
- **Polling Rate**: 10 seconds (background poller)
- **Temperature Compensation**: Feeds pH and EC sensors (throttled: ΔT ≥ 0.2°C or ≥ 60s)
- **Fail-Safe**: Readings older than 120s trigger stale flag, freeze automation

#### AI-102: pH Sensor
- **Device**: Atlas Scientific pH EZO
- **Probe Type**: Glass pH electrode with Ag/AgCl reference
- **Response Time**: 95% in 1 second
- **Calibration**: 3-point (pH 4.0, 7.0, 10.0 buffers) or 2-point (4.0, 7.0)
- **Slope**: Acceptable range 95-105% (ideal 100% = -59.16mV per pH unit)
- **Polling Rate**: 10 seconds (background poller)
- **Temperature Compensation**: Automatic from TI-101
- **Fail-Safe**: Readings older than 120s trigger stale flag, block dosing

#### AI-103: EC Sensor
- **Device**: Atlas Scientific EC EZO
- **Probe Type**: 2-electrode conductivity cell (K=1.0)
- **Response Time**: <1 second
- **Calibration**: 2-point (dry=0, low=1413 µS/cm) or 1-point (1413 only)
- **K Value**: 1.0 (configurable 0.1-10.0)
- **Polling Rate**: 10 seconds (background poller)
- **Temperature Compensation**: Automatic from TI-101
- **Fail-Safe**: Readings older than 120s trigger stale flag, block dosing

---

## Output Signals (Actuators)

### Dosing Pumps (Digital Outputs)

| Tag | Description | GPIO (BCM) | Phys Pin | Relay CH | Power | Flow Rate | Duty Cycle | Daily Cap |
|-----|-------------|------------|----------|----------|-------|-----------|------------|-----------|
| PP-201 | pH UP Pump | 5 | 29 | CH1 | 12VDC | ~5 mL/s* | On-demand | 120s |
| PP-202 | Micro Nutrient Pump | 13 | 33 | CH3 | 12VDC | ~5 mL/s* | Once/day | 300s |
| PP-203 | Grow Nutrient Pump | 6 | 31 | CH2 | 12VDC | ~5 mL/s* | Once/day | 300s |
| PP-204 | Bloom Nutrient Pump | 19 | 35 | CH5 | 12VDC | ~5 mL/s* | Once/day | 300s |

*Flow rates calibrated via `/calib/dose/pumps` API

**Dosing Safety**:
- Press cap: 60s max per press (ph_up), 120s (nutrients)
- Daily cap: 120s/day (ph_up), 300s/day (nutrients)
- Sensor staleness check: blocks if readings >120s old
- EC baseline check: pH dosing blocked if EC <500 µS (baseline_low)
- E-STOP override: all dosing immediately halted

### Circulation Pumps (Digital Outputs)

| Tag | Description | GPIO (BCM) | Phys Pin | Relay CH | Power | Flow Rate | Interlock |
|-----|-------------|------------|----------|----------|-------|-----------|-----------|
| P-301 | Main Circulation Pump | 26 | 37 | CH8 | 120VAC | ~1000 L/hr* | None (master) |
| P-302 | Chiller Circulation Pump | 16 | 36 | CH4 | 120VAC | ~500 L/hr* | Requires P-301 ON |

*Flow rates TBD based on actual pump specs

**Circulation Interlock**:
- P-302 (chiller pump) CANNOT turn ON unless P-301 (main pump) is running
- If P-301 stops, P-302 and C-401 (chiller) are immediately forced OFF
- Reason: Prevents chiller operation without flow through main system
- Override: E-STOP or manual mode only

### Cooling System (Digital Outputs)

| Tag | Description | GPIO (BCM) | Phys Pin | Relay CH | Power | Capacity | Interlock |
|-----|-------------|------------|----------|----------|-------|----------|-----------|
| C-401 | Water Chiller | 20 | 38 | CH6 | 120VAC | ~200W* | Requires P-301 ON |

*Cooling capacity TBD based on actual chiller specs

**Temperature Control Logic**:
- Hysteresis: 0.5°C (configurable via `targets.temp_hysteresis`)
- Start condition: temp > target_high + hysteresis (e.g., >24°C if target 23°C, hyst 1°C)
- Stop condition: temp < target_low (e.g., <21°C)
- MIN_ON: 300s (prevents rapid cycling)
- MIN_OFF: 300s (compressor protection)

### Lighting System (Digital Outputs)

| Tag | Description | GPIO (BCM) | Phys Pin | Relay CH | Power | Schedule | Protection |
|-----|-------------|------------|----------|----------|-------|----------|------------|
| L-501 | Grow Lights | 21 | 40 | CH7 | 120VAC | Edge-based | Protected relay |

**Lights Control**:
- Schedule: ON at `lights_on_time`, OFF at `lights_off_time` (from settings)
- Midnight crossover: Correctly handles ON 20:00, OFF 08:00 (next day)
- Edge-only: No periodic catch-up, pure edge-triggered control
- Protection: Manual override requires whitelisted reason (REASON_OVERRIDE or REASON_MAINTENANCE)
- Cooldown: MIN_OFF = 300s between manual cycles

---

## Control Signals

### Interlocks

| Signal Name | Logic | Priority | Description |
|-------------|-------|----------|-------------|
| CIRCULATION_INTERLOCK | P-301 == ON | HIGH | Enables P-302 and C-401 operation |
| ESTOP_ACTIVE | Software flag | CRITICAL | Disables ALL relays, requires manual reset |

### Dosing Guards

| Signal Name | Condition | Action | Reset |
|-------------|-----------|--------|-------|
| DOSE_STALE | sensor.ts > 120s ago | Block all dosing | Fresh reading received |
| DOSE_PRESS_CAP | duration > 60s (pH) or 120s (nutrients) | Reject dose command | Next dose attempt |
| DOSE_DAILY_CAP | today's total > 120s (pH) or 300s (nutrients) | Block all doses | Midnight rollover |
| PH_GUARD_EC_LOW | EC < 500 µS | Block pH dosing | EC rises above 500 |
| MAINTENANCE_MODE | controller mode == maintenance | Block automation | Mode → auto |

### Mode Signals

| Controller | Signal Name | Values | Effect |
|------------|-------------|--------|--------|
| pH | ph_mode | auto, manual, maintenance | Enables/disables auto-dosing |
| EC | ec_mode | auto, manual, maintenance | Enables/disables auto-dosing |
| Chiller | chiller_mode | auto, manual, maintenance | Enables/disables auto-control |
| Lights | lights_mode | auto, manual, maintenance | Enables/disables schedule |
| Circulation | circulation_mode | auto, manual, maintenance | Enables/disables interlock |

**Mode Hierarchy**:
- `auto`: Full automation enabled
- `manual`: Manual control only, automation disabled
- `maintenance`: Manual control + bypasses some safety checks (e.g., interlock, but NOT daily caps)

---

## Alarm Signals

### High Priority Alarms

| Alarm Tag | Condition | Setpoint | Hysteresis | Action |
|-----------|-----------|----------|------------|--------|
| PAH-102 | pH > ph_high | 6.3 | 0.05 | Alert, hold auto-dosing |
| PAL-102 | pH < ph_low | 5.5 | 0.05 | Alert, hold auto-dosing |
| CAH-103 | EC > ec_high | 2000 µS | 50 µS | Alert, hold auto-dosing |
| CAL-103 | EC < ec_low | 800 µS | 50 µS | Alert, hold auto-dosing |
| TAH-101 | Temp > temp_high | 24°C | 0.5°C | Start chiller, alert if fails |
| TAL-101 | Temp < temp_low | 18°C | 0.5°C | Alert, chiller stuck on? |

### Medium Priority Alarms

| Alarm Tag | Condition | Action |
|-----------|-----------|--------|
| SENSOR_OFFLINE | Any sensor.ts > 120s old | Alert, freeze automation, show staleness in UI |
| DOSE_CAP_EXCEEDED | Daily dose total >= cap | Alert, block further dosing until midnight |
| CALIBRATION_STALE | pH slope not in 95-105% range | Alert, request recalibration |

### Critical Alarms

| Alarm Tag | Condition | Action |
|-----------|-----------|--------|
| MAIN_PUMP_FAULT | P-301 OFF unintentionally | E-STOP chiller system (P-302, C-401 forced OFF) |
| ESTOP_TRIGGERED | User activated E-STOP | All relays OFF, display alert, require manual reset |

---

## Communication Protocols

### I²C Bus
- **Speed**: 100 kHz (standard mode)
- **Pull-ups**: 4.7kΩ on SDA (GPIO 2) and SCL (GPIO 3)
- **Device Addresses**: RTD 0x66, pH 0x63, EC 0x64
- **Protocol**: Atlas EZO command set (ASCII over I²C)
- **Timeout**: 1 second per transaction
- **Error Handling**: Retry once, then use last good value + set stale flag

### GPIO
- **Mode**: BCM numbering (not physical pin numbers)
- **Direction**: All relay pins configured as OUTPUT
- **Active-Low Logic**: HIGH = relay OFF, LOW = relay ON
- **Initialization**: All pins set HIGH (OFF) on boot via `initialize_all_safe_off()`
- **Persistence**: Relay states saved to `~/.rdwc/relay_state.json`, restored on boot (safe relays only)

### API (FastAPI)
- **Protocol**: HTTP/1.1
- **Port**: 8080
- **Endpoints**: RESTful JSON API
- **Authentication**: None (local network only, firewall protected)
- **Rate Limiting**: None (single-user system)
- **WebSocket**: Not used (polling model: frontend polls every 10s)

---

## Database Signals (SQLite)

### Tables
- `readings`: Sensor data (ts, temp_c, ph, ec_mscm, online)
- `ph_dose_log`: pH dosing events (ts, duration_ms, sensor_value_before, sensor_value_after)
- `ec_dose_log`: EC dosing events (ts, pump, duration_ms, ml, ec_before, ec_after)
- `dose_events`: Unified dose log (ts, pump, duration_ms, reason, blocked_by)
- `settings`: Key-value config (key, value, updated_at)
- `chiller_events`: Chiller state changes (ts, event, temp, details)
- `system_state`: Persistent system state (e.g., relay states, E-STOP flag)

### Signal Persistence
- Relay states saved every state change → restored on boot
- Settings saved on every update → restored on boot
- Sensor readings archived every 10s → retained for historical analysis
- Dose logs kept indefinitely → supports learning and auditing

---

## Relay Outputs (Mixed NC / NO Wiring)

| Device | Tag | GPIO | Relay Wiring | Fail (Power / Controller Loss) | Intended Outcome |
|--------|-----|------|--------------|--------------------------------|------------------|
| Main circulation pump | P-301 | 26 | NC | ON | Maintain circulation & oxygenation |
| Chiller circulation pump | P-302 | 16 | NC | ON | Preserve chiller loop circulation |
| Water chiller | C-401 | 20 | NC | ON | Avoid rapid temperature rise |
| Grow lights | L-501 | 21 | NO | OFF | Preserve photoperiod schedule |
| pH UP pump | PP-201 | 5 | NO | OFF | Prevent uncontrolled chemical dosing |
| Micro nutrient pump | PP-202 | 13 | NO | OFF | Prevent nutrient overshoot |
| Grow nutrient pump | PP-203 | 6 | NO | OFF | Prevent nutrient overshoot |
| Bloom nutrient pump | PP-204 | 19 | NO | OFF | Prevent nutrient overshoot |

## Fail-Safe Summary (Updated)

| Component | Fail Condition | Physical State | Logical Recovery |
|-----------|----------------|----------------|------------------|
| NC Relays (P-301, P-302, C-401) | Power loss / controller crash | Remain ON | Controller reconciles & applies temp/flow logic on reboot |
| NO Relays (L-501, PP-201..204) | Power loss / controller crash | Remain OFF | Scheduler & dosing automation resume edges / learning |
| Dosing Pumps | Sensor stale (>120s) | OFF (blocked) | Fresh reading → unblock |
| Chiller System | Main pump OFF | Forced OFF (interlock) | Main pump restart → unblock |
| Automation | Mode = maintenance | Disabled | Mode → auto → re-enable |
| Database | Corruption | Use defaults, alert | Restore from backup |
| I²C Bus | Communication failure | Last good value + stale flag | Power-cycle sensors, wiring check |

---

**End of I/O & Signal List Document**
