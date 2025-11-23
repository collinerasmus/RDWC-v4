# RDWC Electrical Schematics

**Document**: EL-001  
**System**: RDWC v4 Electrical System  
**Date**: 2025-11-22  
**Revision**: As-Built v1.0  

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    5V Power Supply                            │
│                    (Wall Adapter or PSU)                      │
└────────────┬──────────────────────────────────────────────────┘
             │
             │ +5V
             ├──────────────────────┬──────────────────────┐
             │                      │                      │
    ┌────────▼─────────┐   ┌───────▼────────┐   ┌────────▼────────┐
    │  Raspberry Pi 4  │   │  8-Ch Relay    │   │  Atlas EZO      │
    │                  │   │  Board         │   │  Sensor Suite   │
    │  BCM2711         │   │  (Active-Low)  │   │                 │
    │                  │   │                │   │  ┌──────────┐   │
    │  I²C: /dev/i2c-1 │───┤  I²C Bus       │   │  │ RTD 0x66 │   │
    │  SDA: GPIO 2     │   │  SDA/SCL       │───┼──┤ pH  0x63 │   │
    │  SCL: GPIO 3     │   │  Pull-up 4.7kΩ │   │  │ EC  0x64 │   │
    │                  │   │                │   │  └──────────┘   │
    │  GPIO Outputs:   │   │                │   │                 │
    │  ┌─────────────┐ │   │  Relay Inputs: │   │  3.3V Logic    │
    │  │ GPIO 5  ────┼─┼───┼──► CH1 (pH UP)│   │  5V Power       │
    │  │ GPIO 6  ────┼─┼───┼──► CH2 (Grow) │   └─────────────────┘
    │  │ GPIO 13 ────┼─┼───┼──► CH3 (Micro)│
    │  │ GPIO 16 ────┼─┼───┼──► CH4 (Chiller Pump)
    │  │ GPIO 19 ────┼─┼───┼──► CH5 (Bloom)│
    │  │ GPIO 20 ────┼─┼───┼──► CH6 (Chiller)
    │  │ GPIO 21 ────┼─┼───┼──► CH7 (Lights)
    │  │ GPIO 26 ────┼─┼───┼──► CH8 (Main Pump)
    │  └─────────────┘ │   │                │
    │                  │   │  Relay Outputs:│
    │  3.3V Logic      │   │  COM/NO/NC     │
    │  Ground Common   │   │  250VAC 10A    │
    └──────────────────┘   └────────┬───────┘
                                    │
                                    │ 120VAC Switched
                                    ├──────────────────┐
                                    │                  │
                         ┌──────────▼───────┐  ┌──────▼──────┐
                         │  Dosing Pumps    │  │  Circulation │
                         │  PP-201..204     │  │  P-301, P-302│
                         │                  │  │  C-401       │
                         │  12VDC via       │  │  L-501       │
                         │  AC Adapters     │  │              │
                         └──────────────────┘  └──────────────┘
