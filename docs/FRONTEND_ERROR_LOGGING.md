# Frontend Error Logging System

Automatically captures browser console errors and logs for debugging by GitHub agents and developers.

## Features

- **Automatic Error Capture**: Intercepts `console.error()`, `console.warn()`, global errors, and unhandled promise rejections
- **Batched Logging**: Queues logs and sends in batches to reduce network overhead
- **Persistent Storage**: Stores logs in SQLite database with timestamps and metadata
- **Query API**: Retrieve logs filtered by level, time range, and limit
- **Cleanup API**: Delete old logs to prevent database bloat

## How It Works

1. `error_reporter.js` loads in the browser and intercepts console methods
2. Errors/warnings are queued and sent to `/api/frontend/log` endpoint
3. Backend stores logs in `frontend_logs` table
4. GitHub agents can query `/api/frontend/logs` to see recent errors

## API Endpoints

### POST `/api/frontend/log`
Store browser logs (called automatically by error_reporter.js)

**Request Body:**
```json
{
  "logs": [
    {
      "ts": 1700000000,
      "level": "error",
      "message": "Uncaught TypeError: Cannot read property 'x'",
      "stack": "Error: ...\n  at file.js:42:10",
      "url": "http://localhost:8080/static/js/file.js",
      "line_number": 42,
      "column_number": 10,
      "user_agent": "Mozilla/5.0...",
      "page_url": "http://localhost:8080/",
      "metadata": null
    }
  ]
}
```

### GET `/api/frontend/logs`
Retrieve stored logs

**Query Parameters:**
- `level` (optional): Filter by error level (error, warn, info, debug)
- `limit` (optional): Max logs to return (default 100, max 500)
- `hours` (optional): Look back N hours (default 24)

**Example:**
```bash
curl "http://localhost:8080/api/frontend/logs?level=error&limit=50&hours=6"
```

**Response:**
```json
{
  "logs": [
    {
      "id": 1,
      "ts": 1700000000,
      "level": "error",
      "message": "...",
      "stack": "...",
      "url": "...",
      "line_number": 42,
      "column_number": 10,
      "user_agent": "...",
      "page_url": "...",
      "metadata": null,
      "created_at": "2025-11-16T12:00:00"
    }
  ],
  "total": 15,
  "limit": 50,
  "hours": 6
}
```

### DELETE `/api/frontend/logs`
Clear old logs

**Query Parameters:**
- `older_than_hours` (optional): Delete logs older than N hours (default 168 = 7 days, 0 = all)

**Example:**
```bash
curl -X DELETE "http://localhost:8080/api/frontend/logs?older_than_hours=168"
```

## Manual Logging

You can also manually log from browser console:

```javascript
// Log custom message to backend
window.logToBackend('info', 'User clicked button X', {userId: 123});
```

## For GitHub Agents

When debugging UI issues, query the logs endpoint to see what errors occurred:

```python
import requests

# Get recent errors
response = requests.get('http://192.168.88.55:8080/api/frontend/logs?level=error&hours=1')
logs = response.json()['logs']

for log in logs:
    print(f"[{log['level']}] {log['message']}")
    if log['stack']:
        print(f"  Stack: {log['stack'][:200]}...")
```

## Database Schema

Table: `frontend_logs`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| ts | INTEGER | Unix timestamp |
| level | TEXT | error, warn, info, debug |
| message | TEXT | Error message |
| stack | TEXT | Stack trace (optional) |
| url | TEXT | Source file URL (optional) |
| line_number | INTEGER | Line number (optional) |
| column_number | INTEGER | Column number (optional) |
| user_agent | TEXT | Browser user agent |
| page_url | TEXT | Page where error occurred |
| metadata | TEXT | JSON metadata (optional) |
| created_at | TEXT | ISO timestamp |

## Configuration

`error_reporter.js` constants (edit if needed):

- `MAX_QUEUE_SIZE`: Max logs to queue before auto-flush (default 50)
- `FLUSH_INTERVAL_MS`: Batch flush interval (default 5000ms)
- `MAX_MESSAGE_LENGTH`: Truncate messages longer than this (default 2000)
- `MAX_STACK_LENGTH`: Truncate stack traces longer than this (default 5000)

## Maintenance

Setup a cron job to periodically clean old logs:

```bash
# Delete logs older than 7 days
curl -X DELETE "http://localhost:8080/api/frontend/logs?older_than_hours=168"
```

Or add to systemd timer if desired.

## Retention & Auto-Trim

The backend enforces retention automatically after each ingest (`POST /api/frontend/log`). Two environment variables govern this:

- `FRONTEND_LOG_RETENTION_DAYS` (default `7`): Remove logs older than N days. Set to `0` to disable age-based deletion.
- `FRONTEND_LOG_MAX_ROWS` (default `5000`): Cap total rows; if exceeded, oldest rows are removed to reach the cap. Set to `0` to disable row-cap trimming.

On each ingest, trimming runs in two passes: age pruning then row-cap pruning. A summary object is returned under the `trim` key in the ingest response:

```json
{
  "ok": true,
  "received": 3,
  "trim": {
    "retention_days": 7,
    "max_rows": 5000,
    "deleted_by_age": 0,
    "deleted_by_cap": 0,
    "final_count": 123
  }
}
```

### Manual Trim Endpoint

Use `POST /api/frontend/logs/trim` to force a trim with optional override parameters:

**Parameters (query or form):**
- `retention_days` (optional): Override days for this trim run only
- `max_rows` (optional): Override cap for this trim run only

**Example:**
```bash
curl -X POST "http://localhost:8080/api/frontend/logs/trim?retention_days=14&max_rows=2000"
```

**Response:**
```json
{
  "ok": true,
  "stats": {
    "retention_days": 14,
    "max_rows": 2000,
    "deleted_by_age": 12,
    "deleted_by_cap": 0,
    "final_count": 1998
  }
}
```

### Suggested Values

Small deployments (single Pi): keep defaults (7 days / 5000 rows).
High-volume testing or CI: reduce `FRONTEND_LOG_RETENTION_DAYS` to 3 and cap rows at 3000.

### Systemd Timer (Optional)

Even though auto-trim occurs on ingest, you can add a daily trim via a systemd timer to catch long idle periods with no ingest traffic. Call the manual trim endpoint locally with `curl` or a lightweight script.
