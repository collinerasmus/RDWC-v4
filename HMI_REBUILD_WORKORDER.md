# HMI Rebuild Work Order — RDWC v4 Dashboard

**Date:** December 2, 2025  
**Target Branch:** `feature/hmi-rebuild-clean-slate`  
**Pi Deployment:** After full testing and approval only  
**Safety Note:** Current working state on Pi (PR #92, commit 3b60c32) must NOT be disturbed during development

---

## Executive Summary

The current HMI (3,215 lines in `app/static/index.html`) has accumulated technical debt from UI-first development. This work order defines a **clean slate rebuild** to achieve:

- **100% functional UI** — every button, input, and display must work
- **No hidden sections** — eliminate all `<details>` collapsible elements
- **Consistent patterns** — unified design language throughout
- **Dark theme** — green/blue hydroponic aesthetic (maintain current color scheme)
- **Reliable charts** — always-working Chart.js visualizations with proper data
- **Professional operations experience** — built from field-tested best practices

---

## Current State Analysis

### Observed Issues from Screenshots & Code Audit

1. **Collapsible Sections Everywhere**
   - Sensors tab: pH/EC calibration in `<details>` accordions
   - pH Control: Parameters, Pump Calibration, Automation sections collapsed
   - EC Control: Parameters, Pump Calibration, Manual Dosing sections collapsed
   - Chiller, Circulation, Lights, Scheduler: Settings in `<details>` elements
   - System tab: 4 settings cards (General, Safety, Alerts, UI) in collapsibles
   - **User requirement:** NO hidden sections — everything visible always

2. **Duplicate Calibration UI**
   - pH/EC calibration appears in Sensors tab AND again in dedicated controller sections
   - Different button patterns in each location
   - Unclear which is the "real" UI vs. legacy

3. **Scattered Settings**
   - Controller parameters in each controller tab
   - System-wide settings in System tab
   - No unified settings view
   - Changes may not sync properly across locations

4. **Mixed Control Patterns**
   - Some manual controls in KPI header rows
   - Some in collapsed sections below
   - Some as quick-action buttons (EC 3x3 grid)
   - Inconsistent enable/disable visual feedback

5. **Inline Code Bloat**
   - ~1,500 lines inline CSS (should be in `theme_v4.css`)
   - ~500 lines inline JavaScript (camera, charts, settings — should be modules)
   - 23 dynamically-loaded JS modules + `_OLD/` folder with deprecated code

6. **Navigation Issues**
   - Header has 9 tab buttons PLUS 5 controller chips (pH, EC, Chiller, Circulation, Lights)
   - Controller chips show status but also act as navigation (redundant with tabs)
   - Global auto control toggle + E-STOP + build info in header (crowded)

---

## Visual Layout Observations (from Screenshots)

### Tab 1: Overview (Dashboard)
- **Good:** Clean 8-row system status list with controller names + status badges
- **Good:** Live camera feed showing physical hardware (OpenCV/USB mode)
- **Issue:** Page title is redundant ("System" + "CONTROLLERS" label)
- **Keep:** Camera feed, system status rows — this is excellent for operations

### Tab 2: Sensors
- **Good:** 3 large KPIs (pH, EC, Temp) front and center
- **Good:** Sensor History chart with trend lines (pH red rising, EC blue flat, Temp green flat)
- **Good:** Time range selector (Last 24 Hours dropdown + date pickers + Apply/Export CSV)
- **Issue:** "Settings" checkbox + "Sensor Reading" checkbox (unclear purpose, hidden below chart)
- **Issue:** "Recent Readings (last 3)" section in `<details>` — calibration accordions below
- **Issue:** pH Probe Calibration + EC Probe Calibration sections all collapsed
- **Rebuild:** Remove collapsibles, integrate calibration into dedicated pH/EC tabs

### Tab 3: pH Control
- **Good:** Clean KPI row (pH 5.86, Pump OFF, Status "Auto Ready", Guards "All clear", Targets 5.8-6.2, Learned 1.00 ml/pH)
- **Good:** Dose History chart showing dose events (green annotation "Target: 5.8")
- **Issue:** Chart has minimal data (only one dose visible at ~00:00)
- **Issue:** "Parameters" section collapsed — contains 12+ settings (INITIAL_DOSE, INTERVAL_MIN, thresholds, etc.)
- **Issue:** "Pump Calibration" section collapsed — prime/run/commit workflow
- **Issue:** "Automation" section collapsed — learned value + clear button
- **Issue:** "Manual Dosing" section visible — Prime, Run, Commit Rate buttons + dose log
- **Issue:** "Dose Log (Last 20)" visible but empty table
- **Rebuild:** All sections always visible, reorganize into logical flow

### Tab 4: EC Control
- **Excellent:** KPI row (EC 0.42, Target Range 1.8-2.2, Smart Batch 0.0 ml, Status "Updated: 2235135")
- **Excellent:** Guard Status panel with 7 chips (E-STOP green, Sensor green, Manual mode, Stg Cap green, Press Cnt green, Boot green, EC Tgt orange)
- **Excellent:** Controller Preview bar (gradient "Would Dose" → "Needs" → "Below target" → "Target Zone" → "Above target" → "Excess" → "Bloom")
- **Excellent:** Quick Dose 3x3 grid (Grow: 0.5s/1.0s/2.0s, Micro: 0.5s/1.0s/2.0s, Bloom: 0.5s/1.0s/2.0s)
- **Good:** Dose History chart (mostly flat at ~0 mS/cm with target annotations)
- **Issue:** "Parameters" section collapsed (10+ settings: Low EC, High EC, Micro ml/s, Grow ml/s, etc.)
- **Issue:** "Pumps Calibration" section collapsed (3 pumps: Grow, Micro, Bloom — each with Prime/Run/Commit)
- **Issue:** "Automation" section collapsed (learned value + clear button)
- **Issue:** "Manual Dosing (Volume)" section collapsed (dropdown + 3 dose buttons + calibrate button)
- **Issue:** "Pump Control (Time)" section collapsed (Grow/Micro/Bloom time inputs + Pulse buttons)
- **Issue:** "Dose Log (Last 20)" visible — table with 3 recent entries (Bloom 0.0 ml "ui_manual")
- **Rebuild:** Keep excellent guard panel, preview bar, quick dose grid — expand all sections

### Tab 5: Chiller Controller
- **Good:** Clean KPI row (Actual Temp 24.57°C, Target Temp 19.0°C, Growth Stage "Default", Chiller "COOLING")
- **Issue:** "Temperature & Chiller Settings" section in `<details>` — contains all controls
- **Issue:** Settings include Target, Hysteresis, Low Alert, High Alert, Min OFF time, Min ON time, Growth Stage dropdown
- **Issue:** Force chiller ON/OFF buttons + "30 min Auto" dropdown below
- **Issue:** Native M4-3/A status message at bottom (cryptic constraint error message)
- **Rebuild:** Expand settings section always visible, simplify layout

### Tab 6: Circulation Controller
- **Good:** Simple KPI row (Main Pump ON, Chiller Pump ON)
- **Issue:** "Manual Control" section visible — two toggle buttons + description text
- **Issue:** "Settings" section collapsed — Min OFF times for both pumps
- **Rebuild:** Very simple page, just keep visible and clean

### Tab 7: Lights Control
- **Good:** Clean KPI row (Status ON, Schedule "Following schedule", Window "20:00 → 12:00")
- **Issue:** "Manual Control" section visible — toggle + Lights OFF button + description
- **Issue:** "Settings" section collapsed — Lights ON Time / Lights OFF Time inputs
- **Issue:** "Info" section collapsed — 3 bullet points about edge-only scheduler
- **Rebuild:** Simple page, expand all sections

### Tab 8: Scheduler
- **Excellent:** Schedule Timeline visualization — 12-week grid showing phase icons (veg 🌱, bloom 🌺, flush 💧)
- **Excellent:** Week selector buttons (W1-W12) below timeline
- **Excellent:** "This Week Targets" panel (Phase: Bloom, EC Target: 2 mS/cm, pH Band: 5.8-6.2, Lights: 12/12)
- **Good:** "EMG 5 start (vp per 361)" section with Grow/Micro/Bloom inputs
- **Good:** "Next 48h Plan" showing upcoming dose event with EC_DOSE button
- **Issue:** "Schedule Settings" section collapsed (10s/500s/Commit buttons + rapid test helper + status text)
- **Rebuild:** Expand settings section, this is a great visualization

### Tab 9: System
- **Excellent:** 11 information cards showing real-time system state
- **Raspberry Pi card:** CPU 27.8%, Freq 1200 MHz, Temp 55.8°C, Memory 289/906 MB (41.9%), Disk 27.90/30.1 GB, Uptime 2d 1h 20m
- **Software card:** RDWC v4.0 ph1-final, Python 3.11.2, Git copilot/clean-ec-page-style, rdwc(API) Active, rdwc-sensors Active
- **Hardware Environment card:** SPI 0x63, EC 0x64, RTD 0x66, GPIO 21 (sensor power), GPIO 16/20/26 (relays), etc.
- **Database card:** Size 14.09 MB, 233,882 readings, 71 pH Doses, 12 EC Doses, oldest 01/11/2025, newest 02/12/2025
- **Network card:** Hostname sensor-node, IPs 127.0.0.1/192.168.88.49
- **RDWC Processes card:** 3 Python processes with PIDs and memory usage
- **Relays card:** 4x2 grid showing relay states (pH Up/Micro/Main/Bloom ON, Grow/Video/Chiller/Other OFF)
- **Issue:** "General Settings" card collapsed — Grow name, Timezone, Grow start date, Reservoir liters, Day #
- **Issue:** "Safety Settings" card collapsed — 8 checkboxes + 6 numeric inputs (ESTOP, Maintenance, dose limits, etc.)
- **Issue:** "Alerts Settings" card collapsed — Email config + cooldown
- **Issue:** "UI Settings" card collapsed — Sensor range, Refresh interval, Chart poll
- **Rebuild:** Expand all 4 settings cards always visible

---

## Design Requirements (User-Specified)

1. **Dark Theme:** Maintain current dark background (`#0a0e1a` or similar) with green/blue accents
2. **Color Palette:**
   - Green: `#10b981` (success, active states, good readings)
   - Blue: `#3b82f6` (primary actions, info, links)
   - Red: `#ef4444` (errors, alerts, E-STOP)
   - Yellow: `#f59e0b` (warnings, cautions)
   - Gray tones: `#1f2937` (cards), `#374151` (borders), `#9ca3af` (muted text)
3. **No Hidden Sections:** Every section must be visible without clicking to expand
4. **Charts Always Work:** Chart.js instances must initialize properly, handle empty data gracefully, update reliably
5. **100% Functional:** Every button must call backend endpoints, every input must save correctly, every display must show real data

---

## Proposed New HMI Structure

### Global Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ RDWC v4 — Dashboard               [Build: main@abc1234 • 1 hr] │
│                                                                   │
│ [Global Auto: OFF] [E-STOP: Active] [Safe Mode: ON]             │
│                                                                   │
│ [Overview] [Sensors] [pH] [EC] [Chiller] [Circulation]          │
│ [Lights] [Scheduler] [System]                                    │
└─────────────────────────────────────────────────────────────────┘
```

- **Remove:** Redundant controller status chips (already shown in tabs)
- **Keep:** Global auto control toggle, E-STOP button, safe mode indicator
- **Add:** Build/branch info always visible (not just hover tooltip)

### Tab 1: Overview (Keep Excellent Design)

```
┌─────────────────────────────────────────────────────────────────┐
│ System Status                                                     │
│                                                                   │
│ 🌡️ Sensors              [ONLINE] [AUTO]                          │
│ 🧪 pH Controller        [OK] [AUTO]                              │
│ ⚡ EC Controller        [OK] [AUTO]                              │
│ ❄️ Chiller              [COOLING] [PUMP] [IDLE] [AUTO]          │
│ 💧 Circulation          [PUMP] [RUNNING] [AUTO]                  │
│ 💡 Lights               [LIGHTS] [ON] [AUTO]                     │
│ 📅 Scheduler            [ENABLED] [AUTO]                         │
│ 🔧 System               [OK] [AUTO]                              │
│                                                                   │
│ Camera — Live Feed                                                │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │                                                               │ │
│ │              [Hardware camera feed 640x480]                  │ │
│ │                                                               │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ Status: Streaming • Mode: USB/OpenCV                             │
└─────────────────────────────────────────────────────────────────┘
```

### Tab 2: Sensors (Simplified, No Calibration)

```
┌─────────────────────────────────────────────────────────────────┐
│ Sensors                                                           │
│                                                                   │
│ ┌────────────┐  ┌────────────┐  ┌────────────┐                  │
│ │   pH       │  │ EC (mS/cm) │  │  Temp (°C) │                  │
│ │   5.85     │  │   0.42     │  │   24.56    │                  │
│ │  ● ONLINE  │  │  ● ONLINE  │  │  ● ONLINE  │                  │
│ └────────────┘  └────────────┘  └────────────┘                  │
│                                                                   │
│ Sensor History (pH/EC/Temp Trends)                               │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ [Chart with 3 trend lines: pH red, EC blue, Temp green]    │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│ Time Range: [Last 24 Hours ▼] [2025/12/01 21:35] to [Now]      │
│ [Apply] [Export CSV]                                             │
│                                                                   │
│ Sensor Mode: (●) Auto Poller  ( ) Manual Read  ( ) Maintenance  │
│                                                                   │
│ Quick Actions:                                                    │
│ [Read Now] [Power Cycle Sensors] [Fix I²C Addresses]            │
│                                                                   │
│ Last Update: 2 seconds ago • Poller: Active (PID 19466)         │
└─────────────────────────────────────────────────────────────────┘
```

**Note:** Move all calibration UI to dedicated pH/EC tabs where dosing happens

### Tab 3: pH Control (All Sections Visible)

```
┌─────────────────────────────────────────────────────────────────┐
│ pH Control                                        [AUTO: ON]      │
│                                                                   │
│ ┌─────┐ ┌────────┐ ┌────────────┐ ┌──────────┐ ┌──────────────┐│
│ │ pH  │ │ Pump   │ │   Status   │ │  Guards  │ │   Targets    ││
│ │5.86 │ │  OFF   │ │Auto Ready  │ │All clear │ │  5.8 – 6.2   ││
│ └─────┘ └────────┘ └────────────┘ └──────────┘ └──────────────┘│
│                                                                   │
│ Learned Response: 1.00 ml/pH • Total Today: 2.8 ml              │
│                                                                   │
│ Dose History (Last 24 Hours)                                     │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ [Chart: dose events as vertical lines, pH trend, target]   │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ Time Range: [Last 24 Hours ▼] [Date pickers] [Apply] [Export]  │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Controller Parameters                                             │
│                                                                   │
│ Targets:  Low pH [5.8]  High pH [6.2]                           │
│ Dosing:   Initial Dose [0.2] ml  Max Dose [1.0] ml              │
│ Safety:   Interval Min [300] sec  Daily Cap [30] ml             │
│ Learning: Stabilization [300] sec  Max Age [3600] sec            │
│                                                                   │
│ [Save Parameters]                                                 │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ pH Probe Calibration                                             │
│                                                                   │
│ Current pH: 5.86 • Stabilized: 5.86 (±0.02)                     │
│ Calibration Status: Mid (7.00) ✓ • Low ✗ • High ✗               │
│                                                                   │
│ [Read Stable] [Calibrate Mid (7.00)] [Calibrate Low (4.00)]     │
│ [Calibrate High (10.00)] [Clear Calibration]                     │
│                                                                   │
│ Buffer Solutions:  Mid 7.00 • Low 4.00 • High 10.00             │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ pH Up Pump Calibration                                           │
│                                                                   │
│ Current Rate: 0.298 ml/sec                                       │
│ Workflow: 1) Prime pump  2) Run timed dose  3) Commit rate      │
│                                                                   │
│ Duration (s): [10] Measured (ml): [   ]                         │
│ [Prime (3s)] [Run] [Commit Rate]                                │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Automation                                                        │
│                                                                   │
│ Auto Mode: [ON]  •  Learned: 1.00 ml/pH  •  [Clear Learned]    │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Manual Dosing                                                     │
│                                                                   │
│ [Prime (0.5s)] [0.3s] [0.5s] [1.0s] [Dose]                      │
│                                                                   │
│ Safety: Max per press 1.5s • Daily cap 30 ml • Min interval 5s  │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Recent Dose Log (Last 20)                                        │
│                                                                   │
│ Time              Pump    Seconds   pH Before   pH After   Note  │
│ 29/1/2025 19:00   pH_up   0.50b     —           5.85       daily_│
│ 29/1/2025 11:52   pH_up   6.00b     5.07        —          test_ │
│ [Refresh]                                                         │
└─────────────────────────────────────────────────────────────────┘
```

### Tab 4: EC Control (All Sections Visible, Keep Excellent Features)

```
┌─────────────────────────────────────────────────────────────────┐
│ EC Control                                        [AUTO: ON]      │
│                                                                   │
│ ┌──────────┐ ┌────────────┐ ┌─────────────┐                     │
│ │EC (mS/cm)│ │Target Range│ │ Smart Batch │                     │
│ │  0.42    │ │  1.8 – 2.2 │ │   0.0 ml    │                     │
│ └──────────┘ └────────────┘ └─────────────┘                     │
│                                                                   │
│ Guard Status:                                                     │
│ [E-STOP ✓] [Sensor ✓] [Manual] [Stg Cap ✓] [Press Cnt ✓]       │
│ [Boot ✓] [EC Tgt !]                                              │
│                                                                   │
│ Controller Preview:                                               │
│ [████ Would Dose ████ Needs ████ Below ▓▓▓▓ Target ░░ Excess]  │
│ Current action: Target Zone  •  EC deviation: -1.5 mS/cm         │
│                                                                   │
│ Quick Dose (Growth Phase: Bloom)                                 │
│ Grow:  [0.5s] [1.0s] [2.0s]                                     │
│ Micro: [0.5s] [1.0s] [2.0s]                                     │
│ Bloom: [0.5s] [1.0s] [2.0s]                                     │
│                                                                   │
│ Dose History (Last 24 Hours)                                     │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ [Chart: EC trend flat at ~0.4, target band 1.8-2.2]        │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ Time Range: [Last 24 Hours ▼] [Date pickers] [Apply] [Export]  │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Controller Parameters                                             │
│                                                                   │
│ Targets: Low EC [1.8] mS/cm  High EC [2.2] mS/cm                │
│ Rates:   Grow [0.3] ml/s  Micro [0.3] ml/s  Bloom [0.3] ml/s   │
│ Safety:  Interval Min [300] sec  Daily Cap [120] ml             │
│                                                                   │
│ [Save Parameters]                                                 │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ EC Probe Calibration                                             │
│                                                                   │
│ Current EC: 0.42 mS/cm                                           │
│ Calibration Status: Low (1413 µS) ✓ • High ✗                   │
│ Probe Constant (K): 1.0                                          │
│                                                                   │
│ [Calibrate Low (1413)] [Calibrate High (12880)] [Set K]         │
│ [Clear Calibration]                                              │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Nutrient Pump Calibration                                        │
│                                                                   │
│ Grow Pump:  0.3 ml/s  [Prime] [Run] [Commit]  Duration: [10]s  │
│ Micro Pump: 0.3 ml/s  [Prime] [Run] [Commit]  Duration: [10]s  │
│ Bloom Pump: 0.3 ml/s  [Prime] [Run] [Commit]  Duration: [10]s  │
│                                                                   │
│ Measured volume (ml): [   ]  (after Run, before Commit)         │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Automation                                                        │
│                                                                   │
│ Auto Mode: [ON]  •  Learned: 0.0 ml/mS·cm  •  [Clear Learned]  │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Manual Dosing                                                     │
│                                                                   │
│ Volume Mode: [+10 ml] [+50 ml] [+100 ml] [Calibrate (?)]       │
│                                                                   │
│ Time Mode:                                                        │
│ Grow (0.3s):  [0.5s] [1.0s] [Pulse]                            │
│ Micro (0.3s): [0.5s] [1.0s] [Pulse]                            │
│ Bloom (0.3s): [0.5s] [1.0s] [Pulse]                            │
│                                                                   │
│ Safety: Max per press 1.5s • Daily cap 120 ml • Rapid 6-4s     │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Recent Dose Log (Last 20)                                        │
│                                                                   │
│ Time              Pump    Volume    EC Δ    Δ     Note          │
│ 22:56:40 06/1     Bloom   0.0 ml    —.—     —     ui_manual    │
│ 22:56:24 06/1     micro   0.0 ml    —.—     —     ui_manual    │
│ [Refresh]                                                         │
└─────────────────────────────────────────────────────────────────┘
```

### Tab 5: Chiller (Simplified, All Visible)

```
┌─────────────────────────────────────────────────────────────────┐
│ Chiller Control                                  [AUTO: ON]      │
│                                                                   │
│ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ ┌───────────┐ │
│ │ Actual Temp  │ │ Target Temp  │ │   Stage    │ │  Status   │ │
│ │   24.57°C    │ │   19.0°C     │ │  Default   │ │ COOLING   │ │
│ └──────────────┘ └──────────────┘ └────────────┘ └───────────┘ │
│                                                                   │
│ Temperature Settings                                             │
│                                                                   │
│ Target (°C):  [19.0]  Hysteresis (°C): [0.7]                   │
│ Growth Stage: [Default ▼] (affects target from schedule)        │
│                                                                   │
│ Alert Thresholds:                                                │
│ Low Alert (°C): [0]   High Alert (°C): [0]                     │
│                                                                   │
│ Timing Constraints:                                              │
│ Min OFF time (s): [300]   Min ON time (s): [60]                 │
│                                                                   │
│ [Save Settings]                                                   │
│                                                                   │
│ Force Controls (Override automation)                             │
│                                                                   │
│ [Force ON] [Force OFF]  Auto Resume: [30 min ▼]                │
│                                                                   │
│ Native M4-3/A: Convergence prescribed. Deets non ON...          │
└─────────────────────────────────────────────────────────────────┘
```

### Tab 6: Circulation (Minimal)

```
┌─────────────────────────────────────────────────────────────────┐
│ Circulation Control                              [AUTO: ON]      │
│                                                                   │
│ ┌──────────────┐  ┌──────────────┐                              │
│ │  Main Pump   │  │Chiller Pump  │                              │
│ │     ON       │  │     ON       │                              │
│ └──────────────┘  └──────────────┘                              │
│                                                                   │
│ Manual Control                                                    │
│                                                                   │
│ Manual relay control follows Auto/Manual mode and Guardian       │
│ conditional enforcement. Cooldowns are enforced.                 │
│                                                                   │
│ [Toggle Main Pump]  [Toggle Chiller Pump]                       │
│                                                                   │
│ Settings                                                          │
│                                                                   │
│ Configure minimum off times to prevent rapid cycling (bypass     │
│ cooldown with Guardian mode and reason whitelists)               │
│                                                                   │
│ Main Pump Min OFF (s):    [5]                                   │
│ Chiller Pump Min OFF (s): [0]                                   │
│                                                                   │
│ [Save Settings]                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Tab 7: Lights (Minimal)

