.headers on
.mode column
WITH r AS (
  SELECT (ts/3600)*3600 AS h, COUNT(*) AS c
  FROM readings
  WHERE ts >= strftime('%s','now') - 86400
  GROUP BY 1
)
SELECT datetime(h,'unixepoch','localtime') AS hour, c AS rows
FROM r ORDER BY h;