```

---

## Raspberry Pi GPIO Pinout (BCM Mode)

### GPIO Pin Assignments

| GPIO (BCM) | Physical Pin | Function | Relay Channel | Load |
|------------|--------------|----------|---------------|------|
| GPIO 5 | 29 | Output | CH1 | pH UP Pump (PP-201) |
| GPIO 6 | 31 | Output | CH2 | Grow Nutrient Pump (PP-203) |
| GPIO 13 | 33 | Output | CH3 | Micro Nutrient Pump (PP-202) |
| GPIO 19 | 35 | Output | CH5 | Bloom Nutrient Pump (PP-204) |
| GPIO 26 | 37 | Output | CH8 | Main Circulation Pump (P-301) |
| GPIO 16 | 36 | Output | CH4 | Chiller Pump (P-302) |
| GPIO 20 | 38 | Output | CH6 | Water Chiller (C-401) |
| GPIO 21 | 40 | Output | CH7 | Grow Lights (L-501) |
| GPIO 2 | 3 | I²C SDA | I²C Bus | Sensor Communication |
| GPIO 3 | 5 | I²C SCL | I²C Bus | Sensor Communication |

### Power Pins
| Physical Pin | Function | Notes |
|--------------|----------|-------|
| Pin 2, 4 | +5V | Power from USB-C or GPIO header |
| Pin 6, 9, 14, 20, 25, 30, 34, 39 | GND | Common ground |
| Pin 1, 17 | +3.3V | Low-current logic power |

---

## Relay Board Wiring

### Active-Low Configuration
## Relay Board Behavior (Updated Mixed NC / NO Wiring)

Relays remain active-low at the signal layer; wiring now distinguishes fail-safe outcomes:

| Channel | Device | Tag | GPIO | Wiring | Fail (Power/Controller Loss) | Intended Outcome |
|---------|--------|-----|------|--------|------------------------------|------------------|
| CH1 | pH UP pump | PP-201 | 5 | NO | OFF | No unintended chemical dosing |
| CH2 | Micro nutrient pump | PP-202 | 13 | NO | OFF | Prevent nutrient overshoot |
| CH3 | Grow nutrient pump | PP-203 | 6 | NO | OFF | Prevent nutrient overshoot |
| CH4 | Bloom nutrient pump | PP-204 | 19 | NO | OFF | Prevent nutrient overshoot |
| CH5 | Main circulation pump | P-301 | 26 | NC | ON | Maintain oxygenation & mixing |
| CH6 | Chiller circulation pump | P-302 | 16 | NC | ON | Preserve cooling loop circulation |
| CH7 | Water chiller | C-401 | 20 | NC | ON | Prevent rapid temperature rise |
| CH8 | Grow lights | L-501 | 21 | NO | OFF | Avoid photoperiod disruption |

Rationale:
- Critical flow & temperature assets: NC (fail-ON)
- Chemical & photoperiod assets: NO (fail-OFF)

Startup Reconciliation:
On boot the controller compares expected logical states with physical defaults; mismatches logged through relay guard.

### Relay Module Specifications
- **Model**: 8-Channel 5V Relay Module (typical)
- **Control Voltage**: 3.3V compatible (opto-isolated)
- **Switching Capacity**: 250VAC 10A, 30VDC 10A (per channel)
- **Isolation**: Opto-couplers isolate control from load side
- **Indicators**: LED per channel shows relay state

### Wiring Per Channel
```
Pi GPIO Pin ──► Relay IN Pin (CH1-CH8)
               │
               │ Opto-Coupler (active-low)
               ▼
           Relay Coil
               │
               │ Mechanical Contacts
               ├── COM (Common)
               ├── NO (Normally Open) ──► Load (+)
               └── NC (Normally Closed) [Not Used]

120VAC Line ──► Relay NO ──► Load ──► Neutral
```

### Load Connections

| Relay CH | Load | Power Type | Notes |
|----------|------|------------|-------|
| CH1 | pH UP Pump | 12VDC via AC adapter | Switched on AC side |
| CH2 | Grow Pump | 12VDC via AC adapter | Switched on AC side |
| CH3 | Micro Pump | 12VDC via AC adapter | Switched on AC side |
| CH4 | Chiller Pump | 120VAC | Direct switching |
| CH5 | Bloom Pump | 12VDC via AC adapter | Switched on AC side |
| CH6 | Water Chiller | 120VAC | High current (~2A) |
| CH7 | Grow Lights | 120VAC | High current (~5A) |
| CH8 | Main Pump | 120VAC | High current (~1A) |

---

## I²C Bus Schematic

### Bus Configuration
```
            +3.3V
              │
          ┌───┴───┐
       4.7kΩ   4.7kΩ   Pull-up Resistors
          │       │
        SDA ──┬───┴──┬──────┬────── SCL
              │      │      │
          ┌───▼──────▼──────▼────┐
          │   Raspberry Pi        │
          │   GPIO 2 (SDA)        │
          │   GPIO 3 (SCL)        │
          └───┬──────┬──────┬─────┘
              │      │      │
          ┌───▼───┐ │  ┌───▼────┐
          │ RTD   │ │  │ EC     │
          │ 0x66  │ │  │ 0x64   │
          └───────┘ │  └────────┘
                 ┌──▼───┐
                 │ pH   │
                 │ 0x63 │
                 └──────┘