```
┌─────────────────────────────────────────────────────────────────┐
│ Lights Control                                   [AUTO: ON]      │
│                                                                   │
│ ┌─────────┐  ┌─────────────────────┐  ┌──────────────────────┐ │
│ │ Status  │  │      Schedule       │  │       Window         │ │
│ │   ON    │  │Following schedule   │  │   20:00 → 12:00      │ │
│ └─────────┘  └─────────────────────┘  └──────────────────────┘ │
│                                                                   │
│ Manual Control                                                    │
│                                                                   │
│ Manual relay control follows Auto/Manual mode. Schedule edges    │
│ take precedence unless Guardian mode released lights attribution │
│ to manual control.                                               │
│                                                                   │
│ [Lights OFF]                                                      │
│                                                                   │
│ Schedule Settings                                                 │
│                                                                   │
│ Configure light schedule and timing. Only schedules w/o          │
│ transitions fire on day flip; periodic enforcement NOT           │
│ supported. Maintain steady start. Edge suppression auto edges.   │
│                                                                   │
│ Lights ON Time:  [20:00]                                        │
│ Lights OFF Time: [12:00]                                        │
│                                                                   │
│ [Save Settings]                                                   │
│                                                                   │
│ Info                                                              │
│                                                                   │
│ • Edge-only scheduler: only two transitions per day, no          │
│   periodic enforcement                                           │
│ • Manual mode bypasses schedule. Auto resumes schedule edges.    │
│ • Maintenance Override releases relay start. Empty relay attr    │
│   auto relays into lights_OFF                                    │
└─────────────────────────────────────────────────────────────────┘
```

