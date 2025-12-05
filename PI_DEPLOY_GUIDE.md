# Pi-First Deployment & Calibration Guide

**Philosophy**: No local dev environment. All changes committed to GitHub → pulled on Pi → tested on real hardware. This guide is the single source of truth for deploying and calibrating the RDWC-v4 system.

---

## Prerequisites

- **Hardware**: Raspberry Pi (SSH access), HMI laptop (web browser at 192.168.88.33)
- **Network**: Pi at 192.168.88.49, port 8080
- **Git**: Repo cloned on Pi at `/home/pi/RDWC-v4` (or your path)
- **Services**: `rdwc.service` (FastAPI), `rdwc-sensors.service` (background poller), `rdwc-watchdog.service`

---

## Standard Deployment Workflow

### 1. Make Changes Locally (Windows)

```powershell
# Edit files in your local repo (VS Code, etc.)
# Commit changes
git add <files>
git commit -m "Brief description of changes"
git push origin main
```

### 2. Deploy to Pi

```bash
# SSH to Pi
ssh pi@192.168.88.49

# Navigate to repo
cd /home/pi/RDWC-v4

# Pull latest changes
git pull origin main

# Restart services (restarts both API and sensor poller)
sudo systemctl restart rdwc rdwc-sensors

# Verify services are running
sudo systemctl status rdwc rdwc-sensors
```

### 3. Verify via API

```bash
# Check health (should return {"status": "ok", "time": "..."})
curl http://localhost:8080/health

# Check sensor poller status
curl http://localhost:8080/api/sensors/status

# Check sensors are reading (should have fresh timestamp <60s)
curl http://localhost:8080/api/sensors
```

### 4. Verify via HMI

Open browser on HMI laptop:
- Navigate to `http://192.168.88.49:8080`
- Check **Sensors** tab: fresh readings, online=true, timestamp <60s
- Check **Relays** panel: E-STOP status, cooldown timers
- Check **System** tab: service status, errors/alerts

---

## EC Calibration Workflow (from HMI UI)

**Context**: This fixes the EC K value persistence issue. EZO EC probes lose their K constant on power cycles. The calibration endpoints now restore K from settings after applying calibration points.

### Prerequisites

1. **Enable Calibration Mode**

   SSH to Pi and create systemd override:
   
   ```bash
   sudo systemctl edit rdwc
   ```
   
   Add to the `[Service]` section:
   
   ```ini
   [Service]
   Environment="CALIB_ENABLE=1"
   ```
   
   Save and exit (Ctrl+X, Y, Enter). Reload and restart:
   
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart rdwc
   ```
   
   Verify calibration is enabled:
   
   ```bash
   curl http://localhost:8080/calib/ph/caps
   # Should return: {"enabled": true}
   ```

2. **Check Baseline EC Reading**

   From HMI browser at `http://192.168.88.49:8080`:
   - Go to **Sensors** tab
   - Note current EC reading (may be incorrect, e.g., 1.29 mS/cm)
   - Verify timestamp is fresh (<60s)

