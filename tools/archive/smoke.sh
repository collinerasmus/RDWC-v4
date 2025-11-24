#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-8080}"
BASE="http://${HOST}:${PORT}"

echo "== RDWC smoke on $BASE =="

ok() { echo "✔ $1"; }
fail() { echo "✘ $1"; exit 1; }

# Health (with brief readiness retry)
tries=${SMOKE_HEALTH_TRIES:-10}
sleep_s=${SMOKE_HEALTH_SLEEP:-2}
code="000"
for i in $(seq 1 "$tries"); do
	code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/health" || true)
	echo "health:$code"
	[ "$code" = "200" ] && break
	sleep "$sleep_s"
done
[ "$code" = "200" ] || fail "health not 200"
ok "health 200"

# Status
curl -s "$BASE/relay/status" >/dev/null || fail "relay/status failed"
ok "relay/status reachable"

# Sensors
curl -s "$BASE/sensors/read" >/dev/null || fail "sensors/read failed"
ok "sensors/read reachable"

# Settings round-trip (no change)
curl -s "$BASE/settings" | grep -q "lights_on_time" || fail "settings get failed"
ok "settings get"

# Toggle lights ON then OFF via GET (respects cooldowns)
on=$(curl -s "$BASE/relay/set?name=lights&on=1")
echo "$on" | grep -q '"state":true' || echo "note: lights may be cooldown-limited"
sleep 1
off=$(curl -s "$BASE/relay/set?name=lights&on=0")
echo "$off" | grep -q '"state":false' || echo "note: lights may be cooldown-limited"
ok "relay/set reachable (GET path)"

# Debug buffers
curl -s "$BASE/debug/relay_requests" >/dev/null || fail "debug/relay_requests failed"
ok "debug/relay_requests"

curl -s "$BASE/debug/lights_log" >/dev/null || fail "debug/lights_log failed"
ok "debug/lights_log"

echo "== DONE =="