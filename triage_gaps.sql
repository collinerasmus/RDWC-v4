.headers on
.mode column
WITH s AS (
  SELECT ts, ph, ec_ms_cm, temp_c,
         LAG(ts) OVER (ORDER BY ts) AS prev_ts
  FROM readings
  WHERE ts >= strftime('%s','now') - 172800
)
SELECT datetime(prev_ts,'unixepoch','localtime') AS gap_start,
       datetime(ts,'unixepoch','localtime')      AS gap_end,
       (ts - prev_ts) AS gap_sec
FROM s
WHERE prev_ts IS NOT NULL AND (ts - prev_ts) > 180
ORDER BY ts;
