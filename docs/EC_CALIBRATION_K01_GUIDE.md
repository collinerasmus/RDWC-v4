# EC Probe Calibration Guide - K=0.1 Probes

## Overview
This guide covers the proper calibration procedure for Atlas Scientific EZO EC circuits with **K=0.1 conductivity probes**. The K=0.1 probe is designed for low-conductivity measurements (0.5 - 50 µS/cm) which is ideal for hydroponic applications.

## Prerequisites

### Required Items
1. **Atlas Scientific EZO EC circuit** (I2C mode, address 0x64)
2. **K=0.1 conductivity probe** (physically labeled K=0.1)
3. **Calibration solutions**:
   - 84 µS/cm calibration solution (low point)
   - 10,000 µS/cm calibration solution (high point, optional but recommended)
4. **Clean rinse water** (distilled or deionized)

### Before You Begin
- Verify the probe is clean and dry
- Check that the K value in system settings is set to **0.1**
- Allow solutions to reach stable temperature (ideally 20-25°C)
- Have a clean container for each calibration solution

## Calibration Procedure

### Step 1: Set K Factor
**This must be done first and only once per probe.**

1. Navigate to the **Sensors** tab in the UI
2. Open **EC Probe Calibration** section
3. In the "Probe Constant (K)" dropdown, select **K=0.1**
4. Click **Set K**
5. Verify the K chip in the header shows **K=0.1** (green indicator)

**Important**: The K value must match your physical probe label. Using the wrong K value will give incorrect readings.

### Step 2: Dry Calibration
**Required for K=0.1 probes.**

1. Remove the probe from all solutions
2. Wipe the probe clean with a lint-free cloth
3. Allow the probe to air dry for **30 seconds minimum**
4. In the UI, click **Calibrate Dry** (Step 1)
5. Wait for success confirmation
6. Verify the dry indicator shows **✓**

### Step 3: Low Point Calibration
**Required for all probes.**

1. Rinse the probe with clean water
2. Place the probe in **84 µS/cm calibration solution**
3. Gently stir and wait **30 seconds** for stabilization
4. In the UI, click **Calibrate Low** (Step 2)
5. Wait for success confirmation
6. Verify the low indicator shows **✓**

### Step 4: High Point Calibration
**Optional but recommended for best accuracy.**

1. Remove probe from low solution
2. Rinse thoroughly with clean water
3. Place the probe in **10,000 µS/cm calibration solution**
4. Gently stir and wait **30 seconds** for stabilization
5. In the UI, click **Calibrate High** (Step 3)
6. Wait for success confirmation
7. Verify the high indicator shows **✓**

### Step 5: Verification
1. Click **Refresh** to check calibration status
2. Verify status shows **"dry+two-point"** (if all steps completed) or **"dry+low"** (if only low point)
3. Place probe in nutrient solution and verify readings are sensible
4. Expected range for hydroponics: 0.5 - 3.0 mS/cm (500 - 3000 µS/cm)

## Calibration Solutions Reference

### For K=0.1 Probes
| Point | Conductivity | Usage |
|-------|-------------|-------|
| Dry | 0 µS/cm (air) | Required baseline |
| Low | 84 µS/cm | Required accuracy point |
| High | 10,000 µS/cm | Optional for extended range |

### For K=1.0 Probes (Reference)
| Point | Conductivity | Usage |
|-------|-------------|-------|
| Low | 1,413 µS/cm | Standard low |
| High | 12,880 µS/cm | Standard high |

## Troubleshooting

### Calibration Fails
- **Error: "Calibration lock held by sensor poller"**
  - The background sensor poller is reading sensors
  - Wait 5 seconds and try again
  - If persistent, check `/tmp/rdwc_calib.lock` exists and remove it

### K Value Resets
- **K value shows 1.0 instead of 0.1**
  - This was fixed in recent updates
  - K value is now persisted to database
  - After setting K=0.1, it will survive restarts

### Readings Seem Wrong
- **Readings 10x too high or too low**
  - Check K value matches physical probe label
  - Wrong K value is the most common cause
  - K=0.1 probe with K=1.0 setting reads 10x too high
  - K=1.0 probe with K=0.1 setting reads 10x too low