### Tab 8: Scheduler (Keep Excellent Design, Expand Settings)

```
┌─────────────────────────────────────────────────────────────────┐
│ Schedule Controller                              [ENABLED]       │
│                                                                   │
│ ┌──────────┐ ┌─────────┐ ┌────────────┐ ┌─────────────────┐    │
│ │Current   │ │ Phase   │ │   Week     │ │   Day in Grow   │    │
│ │  Week    │ │ bloom   │ │ 11/10/2025 │ │       49        │    │
│ │   49     │ │         │ │            │ │                 │    │
│ └──────────┘ └─────────┘ └────────────┘ └─────────────────┘    │
│                                                                   │
│ Schedule Timeline (12 Weeks)                                     │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ [W1: 🌱 veg]   [W2: 🌱 veg]   [W3: 🌺 bloom]  [W4: 🌺 bloom]│ │
│ │ [W5: 🌺 bloom] [W6: 🌺 bloom] [W7: ⚠️ SKIP]  [W8: 🌺 bloom]│ │
│ │ [W9: 🌺 bloom] [W10: 🌺 bloom][W11: 💧 flush][W12: 💧 flush]│ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│ [W1] [W2] [W3] [W4] [W5] [W6] [W7] [W8] [W9] [W10] [W11] [W12] │
│                                                                   │
│ This Week Targets (Week 49: Bloom)                               │
│                                                                   │
│ Phase: Bloom  •  EC Target: 2 mS/cm  •  pH Band: 5.8–6.2  •     │
│ Lights: 12/12                                                     │
│                                                                   │
│ EMG 5 start (vp per 361)                                         │
│                                                                   │
│ Grow: [5] ml/day  Micro: [5] ml/day  Bloom: [20] ml/day        │
│                                                                   │
│ [Edit Selected Week]  [Reset Schedule to Defaults]              │
│                                                                   │
│ Next 48h Plan                                                     │
│                                                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 02/12/2025, 22:09:19                                         │ │
│ │ GROW: 0.5s+ 5×10 → 0.57 mS/cm                                │ │
│ │ Reason: ec_below_target                                      │ │
│ │                                                 [EC_DOSE]    │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│ Schedule Settings                                                 │
│                                                                   │
│ Status unavailable                                               │
│                                                                   │
│ Rapid Test Helper: Wait intervals...                            │
│ [10s] [500s] [Commit]                                           │
│                                                                   │
│ Baseline offset: no defined start during from this label         │
│ resolution offset = no advance (via during from this, info...)  │
└─────────────────────────────────────────────────────────────────┘
```