```

### I²C Device Table

| Device | Address | Speed | Power | Data Rate |
|--------|---------|-------|-------|-----------|
| RTD Temperature | 0x66 | 100kHz | 5V | 1 reading/s |
| pH Sensor | 0x63 | 100kHz | 5V | 1 reading/s |
| EC Sensor | 0x64 | 100kHz | 5V | 1 reading/s |

### Atlas EZO Sensor Wiring (per device)
```
┌─────────────────┐
│  Atlas EZO      │
│  (e.g., pH)     │
├─────────────────┤
│ VCC ─────► 5V   │  Power (5V recommended, 3.3V compatible)
│ GND ─────► GND  │  Ground (common with Pi)
│ SDA ─────► SDA  │  Data (GPIO 2, pin 3)
│ SCL ─────► SCL  │  Clock (GPIO 3, pin 5)
│ TX  ──── [NC]   │  Not used in I²C mode
│ RX  ──── [NC]   │  Not used in I²C mode
│ PRB ─────► BNC  │  Probe connection (pH/EC/RTD)
└─────────────────┘
```

**Pull-up Resistors**: 4.7kΩ on SDA and SCL lines (usually onboard the Pi or EZO modules).

---

## Power Distribution

### 5V Rail
- **Source**: USB-C power adapter (5V 3A minimum)
- **Consumers**:
  - Raspberry Pi 4: ~600mA idle, ~1.2A under load
  - Relay Board: ~200mA (LEDs + opto-couplers)
  - Atlas EZO Sensors (3x): ~50mA each = 150mA
  - **Total**: ~2A typical, 3A peak

### 12VDC Rail (Dosing Pumps)
- **Source**: 120VAC → 12VDC power adapters (one per pump, or shared)
- **Switching**: Via relay board on AC side (before adapters)
- **Consumers**:
  - Each peristaltic pump: ~200-500mA @ 12V

### 120VAC Loads
- **Main Pump**: ~50W (~0.4A @ 120V)
- **Chiller Pump**: ~30W (~0.25A @ 120V)
- **Water Chiller**: ~200W (~1.7A @ 120V)
- **Grow Lights**: ~600W (~5A @ 120V)

### Fusing & Protection
- **Pi 5V Rail**: Polyfuse or 3A fuse
- **Relay Board 5V**: 500mA fuse (if separate supply)
- **120VAC Loads**: Individual 10A circuit breakers per high-current load (lights, chiller)
- **Ground Fault Protection**: GFCI outlet recommended for water proximity

---

## Sensor Power Options

Some systems may implement a GPIO-controlled relay to power-cycle the sensor rail:

```
GPIO X ──► Relay (Sensor Power) ──► 5V to Atlas EZO modules
```

This allows software recovery from sensor lockups via:
```
POST /api/sensors/power_cycle?off_ms=2000&post_wait_ms=4000&validate=1
```

Configured via env var:
```
RDWC_SENSOR_POWER_PIN=X  # GPIO pin number (BCM)
```

---

## Cable Specifications

| Cable Type | Length | Spec | Use |
|------------|--------|------|-----|
| I²C Bus | <1m | 22AWG, shielded, twisted pair | Minimize noise in wet environment |
| GPIO to Relay | 0.3m | 24AWG ribbon or dupont | Short runs reduce voltage drop |
| AC Power (Pumps) | 2m | 18AWG, SJTW rated | Outdoor/damp location rated |
| AC Power (Lights) | 3m | 14AWG, SJTW rated | High current (5A) |
| BNC Probe Cables | 1m | Atlas EZO supplied | pH/EC/RTD probe to EZO board |

---

## Grounding & Safety

1. **Common Ground**: All devices share common ground (Pi, relay board, sensors, AC neutral)
2. **Isolation**: Relay board opto-isolates Pi logic from AC loads
3. **GFCI Protection**: All 120VAC outlets should be GFCI (water proximity)
4. **Enclosure**: Electronics in waterproof or splash-proof enclosure (IP54+)
5. **No Exposed Terminals**: All AC wiring in conduit or enclosed junction boxes
6. **Emergency Stop**: Physical E-STOP button (optional) wired to Pi shutdown or relay board disable

---

## Troubleshooting

### Relay Not Switching
- Check GPIO state: `gpio readall` or `/api/relays/status`
- Verify opto-coupler: LED on relay board should light when GPIO LOW
- Test continuity: COM to NO should close when relay energized
- Check load power: is AC live? Is adapter outputting DC?

### I²C Communication Failures
- Check wiring: SDA/SCL correct? Pull-ups present?
- Scan bus: `i2cdetect -y 1` should show 0x63, 0x64, 0x66
- Check addresses: Atlas EZO default addresses (change if conflicts)
- Check power: All sensors powered? Ground common?

### Power Issues
- Pi brownout (lightning bolt): Insufficient 5V supply (need 3A minimum)
- Relay board not responding: Check 5V to VCC pin, ground connected
- Sensors offline: Check 5V rail with multimeter, reseat cables

---

## Modifications & Upgrades

### Optional Sensor Power Control
Add a 9th relay channel to switch 5V to sensor rail:
- GPIO X → Relay CH9 → 5V to Atlas EZO modules
- Enables software power-cycle recovery
- Set `RDWC_SENSOR_POWER_PIN=X` in env

### Optional Physical E-STOP
Wire a normally-closed pushbutton to GPIO input (pull-up):
- GPIO Y → NC button → GND
- GPIO Y reads HIGH (3.3V) when button not pressed
- GPIO Y reads LOW (0V) when button pressed → trigger E-STOP
- Software polls GPIO Y every 100ms

### Expandability
- Additional GPIO pins available for future sensors (flow meters, level switches)
- I²C bus can support up to 128 devices (unique addresses required)
- Relay board can be expanded to 16 or 32 channels (via I²C relay boards)

---

**End of Electrical Schematic Document**
