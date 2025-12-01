-- EC Control v2 Migration: Backfill ec_dose_log → dose_events
-- Created: 2025-12-01
-- Idempotent: Safe to re-run (skips duplicates)
--
-- Purpose: Migrate historical EC dose data from ec_dose_log to the unified
-- dose_events table. This enables single source of truth for all dosing logs.
--
-- Note: After this migration, new EC doses are written to dose_events only.
-- The ec_dose_log table is kept for read-only backward compatibility.

-- Ensure dose_events table exists with required schema
CREATE TABLE IF NOT EXISTS dose_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    pump TEXT NOT NULL,
    seconds REAL NOT NULL,
    reason TEXT,
    actor TEXT,
    ph_before REAL,
    ph_after REAL,
    ec_before REAL,
    ec_after REAL,
    temp_c REAL,
    blocked_by TEXT,
    controller_state_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_dose_events_ts ON dose_events(ts DESC);

-- Insert historical EC dose records from ec_dose_log that don't already exist
-- Uses a LEFT JOIN on ts+pump+seconds to detect duplicates
-- Parses mix_ratio to extract pump name (e.g., "grow:1.5s" -> grow)

INSERT INTO dose_events (ts, pump, seconds, reason, actor, ec_before, ec_after, blocked_by)
SELECT 
    CAST(strftime('%s', el.ts_utc) AS INTEGER) as ts,
    CASE 
        -- Parse pump from mix_ratio field (format: "grow:1.5s" or "schedule:G30.0M30.0B30.0")
        WHEN el.mix_ratio LIKE 'grow:%' THEN 'grow'
        WHEN el.mix_ratio LIKE 'micro:%' THEN 'micro'
        WHEN el.mix_ratio LIKE 'bloom:%' THEN 'bloom'
        -- For schedule/custom modes, use 'grow' as representative pump
        WHEN el.mix_ratio LIKE 'schedule:%' THEN 'grow'
        WHEN el.mix_ratio LIKE 'custom:%' THEN 'grow'
        ELSE 'grow'
    END as pump,
    CASE 
        -- Parse seconds from mix_ratio if available (format: "pump:Xs")
        WHEN el.mix_ratio LIKE '%:%s' THEN 
            CAST(SUBSTR(el.mix_ratio, INSTR(el.mix_ratio, ':') + 1, 
                LENGTH(el.mix_ratio) - INSTR(el.mix_ratio, ':') - 1) AS REAL)
        -- Otherwise compute from duration_ms
        WHEN el.duration_ms IS NOT NULL THEN CAST(el.duration_ms AS REAL) / 1000.0
        ELSE 0.0
    END as seconds,
    el.reason,
    CASE 
        WHEN el.reason = 'auto' THEN 'auto'
        WHEN el.result = 'blocked' THEN 'blocked'
        ELSE 'manual'
    END as actor,
    el.pre_ec,
    el.post_ec,
    CASE 
        WHEN el.result = 'blocked' OR el.result LIKE 'error%' THEN el.reason
        ELSE NULL
    END as blocked_by
FROM ec_dose_log el
LEFT JOIN dose_events de ON 
    de.ts = CAST(strftime('%s', el.ts_utc) AS INTEGER)
    AND de.pump IN ('grow', 'micro', 'bloom')
    AND ABS(de.seconds - (COALESCE(el.duration_ms, 0) / 1000.0)) < 0.1
WHERE de.id IS NULL;  -- Only insert if not already exists

-- Mark migration as complete in system_state table
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

INSERT OR REPLACE INTO system_state (key, value, updated_at)
VALUES ('ec_dose_events_migration', 'complete', datetime('now'));
