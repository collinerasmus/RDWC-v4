.headers on
.mode column
SELECT datetime(min(ts),'unixepoch','localtime') AS first_ts,
       datetime(max(ts),'unixepoch','localtime') AS last_ts,
       COUNT(*) AS rows_24h
FROM readings
WHERE ts >= strftime('%s','now') - 86400;