### Tab 9: System (Expand All Settings Cards)

```
┌─────────────────────────────────────────────────────────────────┐
│ System Information                                       [LIVE]  │
│                                                                   │
│ 🍓 Raspberry Pi                                                  │
│ CPU: 27.8% @ 1200 MHz • Temp: 55.8°C • Memory: 289/906 MB      │
│ (41.9%) • Disk: 27.90/30.1 GB (30.1%) • Uptime: 2d 1h 20m      │
│                                                                   │
│ 💻 Software                                                      │
│ RDWC: v4.0 ph1-final • Python: 3.11.2 • Git:                   │
│ copilot/clean-ec-page-style • rdwc(API): Active • rdwc-sensors: │
│ Active                                                           │
│                                                                   │
│ 🔌 Hardware Environment                                         │
│ SPI: 0x63 • EC: 0x64 • RTD: 0x66 • Sensor Power: GPIO 21 •     │
│ Chiller Power: GPIO 16 • Chiller Pump: GPIO 20 • Other Lights:  │
│ GPIO 26 • Dosing I²C: 13 • Dosing Relays: GPIO 6/13/19         │
│                                                                   │
│ 💾 Database                                                      │
│ Size: 14.09 MB • Readings: 233,882 • pH Doses: 71 • EC Doses:  │
│ 12 • Oldest: 01/11/2025 14:37:59 • Newest: 02/12/2025 21:36:30 │
│                                                                   │
│ 🌐 Network                                                       │
│ Hostname: sensor-node • IPs: 127.0.0.1/255.0.0.0,               │
│ 192.168.88.49/255.255.255.0                                     │
│                                                                   │
│ ⚙️ RDWC Processes                                               │
│ PID    NAME       USER    MEMORY                                 │
│ 19048  python     pi      1.49%                                 │
│ 19466  python     pi      25.42%                                │
│ 19602  python1    pi      2.07%                                 │
│                                                                   │
│ 🔧 Relays                                                        │
│ [pH Up: Auto]  [Micro Pump: Auto]  [Main Pump: Auto]  [Bloom:  │
│ Auto]                                                            │
│ [Grow Pump: —]  [Video Doling: Auto]  [Chiller Power: —]       │
│ [Other Lights: —]                                               │
│                                                                   │
│ Last updated at 21:35:24                                         │
│ Manual: relays stay OFF at boot. Auto: critical relays restored │
│ from last state. Active: auto OFF → HDMI. Safe: all off basic.  │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ ⚙️ General Settings                                             │
│                                                                   │
│ Grow name:       [RDWC-v3]                                      │
│ Timezone:        [Africa/Johannesburg]                          │
│ Grow start date: [2021/09/15]  Day #: [49]                     │
│ Reservoir (L):   [100]                                          │
│                                                                   │
│ [Save General Settings]                                          │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 🛡️ Safety Settings                                             │
│                                                                   │
│ [ ] ESTOP prevents across relays                                │
│ [ ] Maintenance override ONLY after checks on override (TEST)   │
│                                                                   │
│ Max seconds per dose press:      [10]                           │
│ Max total seconds per 24h pumps: [500]                          │
│ Min off between doses (s):       [2]                            │
│ Main pump min off (s):           [5]                            │
│ Chiller pump min off (s):        [300]                          │
│ Chiller min on (s):              [60]                           │
│                                                                   │
│ [Save Safety Settings]                                           │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 🔔 Alerts Settings                                              │
│                                                                   │
│ Configure alert notification email and cooldown periods.         │
│                                                                   │
│ Alert email to:    [user@example.com]                           │
│ Alert cooldown (s): [600]                                       │
│                                                                   │
│ [Save Alerts Settings]                                           │
│                                                                   │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 🎨 UI Settings                                                  │
│                                                                   │
│ Configure dashboard behavior and display intervals, display      │
│ preferences                                                       │
│                                                                   │
│ Default sensor range:    [24h]                                  │
│ Refresh Interval (ms):   [1000]                                 │
│ Sensor poll (ms):        [5000]                                 │
│                                                                   │
│ [Save UI Settings]                                               │
│                                                                   │
│ ⚠️ Changes apply immediately unless noted. Always verify changes │
│ on save.                                                         │
│                                                                   │
│ [↻ Refresh] [Export JSON] [Import JSON]                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Guidelines

### Architecture

1. **Keep Existing Backend** — All API endpoints work correctly, DO NOT modify backend
2. **Keep JavaScript Modules** — 23 existing modules are functional, refactor only if necessary
3. **Move Inline Code to Files:**
   - Move ~1,500 lines inline CSS to `app/static/css/theme_v4.css`
   - Move ~500 lines inline JS to appropriate modules or new `app/static/js/ui_core.js`
4. **Delete `_OLD/` Folder** — Remove deprecated code completely
5. **Remove All `<details>` Elements** — Replace with always-visible `<div>` sections

### CSS/Styling

1. **Use Existing Theme Variables:**
   ```css
   :root {
     --bg-primary: #0a0e1a;
     --bg-card: #1f2937;
     --border-color: #374151;
     --text-primary: #f9fafb;
     --text-muted: #9ca3af;
     --success: #10b981;
     --info: #3b82f6;
     --warning: #f59e0b;
     --error: #ef4444;
   }
   ```

2. **Maintain Current Component Styles:**
   - `.kpi-badge` — large value displays
   - `.btn-chip` — status indicators
   - `.guard-chip` — guard status badges
   - `.status-badge` — ON/OFF/AUTO indicators
   - `.card` — section containers

3. **Remove Collapsible Styles:**
   - Delete `details[open]` and `summary` styles
   - Replace with simple `.section` wrappers

### JavaScript

1. **Keep Polling Manager** — `polling_manager.js` handles all updates correctly
2. **Keep Chart Implementations** — `ph_chart.js`, `ec_chart.js`, `trends.js` work well
3. **Keep Controller Modules** — `ph.js`, `ec.js`, `chiller.js`, etc. are functional
4. **Refactor Initialization:**
   - Move inline `window.addEventListener('DOMContentLoaded', ...)` to dedicated init module
   - Ensure all modules load in correct order
   - Handle missing elements gracefully (check `if (element)` before operations)

### Testing Criteria (Before Pi Deployment)

1. **Every Button Works:**
   - Click each button, verify API call in Network tab
   - Verify response handling and UI updates

2. **Every Input Saves:**
   - Change each input field, click Save
   - Verify saved value persists on page refresh

3. **Every Chart Renders:**
   - Check Sensors trend chart shows 3 lines
   - Check pH dose history shows dose events
   - Check EC dose history shows dose events
   - Verify time range selector updates charts
   - Verify charts handle empty data without errors

4. **Guards Display Correctly:**
   - Verify pH/EC guard chips update based on `/api/ph/status` and `/api/ec/status`
   - Verify buttons disable when guards active

5. **Calibration Workflows:**
   - pH: Read → Mid → Low → High → Status check
   - EC: Clear → Low → Status check
   - Dosing pumps: Prime → Run → Commit → Verify rate saved

6. **Manual Controls:**
   - All manual dose buttons functional
   - Force chiller ON/OFF works
   - Pump toggles work
   - Lights toggle works

7. **Settings Persistence:**
   - Change settings in each tab, save, refresh — verify persistence
   - Export JSON, modify, import — verify import works

8. **Camera Stream:**
   - Verify live feed displays in Overview tab
   - Verify health-based mode switching (OpenCV ↔ Picamera2)

9. **Responsive Layout:**
   - Test on 1920x1080 (typical operator screen)
   - Verify no horizontal scroll
   - Verify all text readable

10. **Performance:**
    - No console errors on load
    - No memory leaks (run 5+ minutes, check DevTools memory)
    - Polling doesn't cause UI jank

---

## File-Level Changes Required

### Files to Modify

1. **`app/static/index.html`** (3,215 lines → ~2,000 lines)
   - Remove all `<details>` elements, convert to `<div class="section">`
   - Move inline CSS to `theme_v4.css`
   - Move inline JS to modules
   - Simplify header (remove controller status chips)
   - Reorganize tab content per wireframes above

2. **`app/static/css/theme_v4.css`**
   - Add all inline CSS from `index.html`
   - Remove `details`/`summary` styles
   - Add `.section` styles for always-visible sections

3. **`app/static/js/ui_core.js`** (NEW)
   - Move camera stream init
   - Move chart init
   - Move settings load/save
   - Move tab switching logic

4. **`app/static/js/tabs.js`**
   - Verify tab switching doesn't break with new HTML structure
   - Ensure all tabs initialize correctly

5. **`app/static/js/ph.js`**, **`ec.js`**, **`sensors.js`**, **`chiller.js`**, **`circulation.js`**, **`lights_v2.js`**, **`schedule.js`**, **`system.js`**
   - Update element IDs if changed in HTML
   - Remove collapsible section toggle logic
   - Ensure all `getElementById` calls have null checks

### Files to Delete

1. **`app/static/js/_OLD/`** — entire folder and contents

### Files to Keep Unchanged

1. **All backend files** (`app/*.py`) — DO NOT MODIFY
2. **`app/static/js/polling_manager.js`** — works correctly
3. **`app/static/js/range.js`** — date utilities are fine
4. **`app/static/js/error_reporter.js`** — error handling is fine
5. **Chart.js libraries** — CDN links in HTML

---

## Acceptance Criteria

### Phase 1: Development Branch (feature/hmi-rebuild-clean-slate)

- [ ] All collapsible sections removed
- [ ] All inline CSS moved to `theme_v4.css`
- [ ] All inline JS moved to modules
- [ ] `_OLD/` folder deleted
- [ ] HTML reduced from 3,215 lines to ~2,000 lines
- [ ] No console errors on page load
- [ ] All tabs render correctly

### Phase 2: Functional Testing (Local TestClient)

- [ ] All buttons call correct endpoints
- [ ] All inputs save correctly
- [ ] All charts render with data
- [ ] All calibration workflows complete successfully
- [ ] All manual controls functional
- [ ] Guards update correctly
- [ ] Settings persist across refresh

### Phase 3: Visual QA

- [ ] Dark theme consistent throughout
- [ ] Green/blue accents used appropriately
- [ ] No horizontal scroll on 1920x1080
- [ ] All text readable (no truncation)
- [ ] Spacing/padding consistent
- [ ] Button states clear (hover, active, disabled)

### Phase 4: Performance Testing

- [ ] Page load < 2 seconds
- [ ] No memory leaks after 10 minutes
- [ ] Polling doesn't block UI
- [ ] Charts update smoothly
- [ ] No console warnings

### Phase 5: Pi Deployment

- [ ] Create backup tag: `v4.0-pre-hmi-rebuild`
- [ ] Deploy to Pi test environment first
- [ ] Verify all hardware interactions work (relays, sensors, camera)
- [ ] Run 24-hour soak test
- [ ] Only then merge to main and deploy to production

---

## Cloud Agent Execution Instructions

1. **Create Branch:**
   ```bash
   git checkout -b feature/hmi-rebuild-clean-slate
   ```

2. **Start with HTML Restructure:**
   - Open `app/static/index.html`
   - Extract all inline CSS to `theme_v4.css`
   - Extract all inline JS to `ui_core.js`
   - Remove all `<details>` elements
   - Implement tab structures from wireframes above

3. **Update CSS:**
   - Open `app/static/css/theme_v4.css`
   - Add extracted inline CSS
   - Remove `details`/`summary` styles
   - Add `.section` styles

4. **Create UI Core Module:**
   - Create `app/static/js/ui_core.js`
   - Move camera init
   - Move chart init
   - Move settings functions

5. **Update Existing Modules:**
   - Update element IDs in all modules to match new HTML
   - Remove collapsible toggle logic
   - Add null checks for all DOM queries

6. **Delete Deprecated Code:**
   ```bash
   rm -rf app/static/js/_OLD/
   ```

7. **Test Locally:**
   - Run `uvicorn app.main:app --reload --host 0.0.0.0 --port 8080`
   - Open http://localhost:8080 in browser
   - Go through all 9 tabs
   - Click every button
   - Change every input
   - Verify charts render
   - Check console for errors

8. **Commit and Push:**
   ```bash
   git add .
   git commit -m "HMI rebuild: Remove collapsibles, reorganize layout, move inline code to files"
   git push origin feature/hmi-rebuild-clean-slate
   ```

9. **Report Back:**
   - Total lines removed from HTML
   - All functional testing results
   - Screenshots of each tab
   - Any issues encountered
   - Recommended next steps

---

## Success Metrics

- **Code Quality:** HTML reduced to ~2,000 lines, zero inline CSS/JS
- **Functionality:** 100% of buttons/inputs/charts working
- **User Experience:** Zero hidden sections, consistent design
- **Performance:** No console errors, no memory leaks
- **Safety:** Working Pi state (PR #92) never touched during development

---

## References

- Current working state: Pi at 192.168.88.49:8080, branch `copilot/clean-ec-page-style`, commit 3b60c32
- EC units working: 0.42 mS/cm display correct
- Schedule integration working: 2.0 mS/cm target from `nutrient_schedule` table
- Backend API documented in `QUICK_REFERENCE.md` and `.github/copilot-instructions.md`
- Original EC fixes in PR #92 (to be closed after this work order)

---

**END OF WORK ORDER**
