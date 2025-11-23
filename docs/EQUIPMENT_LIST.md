# RDWC Equipment List

**Document**: EQ-001  
**System**: RDWC v4 Bill of Materials  
**Date**: 2025-11-23  
**Revision**: As-Built v1.0  

---

## Controller & Computing

| Tag | Description | Manufacturer | Model | Qty | Specifications | Source | Notes |
|-----|-------------|--------------|-------|-----|----------------|--------|-------|
| CPU-001 | Main Controller | Raspberry Pi Foundation | Raspberry Pi 4 Model B | 1 | 4GB RAM, BCM2711 quad-core 1.5GHz, WiFi/Ethernet, 40-pin GPIO | raspberrypi.com | Runs Raspberry Pi OS |
| PWR-001 | Pi Power Supply | TBD | USB-C 5V 3A | 1 | 15W minimum | TBD | Official Pi adapter recommended |
| SD-001 | Storage | TBD | microSD Card 32GB+ | 1 | Class 10, A1 rated | TBD | System and database storage |
| CASE-001 | Enclosure | TBD | Waterproof case | 1 | IP54+ rating | TBD | Protect electronics from moisture |

---

## Sensor Suite (Atlas Scientific EZO)

| Tag | Description | Manufacturer | Model | Qty | Specifications | Source | Calibration | Notes |
|-----|-------------|--------------|-------|-----|----------------|--------|-------------|-------|
| TI-101 | RTD Temperature | Atlas Scientific | EZO-RTD | 1 | I²C 0x66, PT-1000 probe, 0-100°C, ±0.1°C | atlas-scientific.com | Factory (1-point verify) | Feeds temp compensation |
| AI-102 | pH Sensor | Atlas Scientific | EZO-pH | 1 | I²C 0x63, glass electrode, 0-14 pH, ±0.02 pH | atlas-scientific.com | 3-point (4.0/7.0/10.0) | Requires KCl storage solution |
| AI-103 | EC Sensor | Atlas Scientific | EZO-EC | 1 | I²C 0x64, K=1.0 cell, 0-10,000 µS/cm, ±2% | atlas-scientific.com | 2-point (dry/1413) | Temperature compensated |
| PROBE-101 | Temperature Probe | Atlas Scientific | PT-1000 RTD | 1 | Platinum RTD, 3-wire | atlas-scientific.com | Factory | BNC connector |
| PROBE-102 | pH Electrode | Atlas Scientific | Lab-grade pH probe | 1 | Glass, Ag/AgCl reference, BNC | atlas-scientific.com | User (buffers) | Lifespan ~1-2 years |
| PROBE-103 | EC Cell | Atlas Scientific | K=1.0 conductivity cell | 1 | 2-electrode, BNC | atlas-scientific.com | User (dry + standard) | Clean regularly |
| BUF-102A | pH 4.0 Buffer | TBD | pH 4.0 calibration | 1 | 250mL bottle | TBD | N/A | Store sealed |
| BUF-102B | pH 7.0 Buffer | TBD | pH 7.0 calibration | 1 | 250mL bottle | TBD | N/A | Store sealed |
| BUF-102C | pH 10.0 Buffer | TBD | pH 10.0 calibration | 1 | 250mL bottle | TBD | N/A | Store sealed |
| BUF-103 | EC 1413 Standard | TBD | EC 1413 µS/cm | 1 | 250mL bottle | TBD | N/A | Store sealed |
| STOR-102 | pH Storage Solution | TBD | KCl storage solution | 1 | 250mL bottle | TBD | N/A | Keep probe submerged |

---

## Relay & Control Hardware

