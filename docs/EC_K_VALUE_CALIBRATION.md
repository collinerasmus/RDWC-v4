# EC Sensor K Value Calibration

## Overview
The EC sensor probe constant (K value) determines the measurement range and accuracy of the EC probe. This value needs to be set correctly for your specific probe type and must persist across system restarts.

## K Value Options
Atlas Scientific EC probes come with different K values based on their measurement range:

- **K = 0.1**: For low conductivity measurements (0.5 - 50 µS/cm)
- **K = 1.0**: For standard range (5 - 200,000 µS/cm) - **Default**
- **K = 10**: For high conductivity (100 µS/cm - 1,000,000 µS/cm)

## Setting the K Value

### Via Web UI (Recommended)
1. Navigate to the **EC** tab
2. Click on **Calibration** section
3. Click **Set K** button
4. Enter your probe's K value (e.g., `0.1` for low range probe)
5. Click OK

The K value will be:
- Sent to the EC sensor device immediately
- Saved to the database settings (`ec.k_value`)
- Automatically restored on sensor initialization/restart

### Via API
```bash
curl -X POST http://localhost:8080/api/ec/k \
  -H "Content-Type: application/json" \
  -d '{"k": 0.1}'
```

Response:
```json
{
  "ok": true,
  "response": "OK",
  "k_value": 0.1
}
```

### Via Settings Database
You can also manually update the setting in the database:

```python
from app.settings import upsert_settings

upsert_settings({"ec.k_value": "0.1"})
```

## Checking Current K Value

### Via Web UI
1. Navigate to the **EC** tab
2. Click **Calibration Status** button
3. The K value will be displayed from the persisted settings

### Via API
```bash
curl http://localhost:8080/api/ec/cal/status
```

Response:
```json
{
  "ok": true,
  "cal": "unknown",
  "k": 0.1,
  "note": "Probe does not respond to query commands (Cal,? K,?) - K value from settings"
}
```

## Persistence Behavior

### Before This Fix
- K value was only set on the device temporarily
- After sensor poller restart or power cycle, K value would reset to default (1.0)
- User had to manually re-set K value after each restart

### After This Fix
- K value is persisted to the `settings` table in the database
- On sensor initialization (`EZO.init_once()`), K value is automatically restored from settings
- K value survives:
  - Sensor poller restarts
  - Main application restarts
  - Sensor power cycles
  - System reboots

## Troubleshooting

### K Value Keeps Resetting
If your K value keeps resetting after the fix:

1. **Check the database setting**:
   ```bash
   sqlite3 data/rdwc.db "SELECT value FROM settings WHERE key='ec.k_value';"
   ```

2. **Verify sensor initialization logs**:
   Look for log messages like:
   ```
   INFO: EC probe K value restored to 0.1 from settings
   ```

3. **Manually verify the setting**:
   ```bash
   curl http://localhost:8080/api/ec/cal/status
   ```

### Wrong K Value Set
To correct a wrong K value:

1. Set the correct value via UI or API (see above)
2. Restart the sensor poller to force re-initialization:
   ```bash
   sudo systemctl restart rdwc-sensors
   ```

3. Verify the new value is active:
   ```bash
   curl http://localhost:8080/api/ec/cal/status
   ```

## Technical Details

### Implementation
- **Settings default**: `ec.k_value = "1.0"` in `app/settings.py`
- **API endpoint**: `/api/ec/k` in `app/main.py`
- **Restoration logic**: `EZO.init_once()` in `app/ezo_i2c_stabilized.py`
- **Status endpoint**: `/api/ec/cal/status` in `app/main.py`

### Files Modified
- `app/settings.py` - Added `ec.k_value` default
- `app/main.py` - Updated endpoints to persist and retrieve k value
- `app/ezo_i2c_stabilized.py` - Added k value restoration on init
- `tests/test_ec_k_value_persistence.py` - Comprehensive test suite

## References
- [Atlas Scientific EC Circuit Datasheet](https://atlas-scientific.com/files/EC_EZO_Datasheet.pdf)
- [Atlas Scientific Calibration Guide](https://atlas-scientific.com/calibration/)
