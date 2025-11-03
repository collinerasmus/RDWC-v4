-- EC Control v1.0 Dose Log Table
-- Created: 2025-11-03
-- Idempotent: Safe to re-run

CREATE TABLE IF NOT EXISTS ec_dose_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    action TEXT NOT NULL,           -- 'dose' or 'prime'
    volume_ml REAL,                 -- calculated from ml or pump flow rate
    mix_ratio TEXT,                 -- 'schedule', 'pump:Xs', or 'G:X M:Y B:Z'
    duration_ms INTEGER,            -- pump ON time in milliseconds
    pre_ec REAL,                    -- EC reading before dose (mS/cm)
    post_ec REAL,                   -- EC reading after dose (mS/cm)
    result TEXT NOT NULL,           -- 'ok', 'blocked', 'error'
    reason TEXT                     -- 'manual', 'auto', guard reason, etc.
);

-- Index for common queries (by timestamp descending)
CREATE INDEX IF NOT EXISTS idx_ec_dose_log_ts ON ec_dose_log(ts_utc DESC);

-- Index for daily aggregations
CREATE INDEX IF NOT EXISTS idx_ec_dose_log_date ON ec_dose_log(date(ts_utc));