| Tag | Description | Manufacturer | Model | Qty | Specifications | Source | Notes |
|-----|-------------|--------------|-------|-----|----------------|--------|-------|
| RLY-001 | Relay Board | TBD | 8-Channel 5V Relay Module | 1 | Active-low, opto-isolated, 250VAC 10A per channel | Amazon/AliExpress | Must be 3.3V logic compatible |
| CONN-001 | GPIO Ribbon Cable | TBD | 40-pin ribbon cable | 1 | 20cm length | TBD | Pi to relay board |
| CONN-002 | Dupont Jumper Wires | TBD | M-F jumper wires | 20 | 22AWG, 20cm | TBD | GPIO to relay individual pins |
| PULL-001 | I²C Pull-up Resistors | TBD | 4.7kΩ resistors | 2 | 1/4W, ±5% | TBD | Usually onboard Pi/EZO |

---

## Dosing System

| Tag | Description | Manufacturer | Model | Qty | Specifications | Source | Calibration | Notes |
|-----|-------------|--------------|-------|-----|----------------|--------|-------------|-------|
| PP-201 | pH UP Pump | TBD | Peristaltic pump 12VDC | 1 | ~5 mL/s, food-safe tubing | Amazon | User via API | Typically <60s doses |
| PP-202 | Micro Nutrient Pump | TBD | Peristaltic pump 12VDC | 1 | ~5 mL/s, food-safe tubing | Amazon | User via API | Once/day dosing |
| PP-203 | Grow Nutrient Pump | TBD | Peristaltic pump 12VDC | 1 | ~5 mL/s, food-safe tubing | Amazon | User via API | Once/day dosing |
| PP-204 | Bloom Nutrient Pump | TBD | Peristaltic pump 12VDC | 1 | ~5 mL/s, food-safe tubing | Amazon | User via API | Once/day dosing |
| PWR-201 | Pump Power Adapters | TBD | 12VDC 2A adapters | 4 | AC to DC, 12V regulated | Amazon | N/A | One per pump or shared |
| TUBE-201 | Dosing Tubing | TBD | Silicone tubing | 4m | Food-safe, 4mm ID | Amazon | N/A | Replace every 6-12 months |
| CHEM-201 | pH UP Solution | General Hydroponics | pH UP (Potassium Hydroxide) | 1L | Concentrated base | Hydro store | N/A | Handle with care |
| CHEM-202 | Micro Nutrients | TBD | TDS/EC concentrate | 1L | NPK + micronutrients | Hydro store | N/A | Follow manufacturer dilution |
| CHEM-203 | Grow Nutrients | TBD | Vegetative NPK formula | 1L | High nitrogen | Hydro store | N/A | Follow manufacturer dilution |
| CHEM-204 | Bloom Nutrients | TBD | Flowering NPK formula | 1L | High phosphorus/potassium | Hydro store | N/A | Follow manufacturer dilution |

---

## Circulation System

| Tag | Description | Manufacturer | Model | Qty | Specifications | Source | Notes |
|-----|-------------|--------------|-------|-----|----------------|--------|-------|
| P-301 | Main Circulation Pump | TBD | Submersible pump 120VAC | 1 | ~1000 L/hr, 50W | Hydro store | SAFETY CRITICAL - always run |
| P-302 | Chiller Circulation Pump | TBD | Submersible pump 120VAC | 1 | ~500 L/hr, 30W | Hydro store | Interlocked with P-301 |
| TUBE-301 | Main Circulation Tubing | TBD | PVC flex tubing | 5m | 1" ID, food-safe | Hydro store | Replace if degraded |
| TUBE-302 | Chiller Loop Tubing | TBD | PVC flex tubing | 3m | 3/4" ID, food-safe | Hydro store | Replace if degraded |
| CLAMP-301 | Hose Clamps | TBD | Stainless steel clamps | 10 | 1" and 3/4" sizes | Hardware store | Secure all connections |

---

## Temperature Control

