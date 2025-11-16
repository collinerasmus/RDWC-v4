-- Frontend error logging table
-- Captures browser console errors and warnings for debugging

CREATE TABLE IF NOT EXISTS frontend_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    level TEXT NOT NULL CHECK(level IN ('error', 'warn', 'info', 'debug')),
    message TEXT NOT NULL,
    stack TEXT,
    url TEXT,
    line_number INTEGER,
    column_number INTEGER,
    user_agent TEXT,
    page_url TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_frontend_logs_ts ON frontend_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_frontend_logs_level ON frontend_logs(level);
CREATE INDEX IF NOT EXISTS idx_frontend_logs_created ON frontend_logs(created_at DESC);