3. **Check Current K Value**

   ```bash
   curl http://192.168.88.49:8080/api/ec/cal/status | jq .
   ```
   
   Look for `"k": 1.0` (or whatever your probe's K value should be). If it shows 0.1, that's the symptom we're fixing.

### Calibration Steps

**You need**: EC 1.413 mS/cm buffer (1413 µS/cm) and optionally EC 12.88 mS/cm buffer (12880 µS/cm) for two-point calibration.

#### Step 1: Clear Calibration (Optional but Recommended)

From HMI browser:
- Navigate to **EC Calibration** tab (or relevant UI section)
- Click **Clear Calibration** button
- API endpoint: `POST /api/ec/cal/clear`
- This resets all cal points and K value to defaults

Or via command line:

```bash
curl -X POST http://192.168.88.49:8080/api/ec/cal/clear
```

#### Step 2: Set K Value (If Known)

If your probe has a specific K value (usually printed on probe or in manual, typically 0.1 to 10):

From HMI browser:
- In **EC Settings** section, find **K Value** input
- Enter your probe's K value (e.g., 1.0)
- Click **Set K** button
- API endpoint: `POST /api/ec/k` with body `{"k": 1.0}`

Or via command line:

```bash
curl -X POST http://192.168.88.49:8080/api/ec/k \
  -H "Content-Type: application/json" \
  -d '{"k": 1.0}'
```

**Note**: If you don't know your probe's K value, use 1.0 as a starting point. You can fine-tune later if readings are consistently off.

#### Step 3: Low-Point Calibration (1.413 mS/cm)

1. **Rinse probe** with distilled water, pat dry gently
2. **Immerse probe** in EC 1.413 mS/cm buffer (1413 µS/cm)
3. **Wait 30-60 seconds** for reading to stabilize
4. From HMI browser:
   - Go to **EC Calibration** tab
   - Enter `1413` in **Low Point (µS/cm)** input
   - Click **Apply Low Calibration** button
   - API endpoint: `POST /api/ec/cal/low` with body `{"us_cm": 1413}`
   - Response will include `k_restored: 1.0` and `k_response: "K=1.0 restored"` confirming K was restored

Or via command line:

```bash
curl -X POST http://192.168.88.49:8080/api/ec/cal/low \
  -H "Content-Type: application/json" \
  -d '{"us_cm": 1413}'
```

Expected response:

```json
{
  "ok": true,
  "response": "Low calibration applied at 1413 µS/cm",
  "k_restored": 1.0,
  "k_response": "K=1.0 restored"
}
```

#### Step 4: Verify Low-Point Calibration

```bash
curl http://192.168.88.49:8080/api/ec/cal/status | jq .
```

Should show:

```json
{
  "low": true,
  "high": false,
  "k": 1.0,
  ...
}
```

#### Step 5: High-Point Calibration (Optional, Two-Point)

If you have EC 12.88 mS/cm buffer (12880 µS/cm):

1. **Rinse probe** thoroughly with distilled water
2. **Immerse probe** in EC 12.88 mS/cm buffer
3. **Wait 30-60 seconds** for reading to stabilize
4. From HMI browser:
   - Enter `12880` in **High Point (µS/cm)** input
   - Click **Apply High Calibration** button
   - API endpoint: `POST /api/ec/cal/high` with body `{"us_cm": 12880}`

Or via command line:

```bash
curl -X POST http://192.168.88.49:8080/api/ec/cal/high \
  -H "Content-Type: application/json" \
  -d '{"us_cm": 12880}'
```

Expected response:

```json
{
  "ok": true,
  "response": "High calibration applied at 12880 µS/cm",
  "k_restored": 1.0,
  "k_response": "K=1.0 restored"
}
```

#### Step 6: Final Verification

```bash
# Check calibration status
curl http://192.168.88.49:8080/api/ec/cal/status | jq .

# Check live reading in reservoir water
curl http://192.168.88.49:8080/api/sensors | jq .ec_mscm
```

From HMI browser:
- Go to **Sensors** tab
- EC reading should now match actual EC of your reservoir water (within ±0.1 mS/cm)
- If reading is still wrong, check K value setting and repeat calibration

#### Step 7: Disable Calibration Mode (After Completing All Calibrations)

Once pH and EC calibrations are complete:

```bash
sudo systemctl edit rdwc
# Remove or comment out the CALIB_ENABLE=1 line
# Save and exit

sudo systemctl daemon-reload
sudo systemctl restart rdwc
```

Verify:

```bash
curl http://localhost:8080/calib/ph/caps
# Should return: {"enabled": false} or 404
```

---

## Troubleshooting

### EC Reading Still Wrong After Calibration

1. **Check K value persisted**:
   ```bash
   curl http://192.168.88.49:8080/api/ec/cal/status | jq .k
   ```
   Should be 1.0 (or your probe's K value), not 0.1.

2. **Check for I²C contention**:
   ```bash
   ls -l /tmp/rdwc_calib.lock
   ```
   If file exists and calibration is failing, sensor poller may be holding lock. Check logs:
   ```bash
   sudo journalctl -u rdwc-sensors -n 50
   ```

3. **Power cycle sensors** (if `RDWC_SENSOR_POWER_PIN` is configured):
   ```bash
   curl -X POST "http://192.168.88.49:8080/api/sensors/power_cycle?off_ms=2000&post_wait_ms=4000&validate=1"
   ```

4. **Check probe is clean**: Rinse with distilled water, gently wipe with soft cloth. Dirty probes give erratic readings.

5. **Verify buffer is fresh**: EC buffers can degrade or evaporate. Use fresh, sealed buffer solution.

### Services Not Starting

```bash
# Check service status
sudo systemctl status rdwc
sudo systemctl status rdwc-sensors

# View recent logs
sudo journalctl -u rdwc -n 100 --no-pager
sudo journalctl -u rdwc-sensors -n 100 --no-pager

# Check for port conflicts
sudo lsof -i :8080
```

### API Not Responding

```bash
# Check if uvicorn process is running
ps aux | grep uvicorn

# Check systemd service
sudo systemctl status rdwc

# Restart
sudo systemctl restart rdwc

# Check logs for errors
sudo journalctl -u rdwc -f
```

---

## Quick Reference: Key Endpoints

### Health & Status

- `GET /health` - API health check
- `GET /api/sensors/status` - Sensor poller status (PID, uptime, last success)
- `GET /api/sensors` - Current sensor readings (cached from DB, max 60s old)
- `GET /diag/sensors/once` - One-shot sensor read (bypasses cache, uses lock)

### EC Calibration

- `GET /api/ec/cal/status` - Current calibration state (low, high, K value)
- `POST /api/ec/cal/clear` - Clear all calibration points
- `POST /api/ec/k` - Set K value: `{"k": 1.0}`
- `POST /api/ec/cal/low` - Apply low calibration: `{"us_cm": 1413}`
- `POST /api/ec/cal/high` - Apply high calibration: `{"us_cm": 12880}`

### pH Calibration

- `GET /calib/ph/caps` - Check if calibration is enabled
- `GET /calib/ph/status` - Current calibration state
- `POST /calib/ph/mid` - Calibrate to pH 7.0: `{"value": 7.0}`
- `POST /calib/ph/low` - Calibrate to pH 4.0: `{"value": 4.0}`
- `POST /calib/ph/high` - Calibrate to pH 10.0: `{"value": 10.0}`
- `POST /calib/ph/clear` - Clear all pH calibration

### Relays

- `GET /api/relays/status` - All relay states, E-STOP, cooldowns
- `POST /api/relays/estop/toggle` - Toggle emergency stop

### Settings

- `GET /api/settings` - All settings
- `POST /api/settings/import` - Bulk import settings: `{"key": "value", ...}`

---

## Notes

- **Always commit → push → pull → restart** for code changes
- **Always verify** after deployment via `/health`, `/api/sensors/status`, HMI UI
- **Calibration lock** (`/tmp/rdwc_calib.lock`) prevents I²C contention between API calibration and background poller
- **K value restoration** happens at two points: (1) sensor startup (`init_once()`), (2) after each calibration point
- **CALIB_ENABLE=1** is required for calibration writes—set via systemd override, disable after calibrations complete
- **No dev environment**: Never run uvicorn locally for hardware operations—always test on Pi with real sensors

---

## EC Calibration Fix Details (Technical Context)

**Problem**: EZO EC probes don't persist K values across power cycles or resets. After calibration, K would revert to 0.1 (default), causing incorrect EC readings.

**Solution**: Modified `/api/ec/cal/low` and `/api/ec/cal/high` endpoints in `app/main.py` to restore K value from settings (`ec.k_value`) immediately after applying calibration points.

**Code Flow**:
1. Acquire calibration lock (`/tmp/rdwc_calib.lock`)
2. Apply calibration command: `Cal,low,1413` or `Cal,high,12880`
3. Sleep 0.5s for EZO to settle
4. Read K value from settings: `get_all_settings().get("ec.k_value", "1.0")`
5. Restore K to probe: `ec_dev.cmd(f"K,{k_value:.2f}")`
6. Return response with `k_restored` and `k_response` fields
7. Release lock

**Verification**: Check `/api/ec/cal/status` for `"k": 1.0` and live EC reading in `/api/sensors` should match actual reservoir EC.

**Commit Reference**: Search git log for "Fix EC calibration K value persistence" or check `app/main.py` lines 4123-4220.

---

**End of Guide**