| Tag | Description | Manufacturer | Model | Qty | Specifications | Source | Notes |
|-----|-------------|--------------|-------|-----|----------------|--------|-------|
| C-401 | Water Chiller | TBD | Aquarium/hydro chiller | 1 | ~200W, 100L capacity, 120VAC | Hydro store | Interlocked with P-301 |
| COOL-401 | Chiller Coolant | TBD | Refrigerant (sealed system) | N/A | R134a or equivalent | Pre-filled | Do not service user-side |

---

## Lighting System

| Tag | Description | Manufacturer | Model | Qty | Specifications | Source | Notes |
|-----|-------------|--------------|-------|-----|----------------|--------|-------|
| L-501 | Grow Lights | TBD | LED grow light 120VAC | 1 | ~600W, full spectrum | Hydro store | Protected relay (schedule only) |
| MOUNT-501 | Light Hangers | TBD | Adjustable ratchet hangers | 2 | 150lb capacity | Hydro store | Adjust height as plants grow |

---

## Reservoir & Plumbing

| Tag | Description | Manufacturer | Model | Qty | Specifications | Source | Notes |
|-----|-------------|--------------|-------|-----|----------------|--------|-------|
| TANK-001 | Main Reservoir | TBD | Food-safe reservoir | 1 | 100L capacity, opaque | Hydro store | Light-proof to prevent algae |
| LID-001 | Reservoir Lid | TBD | Tight-fitting lid | 1 | Light-proof, access ports | Hydro store | Probe penetrations |
| VALVE-001 | Ball Valves | TBD | PVC ball valves | 4 | 1" size | Hardware store | Isolation for maintenance |
| FILTER-001 | Inline Filter | TBD | 100 mesh screen filter | 1 | 1" size | Hydro store | Prevent pump clogging |

---

## Networking & Power

| Tag | Description | Manufacturer | Model | Qty | Specifications | Source | Notes |
|-----|-------------|--------------|-------|-----|----------------|--------|-------|
| NET-001 | Ethernet Cable | TBD | Cat5e/Cat6 cable | 1 | 5m length | TBD | Wired connection preferred |
| NET-002 | Network Switch | TBD | Gigabit switch | 1 | 5-port | TBD | Optional if WiFi used |
| PWR-002 | Power Strip | TBD | GFCI power strip | 1 | 6+ outlets, GFCI protected | Hardware store | Water-safe outlets |
| UPS-001 | Uninterruptible Power Supply | TBD | UPS 600VA+ | 1 | Battery backup, surge protection | Electronics store | Protect against power outages |

---

## Spare Parts & Consumables

| Description | Qty | Reorder Frequency | Source | Notes |
|-------------|-----|-------------------|--------|-------|
| pH Probe | 1 | Every 12-24 months | atlas-scientific.com | Degrades over time |
| EC Probe | 1 | Every 24-36 months | atlas-scientific.com | More robust than pH |
| pH Buffer Set (4/7/10) | 1 set | Every 6 months | TBD | For recalibration |
| EC 1413 Standard | 1 bottle | Every 6 months | TBD | For recalibration |
| pH Storage Solution | 1 bottle | Every 3 months | TBD | Keep probe wet |
| Dosing Pump Tubing | 4m | Every 6-12 months | Amazon | Wear item |
| microSD Card (backup) | 1 | As needed | TBD | System backup |
| Relay Board (spare) | 1 | As needed | Amazon | Critical component |

---

## Tools & Test Equipment

| Description | Model | Qty | Source | Notes |
|-------------|-------|-----|--------|-------|
| pH Meter (portable) | TBD | 1 | TBD | For verifying probe readings |
| EC Meter (portable) | TBD | 1 | TBD | For verifying probe readings |
| Multimeter | TBD | 1 | Hardware store | Electrical troubleshooting |
| I²C Scanner | Software | N/A | GitHub | `i2cdetect -y 1` |
| Graduated Cylinder | 100mL | 1 | Lab supply | Dosing pump calibration |
| Syringe | 60mL | 2 | Pharmacy | Manual dosing/sampling |

---

## Safety Equipment

