# EC Control v1.0

## Overview

The EC (Electrical Conductivity) Control system manages nutrient levels in the RDWC reservoir through automated and manual dosing of three nutrient solutions: Grow, Micro, and Bloom.

## Hardware

- **EC Sensor**: Atlas Scientific EZO-EC (I²C address: 0x64)
- **RTD Temperature Sensor**: Atlas Scientific PT-1000 (I²C address: 0x66)
- **Dosing Pumps** (Peristaltic, active-low relays):
  - Grow: BCM GPIO 6
  - Micro: BCM GPIO 13
  - Bloom: BCM GPIO 19

## Manual Dosing

### Endpoints

**POST /api/ec/dose** - Dose nutrients manually

Supports two modes:

1. **pump + seconds** (primary):
```json
{
  "pump": "grow" | "micro" | "bloom",
  "seconds": 0.5,
  "reason": "manual-smoke"
}
```

2. **ml + mix_ratio** (legacy):
```json
{
  "ml": 50,
  "mix_ratio": "schedule" | "custom",
  "reason": "manual"
}
```

### Guard Rails

All dosing enforces these safety gates:

- **E-STOP**: `safety.estop == true` blocks all dosing
- **Enabled Check**: Requires `ec.enabled == true` OR `ec.maintenance_override == true`
- **Reservoir**: Blocks if `general.reservoir_liters <= 0`
- **Sensor Stale**: Blocks if EC reading > 5 minutes old
- **Mix Lock**: Single pump at a time (mutex with pH dosing)
- **Seconds Clamp**: 0.1-5.0s normal, up to 10.0s with override
- **Min Interval**: `ec.min_interval_sec` between doses per pump
- **Daily Cap**: `ec.max_ml_day` total volume limit

### UI Controls

- Manual tab: Quick dose buttons (10/50/100ml) or custom volume
- Mix ratio selector: Schedule (follows grow phase) or Custom (G/M/B ratios)
- Maintenance override badge: Shows when `ec.maintenance_override == true`
- Freshness indicator: Green (<3min), amber (3-10min), red (>10min)

## Automation

### Logic

The auto-loop runs every 30 seconds when `ec.enabled == true` and `ec.maintenance_override == false`.

**Decision flow:**
1. Check hard gates (E-STOP, reservoir, sensor stale, temp, pH range, mix lock)
2. Check interval guard (min time between doses)
3. Check daily cap
4. Read current EC
5. If EC < `ec.target` low threshold:
   - Calculate dose: `(target_mid - current_ec) * learned_ml_per_mScm * safety_factor`
   - Clamp to `ec.step_min_ml` – `ec.step_max_ml`
   - Dose using schedule mix ratio

### Hard Gates

Auto-loop suspends (holds) when:

- **DB Stale**: Sensor data age > 180s
- **Temp Range**: Water temp < 16°C or > 26°C
- **pH Range**: pH < 5.5 or > 6.5
- **Other guards**: E-STOP, empty reservoir, mix lock

Suspended state shown in UI with reason and "Holding" badge.

### Learning

The system learns `ml per 1.0 mS/cm` from historical dose logs to improve accuracy. Reset learning via:

**POST /api/ec/auto/learn/reset**

## Settings

**Key parameters** (via `/api/ec/settings` or `/api/settings`):

- `ec.enabled`: Auto control master switch
- `ec.maintenance_override`: Bypass cooldown/cap (not hard gates)
- `ec.target`: Target EC in mS/cm (e.g., 0.80)
- `ec.ppm_factor`: Conversion factor (448/500/640/700)
- `ec.step_min_ml`, `ec.step_max_ml`: Auto dose volume range
- `ec.safety_factor`: Conservative multiplier (0.1-1.0)
- `ec.min_interval_sec`: Minimum seconds between doses
- `ec.max_ml_day`: Daily volume cap (0 = unlimited)

**Validation:**
- `ec.target`: 0.6 – 2.4 mS/cm
- `ec.ppm_factor`: {448, 500, 640, 700}
- `ec.safety_factor`: 0.1 – 1.0

## Telemetry

### Endpoints

- **GET /api/ec/live**: Current EC, PPM, temp, freshness indicator
- **GET /api/ec/status**: KPIs, guards, recent doses, auto state
- **GET /api/ec/dose_log**: JSON array of dose events
- **GET /api/ec/dose_log.csv?hours=24**: CSV export

### Database

**Table: `ec_dose_log`**

```sql
CREATE TABLE ec_dose_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  action TEXT NOT NULL,           -- 'dose' or 'prime'
  volume_ml REAL,                 -- calculated from ml or pump flow rate
  mix_ratio TEXT,                 -- 'schedule', 'pump:Xs', or 'G:X M:Y B:Z'
  duration_ms INTEGER,            -- pump ON time
  pre_ec REAL,
  post_ec REAL,
  result TEXT NOT NULL,           -- 'ok', 'blocked', 'error'
  reason TEXT                     -- 'manual', 'auto', guard reason
);
```

### Charts

Dose history chart renders:
- Event scatter (timestamp, EC before/after)
- Cumulative volume line
- Daily totals bar

## Testing

### Smoke Test (10 min)

1. **API Sanity**:
   - `GET /api/ec/live` → 200, fresh data (stale:false)
   - `PUT /api/ec/settings` → 200, settings persisted
   - `GET /health/db` → 200

2. **Manual Dosing**:
   - Enable `ec.maintenance_override`
   - Dose each pump 0.5s (GROW, MICRO, BLOOM)
   - Verify relay clicks, auto-OFF, DB logs

3. **Guard Rails**:
   - Disable `ec.enabled` and `ec.maintenance_override`
   - Attempt dose → HTTP 409 (blocked)

4. **UI**:
   - Check freshness dot (green)
   - Override badge visible when set
   - CSV export downloads with test doses
   - Chart displays dose events

5. **Auto Loop** (optional):
   - Enable `ec.enabled`, set target
   - Observe timed doses, no rapid cycling

## Safety

- **Active-Low Relays**: GPIO HIGH = pump OFF (safe default)
- **Safe-Off on Boot**: All relays initialized HIGH
- **Single Pump Mutex**: Only one nutrient pump active at a time
- **Try/Finally**: Relay OFF guaranteed even if exception
- **Maintenance Override**: Bypasses soft limits (interval, cap) but NOT hard gates (E-STOP, reservoir, stale sensors)

## Migration

**File**: `migrations/20251103_create_ec_dose_log.sql`

Idempotent `CREATE TABLE IF NOT EXISTS` with all columns. Safe to re-run.

## References

- API docs: `/docs` (FastAPI Swagger)
- Hardware map: `README.md`
- Alerts: `docs/alerts.md`
