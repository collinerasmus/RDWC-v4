# RDWC Operating Manual

**Document**: OM-001  
**System**: RDWC v4 Operating Procedures  
**Date**: 2025-11-23  
**Revision**: As-Built v1.0  

---

## Table of Contents
1. [Startup Sequence](#startup-sequence)
2. [Normal Operation](#normal-operation)
3. [Shutdown Sequence](#shutdown-sequence)
4. [Emergency Procedures](#emergency-procedures)
5. [Troubleshooting Guide](#troubleshooting-guide)
6. [Web UI Navigation](#web-ui-navigation)

---

## Startup Sequence

### Pre-Startup Checklist
- [ ] All electrical connections secure (no exposed terminals)
- [ ] GFCI outlets tested (press TEST button, verify trip)
- [ ] Reservoir filled to 100L mark with clean water
- [ ] All probes submerged in reservoir (pH, EC, RTD)
- [ ] pH probe stored in KCl solution overnight (if first use today)
- [ ] Main pump primed (no airlocks, hose clamps tight)
- [ ] Chiller loop primed (no airlocks)
- [ ] Dosing pump bottles filled (pH UP, micro, grow, bloom)
- [ ] No visible leaks around plumbing connections
- [ ] Raspberry Pi powered on, network connected (LED indicators lit)

### Step 1: Power On System
1. **Plug in GFCI power strip** → verify power indicator lit
2. **Wait 60 seconds** for Raspberry Pi boot
3. **Check network connectivity**:
   - SSH: `ssh pi@192.168.88.49` (or your Pi's IP)
   - Or open web browser: `http://192.168.88.49:8080`

### Step 2: Verify Services Running
```powershell
# Check API service status
ssh pi@192.168.88.49 "systemctl status rdwc.service"
# Should show: active (running)

# Check sensor poller status
ssh pi@192.168.88.49 "systemctl status rdwc-sensors.service"
# Should show: active (running)
```

**Expected Output**:
- `rdwc.service`: Active (running) since [boot time]
- `rdwc-sensors.service`: Active (running) since [boot time]

**If services not running**: See [Troubleshooting](#troubleshooting-guide)

### Step 3: Check Sensor Online Status
1. **Open web UI** → `http://192.168.88.49:8080`
2. **Navigate to Sensors tab**
3. **Verify all sensors online**:
   - Temperature: Green badge "Online", value 18-25°C
   - pH: Green badge "Online", value 5-8 pH
   - EC: Green badge "Online", value 0-3000 µS/cm
4. **Check timestamp**: Should be <60 seconds old (fresh data)

**If sensors offline**: See [Troubleshooting - Sensor Failures](#sensor-failures)

### Step 4: Verify Relay Status
1. **Navigate to System tab → Relay Control**
2. **Check E-STOP status**: Should be OFF (green badge)
3. **Check main pump**: Should be OFF initially (yellow badge)
4. **All other relays**: Should be OFF (yellow badges)

### Step 5: Start Main Pump
1. **Navigate to Circulation tab**
2. **Click "Start Main Pump" button**
3. **Verify pump running**: Listen for motor sound, check flow
4. **Check for leaks**: Inspect all hose connections, reservoir lid
5. **Confirm web UI**: Main pump badge should show ON (green)

**IMPORTANT**: Main pump should run continuously during normal operation. Only stop for maintenance.

### Step 6: Verify Calibration Status
#### pH Calibration Check
1. **Navigate to Calibration tab → pH section**
2. **Click "Read Status" button**
3. **Verify calibration**:
   - Calibrated: Yes
   - Points: 3 (or 2 minimum)
   - Slope: 95-105% (ideal 100%)

**If not calibrated**: Follow [Maintenance Manual - pH Calibration](#) procedure

#### EC Calibration Check
1. **Navigate to EC tab → Calibration section**
2. **Click "Status" button**
3. **Verify calibration**:
   - Low point: Accepted (1413 µS/cm)
   - K value: 1.0

**If not calibrated**: Follow [Maintenance Manual - EC Calibration](#) procedure

### Step 7: Verify Dosing Pump Calibration
1. **Navigate to Calibration tab → Dosing Pumps section**
2. **Click "Show Pumps" button**
3. **Verify all pumps have rates**:
   - pH UP: ~5 mL/s (or actual calibrated value)
   - Micro: ~5 mL/s
   - Grow: ~5 mL/s
   - Bloom: ~5 mL/s

**If rates are 0 or missing**: Follow [Maintenance Manual - Pump Calibration](#) procedure

### Step 8: Set Operating Modes
1. **Navigate to System tab → Controller Modes**
2. **Set each controller to desired mode**:
   - **pH**: Auto (for automatic pH control)
   - **EC**: Auto (for automatic nutrient dosing)
   - **Chiller**: Auto (for automatic temperature control)
   - **Lights**: Auto (for scheduled operation)
   - **Circulation**: Auto (for interlock protection)

**Note**: For first startup, consider Manual mode for pH/EC until you verify automation works correctly.

### Step 9: Adjust Setpoints (if needed)
1. **Navigate to System tab → Settings**
2. **Review and adjust targets**:
   - **pH**: Low 5.8, High 6.2 (or as needed for your crop)
   - **EC**: Low 800, High 1600 µS/cm (adjust per grow stage)
   - **Temperature**: Low 18°C, High 24°C
   - **Reservoir Volume**: 100L (critical for dose calculations)
3. **Click "Save All Changes" button**

### Step 10: Verify Lights Schedule
1. **Navigate to Schedule tab**
2. **Review current schedule**:
   - **Lights ON**: 06:00 (or as desired)
   - **Lights Duration**: 18 hours (vegetative) or 12 hours (flowering)
3. **Adjust if needed**, click "Update Schedule"

### Step 11: Monitor Initial Operation
- **Watch sensors for 10 minutes**:
  - Temperature should stabilize within ±0.5°C
  - pH should stabilize within ±0.1 pH
  - EC should stabilize within ±50 µS/cm
- **Check for anomalies**:
  - Rapid pH drift (may indicate probe issue or contamination)
  - EC drift (may indicate probe fouling)
  - Temperature spike (check chiller operation)

**Startup Complete**. System is now ready for normal operation.

---

## Normal Operation

### Daily Monitoring Tasks

#### Morning Routine (5 minutes)
1. **Check web UI** → Sensors tab
2. **Verify all sensors online**: Temperature, pH, EC all showing green "Online" badges
3. **Check sensor readings**:
   - Temperature: 18-24°C (optimal 20-22°C)
   - pH: 5.8-6.2 (or your target range)
   - EC: 800-1600 µS/cm (or your target range for current stage)
4. **Check main pump**: Should be running (green badge on Circulation tab)
5. **Review dose logs** (pH tab → Dose Log):
   - Check if any automatic doses occurred overnight
   - Verify dose volumes reasonable (<50 mL for pH, <200 mL for nutrients)
   - Look for anomalies (excessive dosing, failed doses)

#### Mid-Day Check (2 minutes)
1. **Quick sensor check**: All still online?
2. **Check for alarms**: Any red badges on tabs?
3. **Visual inspection**: Walk past system, listen for unusual pump noises, check for leaks

#### Evening Routine (5 minutes)
1. **Review day's dose summary**:
   - pH tab → "Today's Total" (should be <120s worth of dosing)
   - EC tab → "Today's Total" per pump (should be <300s each)
2. **Check lights schedule**: Did lights turn ON at correct time?
3. **Check chiller runtime**: Temperature tab → Chiller events (should be <12 hours/day)
4. **Plan for tomorrow**: Any setpoint adjustments needed?

### Weekly Tasks (30 minutes)

#### Sensor Maintenance
- **pH Probe Cleaning**:
  1. Remove probe from reservoir
  2. Rinse with distilled water
  3. Gently wipe with soft cloth (don't scratch glass bulb)
  4. Re-submerge in reservoir
  5. Wait 5 minutes, verify reading stable
- **EC Probe Cleaning**:
  1. Remove probe from reservoir
  2. Rinse with distilled water
  3. Use soft brush to clean electrode surfaces
  4. Re-submerge in reservoir
  5. Wait 5 minutes, verify reading stable

#### Nutrient Top-Off
- **Check reservoir level**: Should be 90-100L (mark on reservoir wall)
- **If <90L**:
  1. Prepare top-off solution (RO water + nutrients to match current EC)
  2. Add slowly while monitoring EC
  3. Let circulate for 30 minutes
  4. Re-check EC, adjust if needed

#### Visual Inspection
- [ ] Check all hose clamps (tight, no leaks)
- [ ] Inspect pump impellers (no debris, spinning freely)
- [ ] Check relay board (LEDs working, no burning smell)
- [ ] Inspect wiring (no fraying, connections secure)
- [ ] Check reservoir lid (light-proof seal intact)

### Monthly Tasks (1-2 hours)

#### Full Calibration Verification
- **pH**: Run 1-point verification with pH 7.0 buffer (should read 7.0 ±0.05)
- **EC**: Run 1-point verification with 1413 µS standard (should read 1413 ±30)
- **Temperature**: Compare RTD reading to known-good thermometer (should match ±0.5°C)
- **Dosing Pumps**: Measure actual flow rate, compare to calibrated rate (should match ±10%)

#### Database Maintenance
```powershell
# SSH to Raspberry Pi
ssh pi@192.168.88.49

# Stop services
sudo systemctl stop rdwc.service rdwc-sensors.service

# Backup database
cp /home/pi/RDWC-v4/data/rdwc.db /home/pi/RDWC-v4/data/rdwc.db.backup

# Vacuum database (reclaim space)
sqlite3 /home/pi/RDWC-v4/data/rdwc.db "VACUUM;"

# Analyze database (update statistics)
sqlite3 /home/pi/RDWC-v4/data/rdwc.db "ANALYZE;"

# Restart services
sudo systemctl start rdwc-sensors.service rdwc.service
```

#### System Update Check
```powershell
# Check for RDWC software updates
ssh pi@192.168.88.49 "cd /home/pi/RDWC-v4 && git fetch && git status"

# If updates available, follow deployment procedure (see Deployment Guide)
```

---

## Shutdown Sequence

### Temporary Shutdown (Maintenance)
1. **Set all controllers to Manual mode** (System tab → Controller Modes)
2. **Stop dosing automation** (modes already manual)
3. **Turn off lights manually** (Lights tab → OFF button) if not scheduled OFF
4. **Leave main pump running** (keeps solution mixed, prevents stratification)
5. **Perform maintenance tasks**
6. **Restart automation**: Set controllers back to Auto mode

### Extended Shutdown (>24 hours)
1. **Set all controllers to Manual mode**
2. **Turn off all relays**:
   - Lights: OFF
   - Chiller: OFF
   - Chiller Pump: OFF
   - Dosing Pumps: Already OFF (manual mode)
   - Main Pump: OFF (LAST)
3. **Store pH probe properly**:
   - Remove from reservoir
   - Rinse with distilled water
   - Submerge in KCl storage solution
   - Cap storage bottle
4. **Cover reservoir** (prevent evaporation, contamination)
5. **Leave Pi running** (unless powering down facility)

### Complete Power-Down
1. **Follow Extended Shutdown steps above**
2. **SSH to Pi**: `ssh pi@192.168.88.49`
3. **Stop services**:
   ```bash
   sudo systemctl stop rdwc.service rdwc-sensors.service
   ```
4. **Shutdown Pi**:
   ```bash
   sudo shutdown -h now
   ```
5. **Wait 30 seconds** for Pi to fully shut down (green LED stops flashing)
6. **Unplug power strip**

### Restart After Shutdown
1. **Follow [Startup Sequence](#startup-sequence)** from beginning
2. **Extra verification**:
   - Re-prime pumps if airlock occurred
   - Re-calibrate pH probe if stored in KCl >7 days
   - Check for leaks (hoses may have relaxed during shutdown)

---

## Emergency Procedures

### E-STOP Activation
**When to use**: Any dangerous condition requiring immediate shutdown of all systems.

**Examples**:
- Major leak detected
- Electrical hazard observed
- Pump overheating or smoking
- Chemical spill
- Need immediate access to reservoir/plumbing

**Procedure**:
1. **Click E-STOP button** (System tab → E-STOP section → Toggle button)
2. **Verify all relays OFF**: All badges on System tab should show yellow (OFF)
3. **Physically verify**: Listen for all pumps stopped, lights OFF
4. **Address the emergency**: Fix leak, clean spill, allow equipment to cool
5. **DO NOT RESET E-STOP** until emergency resolved and safe to resume

**E-STOP Reset**:
1. **Verify emergency resolved**
2. **Click E-STOP button again** to toggle OFF
3. **Manually restart main pump** (Circulation tab → Start Main Pump)
4. **Check for leaks** before restarting other systems
5. **Resume automation**: Set controllers back to Auto mode

### Power Loss Recovery
**Symptom**: Pi reboots, services restart automatically

**Auto-Recovery**:
- Pi will boot automatically when power restored
- Services start automatically (`systemd` handles this)
- Relay states NOT restored (fail-safe: all OFF on boot)

**Manual Recovery Steps**:
1. **Wait 2 minutes** for Pi to boot fully
2. **Open web UI**: `http://192.168.88.49:8080`
3. **Check sensor status**: Should come online within 1 minute
4. **Manually restart main pump**: Circulation tab → Start Main Pump
5. **Check for leaks**: Power loss may have caused water hammer or shifted hoses
6. **Resume automation**: Set controllers back to Auto mode (if they were auto before)

**Prevention**: Install UPS (Uninterruptible Power Supply) for Pi and main pump.

### Sensor Failure
**Symptom**: Sensor shows "Offline" (red badge) for >2 minutes

**Immediate Action**:
1. **Automation will freeze automatically** (sensor staleness guard triggers)
2. **Switch affected controller to Manual mode** (prevents dose attempts)
3. **Continue monitoring with working sensors** (e.g., if pH fails, watch EC and temp)

**Diagnosis**:
1. **Check I²C bus**: SSH and run `i2cdetect -y 1`
   - Should show devices at 0x66 (RTD), 0x63 (pH), 0x64 (EC)
   - If missing: check wiring, power, probe connection
2. **Check probe physically**: Is it submerged? BNC connector loose?
3. **Check power**: Are EZO boards lit (LED indicators)?

**Recovery**:
- If probe reconnected: Sensor should come online within 10 seconds
- If probe replaced: Recalibrate immediately
- If EZO board replaced: Recalibrate immediately

**Workaround** (temporary):
- Use portable pH/EC meter for manual monitoring
- Manually dose based on meter readings
- Schedule repair/replacement ASAP (don't run >24 hours without automation)

### Chemical Spill
**Symptom**: pH UP or nutrient solution spilled on floor/equipment

**Immediate Action**:
1. **Activate E-STOP** (if spill near electrical)
2. **Ventilate area** (open windows, turn on fans)
3. **Wear PPE**: Safety glasses, chemical gloves
4. **Contain spill**: Use absorbent pads, spill kit
5. **Neutralize pH UP**: Use vinegar or citric acid solution
6. **Clean with water**: Rinse area thoroughly
7. **Dispose properly**: Neutralized chemicals down drain (check local codes)

**Prevention**:
- Store chemical bottles in spill tray
- Use drip pans under dosing pumps
- Check tubing connections regularly

### Main Pump Failure
**Symptom**: Main pump won't start or stops running during operation

**Immediate Action**:
1. **Circulation interlock will prevent chiller operation** (automatic)
2. **Don't attempt to restart repeatedly** (may indicate hardware failure)

**Diagnosis**:
1. **Check power**: Is relay clicking? Is pump getting power?
2. **Check impeller**: Remove pump, inspect for debris/blockage
3. **Check wiring**: Continuity from relay to pump?
4. **Test relay**: Manually trigger via web UI, listen for click

**Workaround** (temporary):
- If <4 hours until repair: Leave reservoir undisturbed (minimal stratification)
- If >4 hours: Use backup pump (if available) or manually mix every 2 hours

**Long-term**: Replace pump, consider keeping spare pump on hand (critical component).

---

## Troubleshooting Guide

### Sensors Not Coming Online

**Symptom**: Sensor shows "Offline" or timestamp not updating

**Causes & Solutions**:
1. **I²C communication failure**:
   - Check: `ssh pi@192.168.88.49 "i2cdetect -y 1"`
   - Should show 0x63, 0x64, 0x66
   - If missing: Reseat cables, check power to EZO boards
   
2. **Sensor poller not running**:
   - Check: `ssh pi@192.168.88.49 "systemctl status rdwc-sensors.service"`
   - If not active: `sudo systemctl restart rdwc-sensors.service`
   
3. **Probe disconnected**:
   - Check BNC connectors (twist-lock tight)
   - Check probe submerged in solution

4. **EZO board firmware hung**:
   - Try power cycle: Navigate to System tab → Sensor Power Cycle (if available)
   - Or manually power-cycle Pi

### pH Reading Drifting Rapidly

**Symptom**: pH changes >0.5 in <1 hour without dosing

**Causes & Solutions**:
1. **Probe needs calibration**:
   - Check slope: Should be 95-105%
   - Recalibrate with fresh buffers
   
2. **Probe aging**:
   - Check response time (should reach stable value in <1 minute)
   - If slow response: Replace probe
   
3. **Actual pH is changing** (not a measurement issue):
   - Check EC (nutrients affect buffer capacity)
   - Check for contamination (algae, bacteria)
   - Check CO₂ exchange (is reservoir sealed?)

4. **Reference junction clogged**:
   - Soak probe in pH 4.0 buffer for 1 hour
   - Gently agitate to dislodge crystals

### EC Reading Erratic

**Symptom**: EC jumps around ±100 µS/cm, no stable reading

**Causes & Solutions**:
1. **Air bubbles on electrode**:
   - Remove probe, shake off bubbles
   - Reinstall, agitate water near probe
   
2. **Electrode fouled**:
   - Remove probe, clean with soft brush
   - Rinse with distilled water
   
3. **Temperature changing rapidly**:
   - EC is temperature-compensated, but rapid temp changes confuse algorithm
   - Improve temperature stability (chiller tuning)
   
4. **K value incorrect**:
   - Verify K=1.0 (standard for most applications)
   - If using different probe, recalibrate with correct K

### Relay Not Switching

**Symptom**: Click web UI button, relay doesn't change state

**Causes & Solutions**:
1. **Cooldown active**:
   - Check cooldown_remaining in relay status
   - Wait for cooldown to expire
   
2. **Interlock blocking**:
   - For chiller pump/chiller: Main pump must be running first
   - Start main pump, then retry
   
3. **E-STOP active**:
   - Check E-STOP status (System tab)
   - Toggle OFF if activated
   
4. **Mode preventing action**:
   - Manual mode required for manual control
   - Auto mode blocks manual buttons
   
5. **Relay board hardware failure**:
   - SSH and manually test GPIO: `gpio -g write 5 0` (turn on pH pump)
   - If relay doesn't click: Check wiring, replace relay board

### Dosing Not Occurring (Auto Mode)

**Symptom**: pH/EC out of range, but no automatic doses

**Causes & Solutions**:
1. **Sensor stale**:
   - Check sensor timestamp (<120s required)
   - Fix sensor communication first
   
2. **Daily cap exceeded**:
   - Check "Today's Total" on pH/EC tabs
   - pH: 120s max, EC: 300s max per pump
   - Wait until midnight for reset, or manually dose if urgent
   
3. **EC baseline guard (pH only)**:
   - pH dosing blocked if EC <500 µS
   - Add base nutrients first to raise EC
   
4. **Mode not Auto**:
   - Check controller mode (System tab)
   - Set to Auto
   
5. **Outside target range but within hysteresis**:
   - pH: Must be <ph_low or >ph_high (not just outside range)
   - EC: Must be <ec_low or >ec_high

### Web UI Not Loading

**Symptom**: Browser shows "Can't reach this page"

**Causes & Solutions**:
1. **Pi not on network**:
   - Ping: `ping 192.168.88.49`
   - Check ethernet cable, WiFi connection
   
2. **API service not running**:
   - SSH: `ssh pi@192.168.88.49`
   - Check: `systemctl status rdwc.service`
   - Restart: `sudo systemctl restart rdwc.service`
   
3. **Firewall blocking port 8080**:
   - Check: `sudo ufw status` (should be inactive or allow 8080)
   - Allow: `sudo ufw allow 8080/tcp`
   
4. **Wrong IP address**:
   - SSH to Pi, check IP: `hostname -I`
   - Update bookmarks with correct IP

---

## Web UI Navigation

### Sensors Tab
**Purpose**: Real-time sensor monitoring

**Key Elements**:
- **Online/Offline badges**: Green=online, red=offline
- **Sensor values**: Temperature (°C), pH, EC (µS/cm)
- **Timestamp**: How old is the reading? Should be <60s
- **Freshness indicator**: Green bar if fresh, red if stale (>120s)

**Actions**:
- Read Now (forces immediate sensor read, locks I²C bus briefly)
- View historical readings (charts, logs)

### pH Tab
**Purpose**: pH control and dosing

**Sections**:
- **Current pH**: Large display, target range shown
- **Auto Dosing**: Enable/disable, status display
- **Manual Dosing**: Buttons for manual pH UP dosing
- **Dose Log**: Today's doses, total volume/time
- **Auto-Learning**: View learned ml/pH ratios

**Actions**:
- Switch mode (Auto/Manual/Maintenance)
- Manual dose (10/20/30 mL buttons)
- View dose history
- Reset learner (clear learned data)

### EC Tab
**Purpose**: Nutrient control and dosing

**Sections**:
- **Current EC**: Large display, target range shown
- **Recipe**: ml/L per nutrient for current grow stage
- **Manual Dosing**: Buttons for each nutrient pump
- **Dose Log**: Today's doses per pump
- **Grow Stage**: Current day/stage progress

**Actions**:
- Switch mode (Auto/Manual/Maintenance)
- Manual dose (Micro/Grow/Bloom buttons)
- View dose history per pump

### Chiller Tab
**Purpose**: Temperature control and chiller status

**Sections**:
- **Current Temperature**: Large display, target range shown
- **Chiller Status**: Running/Stopped
- **Interlock Status**: Main pump running? Chiller allowed?
- **Chiller Events**: History of ON/OFF cycles

**Actions**:
- Switch mode (Auto/Manual/Maintenance)
- Manual control (Start/Stop chiller, chiller pump)
- View runtime statistics

### Circulation Tab
**Purpose**: Pump control and interlock monitoring

**Sections**:
- **Main Pump**: Status, manual control
- **Chiller Pump**: Status, interlock indicator
- **Interlock Explanation**: Why chiller pump can/can't run

**Actions**:
- Start/Stop main pump (CAUTION: only for maintenance)
- Start/Stop chiller pump (if interlock allows)

### Lights Tab
**Purpose**: Grow light control and scheduling

**Sections**:
- **Current Status**: ON/OFF, time until next edge
- **Schedule**: ON time, duration, current day/stage
- **Manual Override**: Buttons for manual ON/OFF

**Actions**:
- Switch mode (Auto/Manual/Maintenance)
- Manual override (requires whitelisted reason in backend)
- View schedule

### Schedule Tab
**Purpose**: Manage grow stage schedule and lights timing

**Sections**:
- **Timeline**: 12-week grow stages visualization
- **Current Day**: Progress bar, week number
- **Lights Schedule**: ON time, duration per stage
- **Nutrient Schedule**: Automatic recipe per stage

**Actions**:
- Update lights ON time and duration
- View grow stage definitions
- (Future: Edit stage transitions)

### Calibration Tab
**Purpose**: Sensor and pump calibration

**Sections**:
- **pH Calibration**: 3-point process (4.0/7.0/10.0 buffers)
- **EC Calibration**: 2-point process (dry/1413)
- **Dosing Pump Calibration**: Measure flow rate per pump

**Actions**:
- pH: Clear, read value, calibrate point
- EC: Clear, set K value, calibrate point, read status
- Pumps: Prime, run timed dose, measure volume, commit rate

### System Tab
**Purpose**: System-wide settings and status

**Sections**:
- **Controller Modes**: Auto/Manual/Maintenance per controller
- **Relay Control**: E-STOP, manual relay control
- **Settings**: Targets, reservoir volume, safety limits
- **System Info**: Pi hardware, software version, uptime

**Actions**:
- Set controller modes
- Toggle E-STOP
- Adjust setpoints
- View system diagnostics

---

## Best Practices

### Do's
✅ **Check sensors daily** (morning routine: 5 minutes)  
✅ **Keep pH probe in KCl solution** when not in use  
✅ **Clean EC probe weekly** (prevents fouling)  
✅ **Calibrate monthly** (pH verification with 7.0 buffer)  
✅ **Backup database monthly** (before vacuum/analyze)  
✅ **Keep spare pH probe** (most likely component to fail)  
✅ **Monitor dose logs** (detect anomalies early)  
✅ **Use GFCI outlets** (electrical safety near water)

### Don'ts
❌ **Don't let pH probe dry out** (destroys reference junction)  
❌ **Don't bypass circulation interlock** (unless maintenance mode for testing)  
❌ **Don't ignore staleness warnings** (sensor failures = frozen automation)  
❌ **Don't exceed daily dose caps** (120s pH, 300s nutrients)  
❌ **Don't power-cycle during dosing** (mid-dose power loss = unknown volume)  
❌ **Don't skip weekly cleaning** (fouled probes = inaccurate readings)  
❌ **Don't mix different nutrient brands** without research (chemical incompatibilities)

---

**End of Operating Manual**
