# EC Control v2

EC Control v2 brings EC automation to parity with pH control by unifying logging, implementing schedule-driven ratios, adding dry-run default, and centralizing guards.

## Key Changes

### 1. Single Source of Truth: dose_events Table

All EC dose activity (manual, auto, preview/dry-run) is now logged to the unified `dose_events` table only. The legacy `ec_dose_log` table is no longer written to but remains available for read-only backward compatibility.

**Migrated endpoints:**
- `/api/ec/dose_log` - Now reads from `dose_events`
- `/api/ec/dose/recent` - Now reads from `dose_events`
- `/api/ec/dose_log.csv` - Now reads from `dose_events`
- `/api/ec/dose_summary` - Now computes from `dose_events`

### 2. Dry-Run Mode (Default: OFF)

EC dosing defaults to live mode (pumps actuate). The dry-run option exists for testing when nutrients are loaded. When `dosing.dry_run_ec=true`:
- Dose requests log shadow events to `dose_events` with `actor="dry-run"`
- NO pump actuation occurs
- Response includes `dry_run: true` and detailed `controller_state_json`
- Both manual and auto dosing respect this setting

**To enable dry-run mode (for testing with nutrients loaded):**
```sql
UPDATE settings SET value='true' WHERE key='dosing.dry_run_ec';
```

Or via API:
```bash
curl -X PUT http://localhost:8080/api/settings/import \
  -H "Content-Type: application/json" \
  -d '{"dosing.dry_run_ec": "true"}'
```

### 3. Schedule-Driven Ratios

When `mix_ratio="schedule"` (default), G/M/B nutrient split is computed from the `nutrient_schedule` table based on the current grow week:

1. System determines current week from `general.grow_start_date`
2. Fetches `grow_ml10`, `micro_ml10`, `bloom_ml10` for that week
3. Normalizes to ratios (e.g., 3:2:1 → G=0.5, M=0.33, B=0.17)
4. Applies ratios to total dose ml

**Fallback behavior:**
- No start date → Equal split (1/3 each), `ratio_source="equal_split:no_start_date"`
- Invalid date → Equal split, `ratio_source="equal_split:invalid_date"`
- No schedule for week → Equal split, `ratio_source="equal_split:no_schedule_week_N"`
- Flush week (all zeros) → Zero ratio, `ratio_source="schedule:flush_week_N"`

### 4. Centralized Guards

EC dosing now uses the centralized `dosing.check_dosing_guards()` function for consistency with pH dosing:

**Always-On Guards (both Auto and Manual):**
- `estop` - E-STOP active
- `safeoff` - Safe-off mode active
- `mix_lock` - Another dose in progress
- `ec_guard` - EC already at or above threshold

**Auto-Only Guards (only when global_auto enabled):**
- `press_cap` - Exceeds max seconds per press
- `daily_cap` - Daily usage limit reached
- `min_off` - Too soon since last dose
- `stale` - Sensor reading too old

**Blocked dose responses:**
- Return HTTP 409 with `blocked_by` field
- Log blocked event to `dose_events` with `blocked_by` set

### 5. Preview = Worker Logic

The `/api/ec/control/preview` endpoint is now the single source of decision math. The background auto worker reuses this same logic to ensure consistency between preview and actual dosing decisions.

**Preview response includes:**
```json
{
  "would_dose": true,
  "dry_run": true,
  "current_ec": 0.65,
  "setpoint": 1.0,
  "ratio_source": "schedule:week_4",
  "ratios": {"grow": 0.4, "micro": 0.3, "bloom": 0.3},
  "proposed_action": {
    "ml": 45.0,
    "mix": {"grow": 18.0, "micro": 13.5, "bloom": 13.5},
    "ratio_source": "schedule:week_4",
    "needed_mScm": 0.35,
    "safety_factor": 0.6,
    "learned_ml_per_mScm": null,
    "dry_run": true
  }
}
```

## Settings Map

### Canonical Settings (preferred)
| Key | Default | Description |
|-----|---------|-------------|
| `dosing.dry_run_ec` | `true` | Dry-run mode (no pump actuation) |
| `dosing.ec_min_interval_s` | `300` | Minimum seconds between doses |
| `dosing.ec_max_ml_day` | `0` | Daily volume cap (0 = disabled) |
| `dosing.ec_step_ml_min` | `10` | Minimum dose size (ml) |
| `dosing.ec_step_ml_max` | `120` | Maximum dose size (ml) |
| `dosing.ec_safety_factor` | `0.6` | Conservative multiplier (0.1-1.0) |
| `targets.ec_target` | `1.8` | Target EC (mS/cm) |
| `targets.ec_tolerance` | `0.2` | Deadband tolerance |
| `targets.ec_low` | `0.8` | Low EC threshold |
| `targets.ec_high` | `1.2` | High EC threshold |

### Legacy Fallback (deprecated)
| Legacy Key | Maps To |
|-----------|---------|
| `ec.min_interval_sec` | `dosing.ec_min_interval_s` |
| `ec.max_ml_day` | `dosing.ec_max_ml_day` |
| `ec.step_min_ml` | `dosing.ec_step_ml_min` |
| `ec.step_max_ml` | `dosing.ec_step_ml_max` |
| `ec.safety_factor` | `dosing.ec_safety_factor` |
| `ec.target` | `targets.ec_target` |

## API Changes

### POST /api/ec/dose

**New response fields:**
- `dry_run` - Boolean indicating if this was a dry-run
- `ratio_source` - Where ratios came from (e.g., "schedule:week_4")
- `rowid` / `rowids` - ID(s) in dose_events table

**pump+seconds mode:**
```json
{
  "pump": "grow",
  "seconds": 1.5,
  "reason": "manual"
}
```

**ml+mix_ratio mode:**
```json
{
  "ml": 45,
  "mix_ratio": "schedule",
  "reason": "manual"
}
```

### GET /api/ec/control/preview

Returns decision without execution. Now includes:
- `dry_run` - Current dry-run setting
- `ratio_source` - Schedule or fallback source
- `ratios` - G/M/B ratio dict
- `proposed_action.mix` - ml per pump

### GET /api/ec/auto/debug

Now includes:
- `dry_run` in last_decision
- `ratio_source` in last_decision

## Migration

The migration script `20251201_backfill_ec_dose_events.sql`:
1. Creates `dose_events` table if needed
2. Backfills historical `ec_dose_log` rows
3. Skips duplicates (idempotent)
4. Marks migration complete in `system_state`

Run manually if needed:
```bash
sqlite3 data/rdwc.db < migrations/20251201_backfill_ec_dose_events.sql
```

## Rollout

1. Deploy with `dosing.dry_run_ec=true` (default)
2. Verify `/api/ec/control/preview` returns expected decisions
3. Check `/api/ec/dose_log` returns unified data
4. Test manual dose returns `dry_run: true`
5. When ready, set `dosing.dry_run_ec=false` to enable actuation

## Testing

New tests cover:
- Guard blocks with 409 response and `blocked_by`
- Schedule-ratio split computation
- Dry-run logging with actor="dry-run"
- Daily caps and intervals
- Preview math parity with worker
- Backward-compatible endpoint shapes
