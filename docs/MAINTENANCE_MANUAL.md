# RDWC v4 Maintenance Manual

**Document**: MM-001  
**Project**: RDWC v4 Recirculating Deep Water Culture  
**Revision**: v1.0  
**Date**: 2025-11-23  

---

## Table of Contents

1. [Preventive Maintenance Schedule](#preventive-maintenance-schedule)
2. [Calibration Procedures](#calibration-procedures)
3. [Sensor Cleaning & Maintenance](#sensor-cleaning--maintenance)
4. [Database Maintenance](#database-maintenance)
5. [Software Updates](#software-updates)
6. [Hardware Inspection](#hardware-inspection)
7. [Troubleshooting Guide](#troubleshooting-guide)
8. [Spare Parts & Consumables](#spare-parts--consumables)

---

## Preventive Maintenance Schedule

### Daily Tasks (5 minutes)
**Frequency**: Every day  
**Responsible**: Primary operator

- [ ] **Visual Inspection**: Check reservoir for leaks, algae, or debris
- [ ] **Sensor Check**: Verify all sensors online via Sensors tab (green status)
- [ ] **Reading Sanity**: Confirm pH 5.5-6.5, EC 400-1800 µS/cm, Temp 18-24°C
- [ ] **Pump Listen Test**: Verify main pump and chiller pump running smoothly (no grinding/rattling)
- [ ] **Water Level**: Check reservoir level (should be at reference mark)
- [ ] **Lights Operation**: Confirm lights follow schedule (ON during light hours, OFF during dark)
- [ ] **Dose Log Review**: Check pH/EC dose logs for excessive dosing (warning sign of drift)

**Action if Failed**: Refer to Operating Manual emergency procedures or Troubleshooting Guide below.

---

### Weekly Tasks (30 minutes)
**Frequency**: Every 7 days  
**Responsible**: Primary operator

- [ ] **Sensor Cleaning**: Clean pH probe, EC cell, and RTD probe (see Section 3)
- [ ] **Reservoir Top-Off**: Add fresh water to maintain level (may require nutrient adjustment)
- [ ] **Nutrient Top-Off**: Add nutrients per grow schedule if EC drifting low
- [ ] **Calibration Check**: Verify pH calibration flags (pH tab should show green "CAL OK")
- [ ] **System Backup**: Export settings JSON via System tab → Export JSON button
- [ ] **Database Size Check**: Monitor DB size in System tab (should be <100 MB for typical 3-month grow)
- [ ] **Relay Test**: Manually toggle each relay via System tab → Relays section (verify physical actuation)
- [ ] **Cooldown Verification**: Check System tab for any unexpected cooldowns (may indicate hardware issue)

**Action if Failed**: Document issue in Ops Runbook, escalate to secondary operator if unresolved.

---

### Monthly Tasks (1-2 hours)
**Frequency**: Every 30 days  
**Responsible**: Primary operator + technical support

- [ ] **Full Calibration**: pH 3-point calibration (see Section 2.1)
- [ ] **EC Calibration Verification**: EC 2-point calibration if reading drift detected (see Section 2.2)
- [ ] **Dosing Pump Calibration Check**: Verify pump flow rates via Calibration tab → Dosing Pumps (see Section 2.3)
- [ ] **Database Maintenance**: Run VACUUM and ANALYZE (see Section 4)
- [ ] **Database Backup**: Export full SQLite DB to external storage (see Section 4.3)
- [ ] **Software Update**: Check for RDWC updates via Git (see Section 5)
- [ ] **Log Review**: Inspect systemd logs for rdwc-api and rdwc-sensors services (see Section 5.4)
- [ ] **Hardware Inspection**: Inspect relay board, power supply, GPIO connections (see Section 6)
- [ ] **Reservoir Deep Clean**: Drain, scrub, sanitize, refill (coordinate with grow schedule)

**Action if Failed**: Log in maintenance record, schedule repair if hardware issue detected.

---

### Quarterly Tasks (2-3 hours)
**Frequency**: Every 90 days  
**Responsible**: Technical team

- [ ] **pH Probe Replacement**: Replace pH probe if age >12 months or calibration unstable
- [ ] **EC Cell Inspection**: Inspect EC cell for fouling, replace if cleaning ineffective
- [ ] **Relay Endurance Test**: Cycle each relay 20 times, verify no sticking or failure
- [ ] **Pump Maintenance**: Inspect main pump and chiller pump impellers, clean if needed
- [ ] **Cooling System Check**: Inspect chiller coils, clean if dust accumulation present
- [ ] **Network Security Audit**: Review firewall rules, update Pi OS packages (see Section 5.2)
- [ ] **Documentation Review**: Update Operating Manual and Maintenance Manual with lessons learned

**Action if Failed**: Replace failed component, document in asset management system.

### Mixed NC / NO Relay Wiring (Added 2025-11-23)
The system now uses a mixed fail-safe strategy.

| Relay | Tag | Wiring | Fail (Power / Controller Loss) | Expected Physical State | Monthly Check |
|-------|-----|--------|--------------------------------|-------------------------|---------------|
| Main circulation pump | P-301 | NC | Controller/Pi down | Pump running | Toggle via API; verify resume |
| Chiller circulation pump | P-302 | NC | Controller/Pi down | Pump running | Ensure flow; log test |
| Water chiller | C-401 | NC | Controller/Pi down | Chiller ON (if previously ON) | Confirm coolant temp stable |
| Grow lights | L-501 | NO | Controller/Pi down | Lights OFF | Verify schedule resumes after boot |
| pH UP pump | PP-201 | NO | Controller/Pi down | Pump OFF | Check no unintended dosing |
| Micro pump | PP-202 | NO | Controller/Pi down | Pump OFF | Check reservoir EC stability |
| Grow pump | PP-203 | NO | Controller/Pi down | Pump OFF | Same as Micro |
| Bloom pump | PP-204 | NO | Controller/Pi down | Pump OFF | Same as Micro |

Inspection Notes:
1. NC channels reduce coil energized time compared to former NO configuration, lowering thermal wear.
2. After any unplanned reboot: verify pumps & chiller still running, then confirm controller logic reasserts correct states within one cycle.
3. Use relay guard anomalies endpoint to detect mismatch after startup.
4. Document results in maintenance log with timestamp and operator initials.

Annual Functional Test:
- Power down controller (graceful stop of services), observe NC assets remain ON.
- Manually disconnect relay board power briefly; confirm NC contacts close and devices resume.
- Restore services; verify lights and dosing remain OFF until automation resumes.

---

## Calibration Procedures

### 2.1 pH Sensor 3-Point Calibration

**Frequency**: Monthly or if drift detected  
**Duration**: 15-20 minutes  
**Required Buffers**: pH 4.0, 7.0, 10.0 (Atlas Scientific or equivalent)  
**Prerequisites**: 
- Set `CALIB_ENABLE=1` in environment variables (`.env` file)
- Restart API service: `sudo systemctl restart rdwc-api`

**Procedure**:

1. **Prepare Buffers**:
   - Ensure buffers are fresh (<6 months old, unopened)
   - Bring buffers to room temperature (20-25°C)
   - Pour ~50ml of each buffer into separate clean containers

2. **Access Calibration Tab**:
   - Navigate to web UI → Calibration tab
   - Verify pH section shows "Calibration: ENABLED"

3. **Mid-Point Calibration (pH 7.0)**:
   - Remove pH probe from reservoir
   - Rinse probe with distilled water, blot dry with lint-free tissue
   - Immerse probe in pH 7.0 buffer (ensure junction is submerged)
   - Wait 30 seconds for temperature equilibration
   - Click "Read Stable" button in Calibration tab → pH section
   - Wait for reading to stabilize (green checkmark appears, ~60-90 seconds)
   - Click "Calibrate Mid (7.0)" button
   - System will respond: "Mid calibration success" or error message
   - **Acceptance**: Mid flag should turn GREEN in Calibration tab

4. **Low-Point Calibration (pH 4.0)**:
   - Rinse probe thoroughly with distilled water
   - Immerse probe in pH 4.0 buffer
   - Wait 30 seconds for equilibration
   - Click "Read Stable" button
   - Wait for stabilization (green checkmark)
   - Click "Calibrate Low (4.0)" button
   - **Acceptance**: Low flag should turn GREEN

5. **High-Point Calibration (pH 10.0)**:
   - Rinse probe thoroughly with distilled water
   - Immerse probe in pH 10.0 buffer
   - Wait 30 seconds for equilibration
   - Click "Read Stable" button
   - Wait for stabilization (green checkmark)
   - Click "Calibrate High (10.0)" button
   - **Acceptance**: High flag should turn GREEN

6. **Verification**:
   - Rinse probe and return to reservoir
   - Navigate to pH tab
   - Verify current pH reading is within expected range (5.5-6.5 for typical grow)
   - Check Calibration tab: All three flags (Mid, Low, High) should be GREEN

7. **Post-Calibration**:
   - Record calibration date in Ops Runbook
   - Set `CALIB_ENABLE=0` in `.env` file (security measure)
   - Restart API service: `sudo systemctl restart rdwc-api`

**Troubleshooting**:
- **Unstable reading**: Buffer contaminated or probe aging → Use fresh buffer or replace probe
- **Calibration rejected**: Probe out of range → Clean probe thoroughly, try again
- **Calibration timeout**: Sensor poller contention → Stop poller temporarily: `sudo systemctl stop rdwc-sensors`

---

### 2.2 EC Sensor 2-Point Calibration

**Frequency**: Quarterly or if drift detected  
**Duration**: 10-15 minutes  
**Required Solutions**: Dry calibration (factory default) OR 1413 µS/cm solution  
**Prerequisites**: EC sensor online, system in Manual mode recommended

**Procedure**:

1. **Dry Calibration (Factory Reset)**:
   - Remove EC probe from reservoir
   - Rinse with distilled water, shake dry thoroughly
   - Ensure probe is completely dry (air dry 5 minutes)
   - Navigate to EC tab in web UI
   - Click "Clear EC Cal" button
   - System will respond: "EC calibration cleared"
   - Click "Set K Value" button, enter `1.0` (factory default)
   - **Acceptance**: EC tab shows "K=1.0"

2. **Low-Point Calibration (1413 µS/cm)**:
   - Pour ~50ml of 1413 µS/cm calibration solution into clean container
   - Immerse EC probe fully (both pins submerged)
   - Wait 30 seconds for equilibration
   - Navigate to EC tab → scroll to Calibration section
   - Click "Cal Low (1413)" button
   - System will respond: "Low calibration success" or error
   - **Acceptance**: EC status should show "low" flag accepted

3. **High-Point Calibration (12,880 µS/cm)** (Optional):
   - Only required if measuring >10,000 µS/cm (not typical for RDWC)
   - Follow same procedure with 12,880 µS/cm solution
   - Click "Cal High (12880)" button

4. **Verification**:
   - Rinse probe thoroughly with distilled water
   - Return probe to reservoir
   - Navigate to EC tab
   - Verify current EC reading is within expected range (400-1800 µS/cm for grow)
   - Check EC tab: "low" flag should be present in status

5. **Post-Calibration**:
   - Record calibration date in Ops Runbook
   - No service restart required (calibration persists in EZO firmware)

**Troubleshooting**:
- **EC reading erratic**: Air bubbles on pins → Gently shake probe or tap to dislodge
- **Calibration rejected**: Solution contaminated → Use fresh calibration solution
- **K value reset**: Firmware reset occurred → Recalibrate from dry cal

---

### 2.3 Dosing Pump Calibration

**Frequency**: Monthly or if dose accuracy drifts  
**Duration**: 20-30 minutes  
**Required Materials**: Graduated cylinder (50ml or 100ml), water, timer  
**Prerequisites**: Pumps primed, system in Manual mode

**Procedure**:

1. **Access Calibration Tab**:
   - Navigate to web UI → Calibration tab
   - Scroll to "Dosing Pumps" section

2. **Prime Pumps** (if needed):
   - Click "Prime pH UP" button (runs pump for 10 seconds)
   - Repeat for "Prime Micro", "Prime Grow", "Prime Bloom"
   - Ensure pump tubing is filled with fluid (no air bubbles)

3. **Calibration Run**:
   - For **each pump** (pH UP, Micro, Grow, Bloom):
     - Place pump output tube into graduated cylinder
     - Click "Run [Pump] for 30s" button
     - System will run pump for exactly 30 seconds
     - Measure volume dispensed in graduated cylinder (record ml)

4. **Commit Calibration**:
   - For **each pump**, enter measured volume (ml) in corresponding "Dispensed (ml)" field
   - Example: pH UP dispensed 45ml in 30s → Enter `45` in "pH UP Dispensed" field
   - Click "Commit [Pump] Cal" button
   - System calculates and stores flow rate (ml/s)
   - **Acceptance**: Pump card should display rate in ml/s (e.g., "1.5 ml/s")

5. **Verification**:
   - Navigate to Calibration tab → Dosing Pumps section
   - Verify all pumps show flow rate >0 ml/s
   - Typical rates: 1.0-2.0 ml/s for peristaltic pumps

6. **Safety Caps Verification**:
   - System will display safety caps below pump controls:
     - **pH UP**: Max per press 60s, Daily cap 120s
     - **Nutrients (Micro/Grow/Bloom)**: Max per press 120s each, Daily cap 300s total
   - Verify caps are displayed correctly

7. **Post-Calibration**:
   - Return pump output tubes to reservoir
   - Record calibration date and flow rates in Ops Runbook
   - Test manual dose: Navigate to pH tab, click "+1 ml" button, verify ~1ml dispensed

**Troubleshooting**:
- **Flow rate = 0**: Pump not primed or tube kinked → Re-prime, check tubing
- **Flow rate too low (<0.5 ml/s)**: Tube constriction or pump aging → Inspect tubing, replace pump
- **Inconsistent flow**: Air bubbles in line → Re-prime thoroughly

---

## Sensor Cleaning & Maintenance

### 3.1 pH Probe Cleaning

**Frequency**: Weekly or if reading drifts  
**Duration**: 5-10 minutes  
**Materials**: Soft brush, distilled water, pH storage solution (KCl 3M)

**Procedure**:

1. **Remove Probe**:
   - Navigate to System tab → Relays section
   - Click "Main Pump OFF" (stop circulation to access probe safely)
   - Remove pH probe from reservoir

2. **Rinse**:
   - Rinse probe with distilled water to remove nutrient residue
   - Inspect glass bulb for cracks or discoloration (replace if damaged)

3. **Clean Junction**:
   - Gently scrub reference junction (white ceramic frit near bulb) with soft brush
   - Rinse again with distilled water
   - **Caution**: Do NOT scrub glass bulb (very fragile)

4. **Soaking** (if fouled):
   - Prepare cleaning solution: 1:10 bleach:water OR pH probe cleaning solution
   - Soak probe for 5 minutes (no longer than 10 minutes)
   - Rinse thoroughly with distilled water

5. **Storage Solution Refresh**:
   - Remove old storage solution from probe cap
   - Add fresh KCl 3M storage solution to cap
   - Reattach cap to probe tip (ensures hydration between uses)

6. **Reinstall**:
   - Return probe to reservoir (ensure junction is submerged)
   - Turn main pump back ON via System tab
   - Wait 5 minutes for reading to stabilize

7. **Verification**:
   - Navigate to Sensors tab
   - Verify pH reading is stable and within expected range
   - If reading still drifts, perform 3-point calibration (Section 2.1)

**Maintenance Notes**:
- **Probe Lifespan**: 12-24 months typical, 6-12 months in harsh conditions
- **Hydration**: Never let probe dry out (glass bulb must stay hydrated)
- **Storage**: When not in use, store in KCl solution (not distilled water)

---

### 3.2 EC Probe Cleaning

**Frequency**: Weekly or if reading erratic  
**Duration**: 5 minutes  
**Materials**: Soft brush, distilled water, white vinegar (optional)

**Procedure**:

1. **Remove Probe**:
   - Stop main pump via System tab
   - Remove EC probe from reservoir

2. **Visual Inspection**:
   - Inspect four pins (electrodes) for fouling or corrosion
   - Buildup appears as white/brown deposits on pins

3. **Clean Pins**:
   - Gently scrub pins with soft brush under running distilled water
   - For stubborn deposits: Soak in white vinegar for 5 minutes, then scrub

4. **Rinse**:
   - Rinse thoroughly with distilled water
   - Shake probe to remove trapped water between pins

5. **Reinstall**:
   - Return probe to reservoir (ensure all four pins submerged)
   - Turn main pump back ON
   - Wait 2 minutes for reading to stabilize

6. **Verification**:
   - Navigate to Sensors tab
   - Verify EC reading is stable and within expected range (400-1800 µS/cm)
   - If reading still erratic, perform 2-point calibration (Section 2.2)

**Maintenance Notes**:
- **Probe Lifespan**: 2-5 years typical
- **Air Bubbles**: Trapped air between pins causes erratic readings → Tap probe or shake gently
- **Storage**: Can be stored dry (unlike pH probe)

---

### 3.3 RTD Temperature Probe Cleaning

**Frequency**: Monthly or if reading drifts  
**Duration**: 3 minutes  
**Materials**: Soft cloth, distilled water

**Procedure**:

1. **Remove Probe**:
   - Stop main pump via System tab
   - Remove RTD probe from reservoir

2. **Visual Inspection**:
   - Inspect probe tip (stainless steel cylinder) for fouling
   - Buildup appears as algae, mineral deposits, or biofilm

3. **Clean**:
   - Wipe probe tip with soft cloth dampened with distilled water
   - For stubborn deposits: Soak in white vinegar for 5 minutes, then wipe

4. **Rinse**:
   - Rinse thoroughly with distilled water

5. **Reinstall**:
   - Return probe to reservoir (ensure tip is submerged)
   - Turn main pump back ON
   - Wait 1 minute for reading to stabilize

6. **Verification**:
   - Navigate to Sensors tab
   - Verify temperature reading is stable and accurate (~20-24°C for typical reservoir)
   - **Note**: RTD probes rarely require calibration (factory-calibrated, very stable)

**Maintenance Notes**:
- **Probe Lifespan**: 10+ years typical (very robust)
- **Accuracy**: ±0.1°C typical, ±0.5°C max drift over lifetime
- **No Calibration**: RTD calibration requires specialized equipment (not user-serviceable)

---

## Database Maintenance

### 4.1 Database Size Monitoring

**Frequency**: Monthly  
**Tool**: System tab → Database card

**Procedure**:

1. **Check DB Size**:
   - Navigate to System tab
   - Locate "Database" card
   - Read "DB Size" KPI (typical: 10-50 MB for 1-3 month grow)

2. **Thresholds**:
   - **<100 MB**: Normal, no action required
   - **100-500 MB**: High but acceptable, schedule VACUUM
   - **>500 MB**: Excessive, investigate (may have runaway logging)

3. **Record Counts**:
   - Check "Readings", "pH Doses", "EC Doses" KPIs
   - Typical: 250,000-500,000 readings for 3-month grow (10s polling interval)

4. **Action if Oversized**:
   - Perform VACUUM (Section 4.2)
   - Consider pruning old readings (Section 4.4)

---

### 4.2 Database VACUUM & ANALYZE

**Frequency**: Monthly  
**Duration**: 2-5 minutes  
**Tool**: SSH + sqlite3 command-line

**Procedure**:

1. **SSH to Raspberry Pi**:
   ```powershell
   ssh pi@192.168.88.49
   ```

2. **Stop Services** (prevents database locks):
   ```bash
   sudo systemctl stop rdwc-api
   sudo systemctl stop rdwc-sensors
   ```

3. **Run VACUUM**:
   ```bash
   cd /home/pi/rdwc-v4
   sqlite3 data/rdwc.db "VACUUM;"
   ```
   - **Purpose**: Reclaims space from deleted records, defragments database
   - **Duration**: 30-120 seconds depending on DB size

4. **Run ANALYZE**:
   ```bash
   sqlite3 data/rdwc.db "ANALYZE;"
   ```
   - **Purpose**: Updates query planner statistics for optimal performance
   - **Duration**: 5-15 seconds

5. **Restart Services**:
   ```bash
   sudo systemctl start rdwc-sensors
   sudo systemctl start rdwc-api
   ```

6. **Verification**:
   - Navigate to System tab in web UI
   - Verify "DB Size" has decreased (typical: 10-30% reduction)
   - Check logs: `sudo journalctl -u rdwc-api -f` (should show no errors)

**Troubleshooting**:
- **VACUUM fails**: Database locked → Ensure both services stopped
- **DB size unchanged**: No fragmentation present (normal if no deletions occurred)

---

### 4.3 Database Backup

**Frequency**: Monthly + before major software updates  
**Duration**: 1-2 minutes  
**Tool**: SSH + cp command OR Settings export

**Method 1: Full Database Backup (Recommended)**

1. **SSH to Raspberry Pi**:
   ```powershell
   ssh pi@192.168.88.49
   ```

2. **Stop Services**:
   ```bash
   sudo systemctl stop rdwc-api
   sudo systemctl stop rdwc-sensors
   ```

3. **Copy Database**:
   ```bash
   cd /home/pi/rdwc-v4
   cp data/rdwc.db data/rdwc_backup_$(date +%Y%m%d).db
   ```

4. **Transfer to PC** (from Windows PowerShell):
   ```powershell
   scp pi@192.168.88.49:/home/pi/rdwc-v4/data/rdwc_backup_*.db C:\Backups\RDWC\
   ```

5. **Restart Services**:
   ```bash
   sudo systemctl start rdwc-sensors
   sudo systemctl start rdwc-api
   ```

**Method 2: Settings Export (Quick, Settings Only)**

1. Navigate to System tab in web UI
2. Click "Export JSON" button
3. Save `rdwc_settings_YYYYMMDD_HHMMSS.json` to PC
4. **Note**: Only exports `settings` table, not full database (no readings/logs)

**Backup Retention**:
- **Daily**: Keep last 7 days (automated via cron if desired)
- **Weekly**: Keep last 4 weeks
- **Monthly**: Keep last 12 months

---

### 4.4 Database Pruning (Optional)

**Frequency**: As needed (database >500 MB)  
**Duration**: 5-10 minutes  
**Caution**: Deletes historical data permanently

**Procedure**:

1. **Stop Services**:
   ```bash
   sudo systemctl stop rdwc-api
   sudo systemctl stop rdwc-sensors
   ```

2. **Prune Old Readings** (keep last 90 days):
   ```bash
   cd /home/pi/rdwc-v4
   sqlite3 data/rdwc.db "DELETE FROM readings WHERE ts < unixepoch('now', '-90 days');"
   ```

3. **Prune Old Dose Logs** (keep last 60 days):
   ```bash
   sqlite3 data/rdwc.db "DELETE FROM ph_dose_log WHERE ts < unixepoch('now', '-60 days');"
   sqlite3 data/rdwc.db "DELETE FROM ec_dose_log WHERE ts < unixepoch('now', '-60 days');"
   sqlite3 data/rdwc.db "DELETE FROM dose_events WHERE ts < unixepoch('now', '-60 days');"
   ```

4. **Run VACUUM** (reclaim space):
   ```bash
   sqlite3 data/rdwc.db "VACUUM;"
   ```

5. **Restart Services**:
   ```bash
   sudo systemctl start rdwc-sensors
   sudo systemctl start rdwc-api
   ```

6. **Verification**:
   - Check System tab → Database card
   - Verify "Oldest Reading" date is now ~90 days ago
   - Verify "DB Size" has decreased significantly

**Recommendation**: Export full backup before pruning (Section 4.3).

---

## Software Updates

### 5.1 Checking for Updates

**Frequency**: Monthly  
**Duration**: 2 minutes  
**Tool**: SSH + Git

**Procedure**:

1. **SSH to Raspberry Pi**:
   ```powershell
   ssh pi@192.168.88.49
   ```

2. **Navigate to Project Directory**:
   ```bash
   cd /home/pi/rdwc-v4
   ```

3. **Fetch Latest Changes**:
   ```bash
   git fetch origin main
   ```

4. **Check for New Commits**:
   ```bash
   git log HEAD..origin/main --oneline
   ```
   - If output is empty: No updates available
   - If output shows commits: Updates available

5. **Review Changes** (if updates available):
   ```bash
   git log HEAD..origin/main --stat
   ```
   - Review commit messages and changed files
   - Assess risk (minor tweaks vs major refactor)

**Decision**:
- **No updates**: Exit, no action required
- **Updates available**: Proceed to Section 5.2 (Apply Updates)

---

### 5.2 Applying Software Updates

**Frequency**: As needed (after checking for updates)  
**Duration**: 5-10 minutes  
**Prerequisites**: Database backup (Section 4.3)

**Procedure**:

1. **Backup Current State**:
   - Perform database backup (Section 4.3 Method 1)
   - Export settings JSON (System tab → Export JSON)

2. **SSH to Raspberry Pi**:
   ```powershell
   ssh pi@192.168.88.49
   ```

3. **Stop Services**:
   ```bash
   sudo systemctl stop rdwc-api
   sudo systemctl stop rdwc-sensors
   ```

4. **Stash Local Changes** (if any):
   ```bash
   cd /home/pi/rdwc-v4
   git stash
   ```

5. **Pull Updates**:
   ```bash
   git pull origin main
   ```
   - If merge conflicts: Abort and contact technical support
     ```bash
     git merge --abort
     git stash pop  # Restore local changes
     ```

6. **Update Python Dependencies** (if requirements.txt changed):
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt --upgrade
   ```

7. **Run Database Migrations** (if migrations/ folder changed):
   ```bash
   python migrations/apply_all.py
   ```

8. **Restart Services**:
   ```bash
   sudo systemctl start rdwc-sensors
   sudo systemctl start rdwc-api
   ```

9. **Verification**:
   - Navigate to web UI (http://192.168.88.49:8080)
   - Check System tab → Software card → "RDWC Version"
   - Verify version number updated
   - Test critical paths: Sensors tab (readings), pH tab (manual dose), System tab (relay control)

10. **Post-Update**:
    - Monitor logs for errors: `sudo journalctl -u rdwc-api -f`
    - Document update in Ops Runbook (version, date, any issues)

**Rollback Procedure** (if update fails):

1. **Stop Services**:
   ```bash
   sudo systemctl stop rdwc-api
   sudo systemctl stop rdwc-sensors
   ```

2. **Revert Git Changes**:
   ```bash
   cd /home/pi/rdwc-v4
   git reset --hard HEAD@{1}  # Rollback to previous commit
   ```

3. **Restore Database Backup** (if migrations ran):
   ```bash
   cp data/rdwc_backup_YYYYMMDD.db data/rdwc.db
   ```

4. **Restart Services**:
   ```bash
   sudo systemctl start rdwc-sensors
   sudo systemctl start rdwc-api
   ```

5. **Verification**:
   - Verify web UI loads
   - Check version number reverted
   - Contact technical support for troubleshooting

---

### 5.3 Raspberry Pi OS Updates

**Frequency**: Quarterly  
**Duration**: 10-20 minutes  
**Caution**: May require system restart

**Procedure**:

1. **SSH to Raspberry Pi**:
   ```powershell
   ssh pi@192.168.88.49
   ```

2. **Update Package Lists**:
   ```bash
   sudo apt update
   ```

3. **Upgrade Packages**:
   ```bash
   sudo apt upgrade -y
   ```
   - **Duration**: 5-15 minutes depending on updates available
   - **Note**: Will update system libraries, Python, etc.

4. **Check for Kernel Updates**:
   ```bash
   sudo apt full-upgrade -y
   ```
   - **Caution**: May update kernel, requires reboot

5. **Clean Old Packages**:
   ```bash
   sudo apt autoremove -y
   sudo apt clean
   ```

6. **Reboot** (if kernel updated):
   ```bash
   sudo reboot
   ```
   - **Wait**: 2-3 minutes for Pi to restart

7. **Verification**:
   - SSH back in after reboot
   - Verify services started: `sudo systemctl status rdwc-api rdwc-sensors`
   - Navigate to web UI, verify functionality

**Troubleshooting**:
- **Services fail to start after update**: Check logs (`sudo journalctl -u rdwc-api -n 50`)
- **Python version mismatch**: Recreate virtual environment:
  ```bash
  cd /home/pi/rdwc-v4
  python3 -m venv venv --clear
  source venv/bin/activate
  pip install -r requirements.txt
  ```

---

### 5.4 Log Review & Rotation

**Frequency**: Monthly  
**Duration**: 10 minutes  
**Tool**: journalctl + logrotate

**Procedure**:

1. **Review API Service Logs**:
   ```bash
   sudo journalctl -u rdwc-api --since "1 week ago" | grep -i error
   ```
   - Look for: HTTP 500 errors, database locks, I²C failures

2. **Review Sensor Poller Logs**:
   ```bash
   sudo journalctl -u rdwc-sensors --since "1 week ago" | grep -i error
   ```
   - Look for: I²C timeouts, sensor offline, calibration lock contention

3. **Check Log Disk Usage**:
   ```bash
   sudo journalctl --disk-usage
   ```
   - **Threshold**: >500 MB indicates retention too long

4. **Rotate Logs** (if excessive):
   ```bash
   sudo journalctl --vacuum-time=30d  # Keep last 30 days only
   ```

5. **Persistent Logging Configuration** (if not already set):
   ```bash
   sudo nano /etc/systemd/journald.conf
   ```
   - Set: `SystemMaxUse=200M` (limits journal to 200 MB)
   - Restart journald: `sudo systemctl restart systemd-journald`

**Common Errors to Investigate**:
- **I²C bus timeout**: Sensor wiring issue or EZO firmware lockup
- **Database locked**: Concurrent access during backup (normal if brief)
- **Relay state mismatch**: GPIO issue or relay guard anomaly
- **HTTP 500**: Python exception in API endpoint (requires code fix)

---

## Hardware Inspection

### 6.1 Relay Board Inspection

**Frequency**: Monthly  
**Duration**: 5 minutes  
**Safety**: Power OFF relays before inspection (E-STOP active)

**Procedure**:

1. **Activate E-STOP**:
   - Navigate to web UI
   - Click "E-STOP" button (turns red, all relays OFF)

2. **Visual Inspection**:
   - Inspect relay board for:
     - Burn marks (indicates overload)
     - Loose connections (terminal blocks)
     - Corrosion on terminals (moisture ingress)
     - LED indicators (should be OFF when relay OFF, ON when relay ON)

3. **Relay Actuation Test**:
   - Deactivate E-STOP
   - Navigate to System tab → Relays section
   - Toggle each relay ON/OFF individually
   - Listen for distinct "click" sound (indicates mechanical actuation)
   - **Failure**: No click = stuck relay → Replace relay module

4. **Load Test** (optional):
   - With relay ON, measure voltage across load terminals
   - Should read ~120V AC (for AC loads) or ~12V DC (for DC loads)
   - **Caution**: Use multimeter, observe electrical safety

5. **Document Findings**:
   - Record any anomalies in Ops Runbook
   - Schedule replacement if relay fails actuation test

---

### 6.2 Power Supply Inspection

**Frequency**: Quarterly  
**Duration**: 3 minutes  
**Safety**: Do NOT open power supply (shock hazard)

**Procedure**:

1. **Visual Inspection**:
   - Inspect power supply for:
     - Overheating (touch case, should be warm not hot)
     - Fan operation (if equipped, should spin quietly)
     - Burn smell (indicates component failure)

2. **Voltage Check**:
   - Use multimeter to measure output voltage
   - **5V Rail** (Raspberry Pi): 5.0V ±0.25V
   - **12V Rail** (relays, if applicable): 12.0V ±0.5V

3. **Ripple Check** (advanced):
   - Use oscilloscope to measure AC ripple on DC output
   - **Threshold**: <100mV peak-to-peak ripple (typical for switching PSU)

4. **Action if Failed**:
   - Replace power supply immediately (undervoltage causes Pi instability)

---

### 6.3 GPIO Connection Inspection

**Frequency**: Quarterly  
**Duration**: 5 minutes  
**Safety**: E-STOP active, no power to GPIO

**Procedure**:

1. **Activate E-STOP** (all GPIO outputs LOW/OFF)

2. **Visual Inspection**:
   - Inspect GPIO header on Raspberry Pi
   - Check for:
     - Bent pins (causes intermittent connection)
     - Loose jumper wires (jiggle gently to test)
     - Corrosion on pin headers (green/white oxidation)

3. **Continuity Test** (with multimeter):
   - Set multimeter to continuity mode (beep)
   - Test each GPIO pin to relay board input
   - **Expected**: Beep indicates good connection

4. **Insulation Check**:
   - Verify no exposed wire touching metal chassis (short circuit risk)
   - Use electrical tape or heat shrink to insulate any exposed connections

5. **Cable Management**:
   - Secure cables with zip ties or cable clips
   - Ensure no cables near moving parts (fans, pumps)

---

## Troubleshooting Guide

### 7.1 Sensor Not Online

**Symptom**: Sensors tab shows "Offline" status for pH, EC, or RTD  
**Diagnosis**:

1. **Check I²C Bus**:
   ```bash
   sudo i2cdetect -y 1
   ```
   - **Expected**: 0x63 (pH), 0x64 (EC), 0x66 (RTD) appear in grid
   - **Failure**: Missing address → Sensor disconnected or powered off

2. **Check Sensor Poller Service**:
   ```bash
   sudo systemctl status rdwc-sensors
   ```
   - **Expected**: "active (running)" status
   - **Failure**: "inactive (dead)" → Restart service: `sudo systemctl start rdwc-sensors`

3. **Check Sensor Power**:
   - If `RDWC_SENSOR_POWER_PIN` configured (optional feature):
     - Navigate to System tab → Hardware Environment card
     - Verify "Sensor Power Pin" shows GPIO number and ON status
   - If sensor power relay exists: Toggle via System tab → Relays

4. **Check EZO Firmware**:
   ```bash
   cd /home/pi/rdwc-v4
   source venv/bin/activate
   python -c "from app.ezo_i2c_stabilized import query_ezo; print(query_ezo(0x63, 'i'))"
   ```
   - **Expected**: Firmware version string (e.g., "?I,pH,1.0")
   - **Failure**: Timeout or error → Sensor hardware fault

**Solution**:
- **Loose connection**: Reseat I²C wires at sensor and Pi
- **Sensor power off**: Toggle sensor power relay ON
- **Firmware lockup**: Power cycle sensors via API: `POST /api/sensors/power_cycle?off_ms=2000&post_wait_ms=4000`
- **Hardware failure**: Replace sensor

---

### 7.2 pH/EC Reading Drifting Rapidly

**Symptom**: pH changes >0.5 units in 5 minutes, or EC swings >200 µS/cm  
**Diagnosis**:

1. **Check Calibration**:
   - Navigate to Calibration tab → pH section
   - Verify flags are GREEN (Mid, Low, High)
   - If any flag is red/yellow: Recalibrate (Section 2.1)

2. **Check Probe Condition**:
   - Remove probe from reservoir
   - Inspect for fouling, cracks, or discoloration
   - Clean probe (Section 3.1 for pH, Section 3.2 for EC)

3. **Check Actual Drift** (not sensor error):
   - Verify reservoir is stable (main pump running, circulation active)
   - Check dosing logs: Navigate to pH/EC tab → Dose Log
   - Excessive dosing indicates actual drift (not sensor error)

4. **Check Temperature Compensation**:
   - Navigate to Sensors tab
   - Verify "Temp" shows stable reading (~20-24°C)
   - Rapid temperature swings affect pH/EC readings (physics, not sensor fault)

**Solution**:
- **Calibration drift**: Recalibrate probe (Sections 2.1 or 2.2)
- **Fouled probe**: Clean thoroughly or replace if >12 months old
- **Actual drift**: Adjust dosing parameters or add buffers to reservoir
- **Aging probe**: Replace (pH probes: 12-24 month lifespan)

---

### 7.3 Relay Not Switching

**Symptom**: Relay button pressed but load does not actuate (pump/light/chiller OFF)  
**Diagnosis**:

1. **Check E-STOP**:
   - Verify E-STOP button is NOT active (should be gray, not red)
   - If red: Deactivate E-STOP

2. **Check Mode**:
   - Verify system is in Manual mode (for manual relay control)
   - Navigate to System tab → Controller Modes
   - If Auto mode: Relay is controlled by automation (manual override disabled)

3. **Check Cooldown**:
   - Navigate to System tab → Relays section
   - Look for cooldown timer next to relay (e.g., "15s remaining")
   - **Cause**: MIN_ON or MIN_OFF timer (safety feature)
   - **Solution**: Wait for cooldown to expire

4. **Check Interlock**:
   - For chiller/chiller pump: Verify main pump is running (circulation interlock)
   - Navigate to Circulation tab → Interlock Status
   - **Solution**: Start main pump before starting chiller pump/chiller

5. **Check Relay Status API**:
   ```powershell
   $base='http://192.168.88.49:8080'
   Invoke-RestMethod "$base/api/relays/status"
   ```
   - Inspect `relays` object for target relay
   - Check `gpio_state` (false=OFF, true=ON)
   - Check `reason` field for block reason

6. **Check Physical Relay**:
   - SSH to Pi and manually set GPIO:
     ```bash
     sudo raspi-gpio set 21 op dh  # Set GPIO 21 HIGH (lights OFF for active-low)
     sudo raspi-gpio set 21 op dl  # Set GPIO 21 LOW (lights ON for active-low)
     ```
   - If load still does NOT actuate: Relay hardware failure

**Solution**:
- **E-STOP active**: Deactivate E-STOP
- **Mode Auto**: Switch to Manual mode OR wait for automation to act
- **Cooldown**: Wait or set `force=true` in API call (not available in UI, requires curl/PowerShell)
- **Interlock**: Start main pump first
- **Hardware failure**: Replace relay module

---

### 7.4 Dosing Not Occurring (Auto Mode)

**Symptom**: Auto mode enabled, pH/EC out of range, but no dosing occurs  
**Diagnosis**:

1. **Check Mode**:
   - Navigate to pH/EC tab
   - Verify "Mode" badge shows "AUTO" (not Manual or Maintenance)

2. **Check Hold State**:
   - Verify "Hold" badge is NOT active
   - If hold active: Resume via corresponding tab button

3. **Check Sensor Staleness**:
   - Navigate to Sensors tab
   - Verify "Last Update" is <60 seconds ago
   - **Failure**: Stale sensors block dosing (safety guard)

4. **Check Dosing Guards**:
   - Navigate to pH/EC tab → Manual Dosing section
   - Below buttons, look for guard messages:
     - **pH**: "EC baseline guard" (EC <500 µS/cm blocks pH dosing)
     - **EC**: "pH guard" (pH <5.0 or >7.0 blocks EC dosing)
     - **Both**: "Daily cap reached" (safety limit hit)
     - **Both**: "Press cap in effect" (too soon since last dose)

5. **Check pH Hysteresis**:
   - pH automation only triggers if pH OUTSIDE target band
   - Navigate to pH tab → Parameters section
   - Check "pH Low" and "pH High" settings
   - **Example**: Low=5.8, High=6.2 → Dosing only occurs if pH <5.8 or >6.2
   - If pH = 6.0: Within band, no dosing required

6. **Check API Logs**:
   ```bash
   sudo journalctl -u rdwc-api -n 100 | grep -i dose
   ```
   - Look for dose attempts and block reasons

**Solution**:
- **Stale sensors**: Fix sensor poller (Section 7.1)
- **EC baseline**: Raise EC above 500 µS/cm (add nutrients)
- **pH guard**: Adjust pH to 5.0-7.0 range manually
- **Daily cap**: Wait until midnight (cap resets) OR manually override
- **Hysteresis**: Wait until pH drifts outside band OR manually dose

---

### 7.5 Web UI Not Loading

**Symptom**: Browser shows "Cannot connect" or "503 Service Unavailable"  
**Diagnosis**:

1. **Check Network Connectivity**:
   ```powershell
   Test-Connection 192.168.88.49 -Count 2
   ```
   - **Expected**: Reply from Pi (ping successful)
   - **Failure**: No reply → Network issue (Pi offline, WiFi down, IP changed)

2. **Check API Service**:
   ```bash
   ssh pi@192.168.88.49
   sudo systemctl status rdwc-api
   ```
   - **Expected**: "active (running)"
   - **Failure**: "inactive (dead)" → Restart: `sudo systemctl start rdwc-api`

3. **Check Port Binding**:
   ```bash
   sudo netstat -tuln | grep 8080
   ```
   - **Expected**: Line showing `0.0.0.0:8080` (API listening)
   - **Failure**: No output → API crashed or port blocked

4. **Check Firewall**:
   ```bash
   sudo iptables -L -n | grep 8080
   ```
   - **Expected**: No DROP rules for port 8080
   - **Failure**: DROP rule present → Remove: `sudo iptables -D INPUT -p tcp --dport 8080 -j DROP`

5. **Check Logs for Crash**:
   ```bash
   sudo journalctl -u rdwc-api -n 50
   ```
   - Look for Python traceback or "Fatal error" messages

**Solution**:
- **Network down**: Check Pi ethernet/WiFi, verify router
- **Service crashed**: Restart service, review logs for root cause
- **Port blocked**: Remove firewall rule OR change API port in `.env` file
- **Python exception**: Fix code bug (contact technical support)

---

## Spare Parts & Consumables

### 8.1 Critical Spare Parts

**Purpose**: Minimize downtime during component failure

| Part | Quantity | Reorder When | Est. Cost | Supplier |
|------|----------|--------------|-----------|----------|
| **Atlas Scientific pH Probe** | 1 | Probe age >10 months | $60 | Atlas Scientific |
| **Atlas Scientific EC Probe** | 1 | Probe shows corrosion | $60 | Atlas Scientific |
| **pH Calibration Buffer Set** (4.0, 7.0, 10.0) | 1 set | Buffers >6 months old | $25 | Atlas Scientific |
| **EC Calibration Solution** (1413 µS/cm) | 1 bottle | Bottle opened >12 months | $15 | Atlas Scientific |
| **Peristaltic Pump Tubing** | 2m | Tubing cracked or stiff | $20 | Generic |
| **8-Channel Relay Module** | 1 | Relay fails actuation test | $15 | Amazon/AliExpress |
| **Raspberry Pi 4** (4GB or 8GB) | 1 | Pi crashes frequently | $55 | RPi Foundation |
| **MicroSD Card** (32GB, Class 10) | 1 | Corrupted filesystem | $10 | SanDisk |
| **5V 3A Power Supply** (USB-C for Pi) | 1 | Undervoltage detected | $10 | RPi Foundation |

**Storage Location**: Climate-controlled cabinet, away from moisture and chemicals.

---

### 8.2 Consumables

**Purpose**: Routine maintenance and calibration

| Item | Usage Rate | Reorder When | Est. Cost | Supplier |
|------|------------|--------------|-----------|----------|
| **pH Storage Solution** (KCl 3M) | 50ml/month | <100ml remaining | $12 | Atlas Scientific |
| **Distilled Water** | 500ml/week | <1L remaining | $5 | Grocery store |
| **Soft Brushes** (sensor cleaning) | 1/year | Bristles frayed | $5 | Generic |
| **Lint-Free Wipes** | 10/week | <50 remaining | $10 | Lab supply |
| **White Vinegar** (sensor descaling) | 100ml/month | <200ml remaining | $3 | Grocery store |
| **Isopropyl Alcohol 70%** (disinfection) | 50ml/month | <100ml remaining | $5 | Pharmacy |

**Storage**: Consumables shelf, clearly labeled with purchase date.

---

### 8.3 Tools

**Purpose**: Maintenance and troubleshooting

| Tool | Purpose | Recommended Model |
|------|---------|-------------------|
| **Digital Multimeter** | Voltage, continuity, resistance testing | Fluke 117 or equivalent |
| **Soft Brush Set** | Sensor cleaning | Lab supply (nylon bristles) |
| **Graduated Cylinder** (50ml, 100ml) | Dosing pump calibration | Borosilicate glass |
| **pH Meter** (handheld, optional) | Verify RDWC pH sensor accuracy | Apera PH60 or equivalent |
| **EC Meter** (handheld, optional) | Verify RDWC EC sensor accuracy | HM Digital COM-100 |
| **Thermometer** (digital) | Verify RDWC RTD accuracy | Thermoworks |
| **Tweezers** (plastic, ESD-safe) | GPIO wire handling | Generic |
| **Screwdrivers** (Phillips, flathead) | Relay board, Pi case | Generic |
| **Wire Strippers** | GPIO wire repair | Klein Tools |
| **Heat Shrink Tubing** | Wire insulation | Generic |
| **Zip Ties** | Cable management | Generic |

**Storage**: Toolbox near RDWC system, organized by category.

---

## Appendix A: Maintenance Checklists

### A.1 Daily Checklist (5 min)
- [ ] Visual inspection (leaks, debris)
- [ ] Sensors online (Sensors tab)
- [ ] Readings sanity check (pH 5.5-6.5, EC 400-1800, Temp 18-24°C)
- [ ] Pump operation (main pump, chiller pump running smoothly)
- [ ] Water level check
- [ ] Lights on schedule
- [ ] Dose log review (no excessive dosing)

### A.2 Weekly Checklist (30 min)
- [ ] Clean pH probe (Section 3.1)
- [ ] Clean EC probe (Section 3.2)
- [ ] Clean RTD probe (Section 3.3)
- [ ] Reservoir top-off (water + nutrients if needed)
- [ ] Calibration flag check (pH tab green)
- [ ] Settings backup (Export JSON)
- [ ] Database size check (<100 MB)
- [ ] Relay manual test (all 8 relays)
- [ ] Cooldown check (System tab, no unexpected blocks)

### A.3 Monthly Checklist (1-2 hr)
- [ ] Full pH 3-point calibration (Section 2.1)
- [ ] EC calibration verification (Section 2.2)
- [ ] Dosing pump calibration check (Section 2.3)
- [ ] Database VACUUM (Section 4.2)
- [ ] Database backup (Section 4.3)
- [ ] Software update check (Section 5.1)
- [ ] Log review (Section 5.4)
- [ ] Relay board inspection (Section 6.1)
- [ ] Reservoir deep clean (if end of grow)

### A.4 Quarterly Checklist (2-3 hr)
- [ ] pH probe replacement (if >12 months old)
- [ ] EC cell inspection and replacement (if needed)
- [ ] Relay endurance test (20 cycles each)
- [ ] Pump maintenance (impellers, tubing)
- [ ] Chiller coil cleaning
- [ ] Raspberry Pi OS updates (Section 5.3)
- [ ] Power supply inspection (Section 6.2)
- [ ] GPIO connection inspection (Section 6.3)
- [ ] Documentation review and update

---

## Appendix B: Maintenance Log Template

**Grow Cycle**: ____________  
**Operator**: ____________  
**Date Range**: ____________ to ____________

| Date | Task | Duration | Findings | Action Taken | Next Due |
|------|------|----------|----------|--------------|----------|
| YYYY-MM-DD | pH Calibration | 20 min | All flags green | None | YYYY-MM-DD |
| YYYY-MM-DD | Sensor Cleaning | 10 min | Slight fouling on EC probe | Cleaned with vinegar | YYYY-MM-DD |
| YYYY-MM-DD | Database Backup | 2 min | 45 MB DB size | Backed up to PC | YYYY-MM-DD |

**Notes**:
- Record any anomalies, component replacements, or system downtime.
- Attach photos of damaged components or unusual conditions.
- Update this log after EVERY maintenance task.

---

**End of Maintenance Manual**