| Description | Qty | Source | Notes |
|-------------|-----|--------|-------|
| Safety Glasses | 2 | Hardware store | When handling chemicals |
| Chemical-resistant Gloves | 2 pairs | Hardware store | When handling pH UP |
| First Aid Kit | 1 | Pharmacy | For chemical exposure |
| Fire Extinguisher (ABC) | 1 | Hardware store | Near electrical/chemicals |
| Spill Kit | 1 | Lab supply | Absorbent pads, neutralizer |

---

## Installation & Commissioning

### Required Before First Power-On
- [ ] All electrical connections verified (no exposed terminals)
- [ ] GFCI outlets tested
- [ ] Reservoir filled with clean water (no nutrients yet)
- [ ] All probes submerged in reservoir
- [ ] Pumps primed (no airlocks)
- [ ] Hose clamps tight (no leaks)
- [ ] GPIO connections correct (BCM pin numbers verified)
- [ ] I²C devices detected (`i2cdetect -y 1`)

### Calibration Order
1. Temperature (RTD) - verify factory calibration
2. pH - 3-point calibration (4.0, 7.0, 10.0)
3. EC - 2-point calibration (dry, 1413 µS/cm)
4. Dosing pumps - measure flow rate per second

### Break-In Period
- Run circulation 24 hours before adding nutrients
- Verify no leaks under pressure
- Monitor temperature stability
- Check sensor readings every hour initially

---

## Lifecycle & Replacement Schedule

| Component | Expected Lifespan | Replacement Indicators | Cost Estimate |
|-----------|-------------------|------------------------|---------------|
| pH Probe | 12-24 months | Slow response, slope <95% | $60-100 |
| EC Probe | 24-36 months | Erratic readings, drift | $50-80 |
| Dosing Tubing | 6-12 months | Cracks, stiffness, leaks | $10-20 |
| Main Pump | 24-48 months | Reduced flow, noise, heat | $50-100 |
| Chiller Pump | 24-48 months | Reduced flow, noise, heat | $30-60 |
| Relay Board | 36-60 months | Stuck contacts, no switching | $15-30 |
| Chiller Unit | 60+ months | Insufficient cooling, compressor failure | $200-400 |
| Raspberry Pi | 60+ months | SD card corruption, overheating | $50-80 |

---

## Procurement Notes

### Critical Lead Times
- Atlas Scientific EZO sensors: 1-2 weeks (direct from manufacturer)
- Calibration buffers: 1-3 days (Amazon/local hydro store)
- Raspberry Pi 4: 1-2 weeks (supply chain dependent)
- Relay boards: 1-3 days (Amazon Prime available)

### Budget Estimate (New Build)
- Controller & sensors: $400-500
- Dosing system: $200-300
- Circulation & chiller: $400-600
- Lighting: $300-500
- Plumbing & misc: $100-200
- **Total**: $1400-2100 USD

### Recommended Suppliers
- Atlas Scientific: sensors, probes, calibration solutions
- Amazon: pumps, tubing, relay boards, cables
- Local hydro store: nutrients, reservoir, grow lights
- Raspberry Pi Foundation: official Pi 4, accessories
- DigiKey/Mouser: electronic components, connectors

---

## Warranty & Support

| Component | Warranty Period | Support Contact |
|-----------|-----------------|-----------------|
| Atlas Scientific EZO | 1 year | support@atlas-scientific.com |
| Raspberry Pi | 1 year | raspberrypi.com/support |
| Relay Boards | 30-90 days | Varies by supplier |
| Pumps/Chiller | 90 days - 1 year | Manufacturer specific |

---

## Document Control

**Revision History**:
- v1.0 (2025-11-23): Initial equipment list template created from as-built codebase

**Approval**:
- [ ] User to populate TBD fields with actual part numbers
- [ ] User to verify all specifications match installed hardware
- [ ] User to update costs and suppliers based on actual purchases

---

**End of Equipment List**