- **Readings unstable or drifting**
  - Verify calibration solutions are fresh (not expired)
  - Check probe is clean (no buildup on electrodes)
  - Allow more settling time between steps (60s instead of 30s)
  - Verify temperature is stable

### Probe Not Responding
- **No response to calibration commands**
  - Check I2C connection (address 0x64)
  - Verify probe LED is blue (I2C mode)
  - Try power cycling the sensor rail
  - Check `/api/sensors` endpoint for connectivity

## Maintenance

### Regular Calibration Schedule
- **Initial**: Full 3-point calibration (dry + low + high)
- **Monthly**: Verify with low point solution
- **Quarterly**: Full 3-point recalibration
- **After probe cleaning**: At least low point recalibration
- **After solution changes**: Verify readings, recalibrate if needed

### Probe Cleaning
1. Rinse with clean water
2. Soak in 5% HCl solution for 5 minutes (if mineral buildup)
3. Rinse thoroughly with clean water
4. Recalibrate after cleaning

### Storage
- Store probe in storage solution (NOT distilled water)
- If storing dry, add a few drops of storage solution to cap
- Recalibrate after extended storage (>1 month)

## API Reference

### Endpoints

#### Set K Factor
```bash
POST /api/ec/k
Content-Type: application/json

{
  "k": 0.1
}
```

#### Dry Calibration
```bash
POST /api/ec/cal/dry
```

#### Low Point Calibration
```bash
POST /api/ec/cal/low
Content-Type: application/json

{
  "us_cm": 84
}
```

#### High Point Calibration
```bash
POST /api/ec/cal/high
Content-Type: application/json

{
  "us_cm": 10000
}
```

#### Get Calibration Status
```bash
GET /api/ec/cal/status
```

Response:
```json
{
  "ok": true,
  "k": 0.1,
  "cal": "dry+two-point",
  "dry": true,
  "low": true,
  "high": true,
  "cal_response": "?CAL,3",
  "note": "K factor is source of truth from settings"
}
```

#### Clear Calibration
```bash
POST /api/ec/cal/clear
```

## Technical Details

### EZO EC I2C Commands
- `K,0.1` - Set K factor to 0.1
- `Cal,dry` - Calibrate dry (zero point)
- `Cal,low,84` - Calibrate low point at 84 µS/cm
- `Cal,high,10000` - Calibrate high point at 10,000 µS/cm
- `Cal,clear` - Clear all calibration points
- `Cal,?` - Query calibration status

### Calibration Response Codes
- `?CAL,0` - Uncalibrated
- `?CAL,1` - One-point calibration (low)
- `?CAL,2` - Two-point calibration (low + high)
- `?CAL,3` - Dry + two-point calibration (dry + low + high)

### K Factor Ranges
- **K=0.1**: 0.5 - 50 µS/cm (0.0005 - 0.05 mS/cm)
- **K=1.0**: 5 - 200,000 µS/cm (0.005 - 200 mS/cm)
- **K=10.0**: 100 - 1,000,000 µS/cm (0.1 - 1,000 mS/cm)

## References
- [Atlas Scientific EZO EC Datasheet](https://files.atlas-scientific.com/EC_EZO_Datasheet.pdf) (Pages 40-65)
- [Atlas Scientific Calibration Solutions](https://atlas-scientific.com/conductivity/)
- Repository: `docs/FIX_SUMMARY_EC_K_VALUE.md` - K value persistence fix details

## Change Log

### 2025-01-06
- Updated default calibration values for K=0.1 probes
- Changed low point from 1413 to 84 µS/cm
- Changed high point from 12880 to 10000 µS/cm
- Added dry calibration step (required for K=0.1)
- Enhanced UI with step-by-step wizard
- Added visual indicators for completed calibration steps

### Previous
- K value persistence fixed (see `docs/FIX_SUMMARY_EC_K_VALUE.md`)
- K value now defaults to 0.1 in settings
- K value automatically restored on sensor initialization
