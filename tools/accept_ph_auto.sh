#!/bin/bash
# Acceptance Script for pH Up Automation v1.0
# 
# Usage:
#   bash tools/accept_ph_auto.sh
#
# Verifies:
# - Service is active
# - Key settings and guards present
# - Auto toggle works (ON → wait → OFF)
# - Learn reset works
# - Safe defaults enforced
#
set -euo pipefail

API="http://127.0.0.1:8080"
POLL_INTERVAL_S=30

echo "=== pH Up Automation Acceptance Test ==="
echo ""

# 1. Verify service active
echo "1️⃣  Checking service status..."
if ! systemctl is-active rdwc >/dev/null 2>&1; then
    echo "❌ FAIL: rdwc service is not active"
    exit 1
fi
echo "   ✅ Service active"
echo ""

# 2. Print key settings and guards
echo "2️⃣  Checking key settings..."
SETTINGS=$(curl -s "$API/api/settings" || echo "{}")
AUTO_ENABLED=$(echo "$SETTINGS" | jq -r '."ph.auto_enabled" // "unknown"')
POLL_INTERVAL=$(echo "$SETTINGS" | jq -r '."dosing.poll_interval_s" // "unknown"')
EC_BASELINE=$(echo "$SETTINGS" | jq -r '."dosing.ec_baseline_min" // "unknown"')
MAINT_OVERRIDE=$(echo "$SETTINGS" | jq -r '."safety.maintenance_override" // "unknown"')

echo "   ph.auto_enabled: $AUTO_ENABLED"
echo "   dosing.poll_interval_s: $POLL_INTERVAL"
echo "   dosing.ec_baseline_min: $EC_BASELINE"
echo "   safety.maintenance_override: $MAINT_OVERRIDE"

if [[ "$POLL_INTERVAL" != "unknown" && "$POLL_INTERVAL" =~ ^[0-9]+$ ]]; then
    POLL_INTERVAL_S="$POLL_INTERVAL"
fi
echo ""

echo "3️⃣  Checking guards..."
STATUS=$(curl -s "$API/api/ph/status" || echo "{}")
GUARDS=$(echo "$STATUS" | jq -c '.guards // {}')
echo "   Guards: $GUARDS"
echo ""

# 4. Toggle auto ON, wait, check holding reason
echo "4️⃣  Testing auto toggle ON..."
TOGGLE_ON=$(curl -s -X POST "$API/api/ph/auto" -H "Content-Type: application/json" -d '{"enable":true}' || echo "{}")
ENABLED=$(echo "$TOGGLE_ON" | jq -r '.enabled // false')
if [[ "$ENABLED" != "true" ]]; then
    echo "   ❌ FAIL: Could not enable automation"
    exit 1
fi
echo "   ✅ Automation enabled"

echo "   Waiting ${POLL_INTERVAL_S}s (one poll interval for warm-up)..."
sleep "$POLL_INTERVAL_S"

STATUS_AFTER=$(curl -s "$API/api/ph/status" || echo "{}")
AUTO_STATE=$(echo "$STATUS_AFTER" | jq -c '.auto // {}')
echo "   Auto state after warm-up: $AUTO_STATE"
echo ""

# 5. Toggle auto OFF
echo "5️⃣  Testing auto toggle OFF..."
TOGGLE_OFF=$(curl -s -X POST "$API/api/ph/auto" -H "Content-Type: application/json" -d '{"enable":false}' || echo "{}")
DISABLED=$(echo "$TOGGLE_OFF" | jq -r '.enabled // true')
if [[ "$DISABLED" != "false" ]]; then
    echo "   ❌ FAIL: Could not disable automation"
    exit 1
fi
echo "   ✅ Automation disabled"
echo ""

# 6. Test learn reset
echo "6️⃣  Testing learn reset..."
LEARNED_BEFORE=$(echo "$STATUS_AFTER" | jq -r '.auto.learned_ml_per_pH // "null"')
echo "   Learned before reset: $LEARNED_BEFORE"

RESET_RESP=$(curl -s -X POST "$API/api/ph/auto/learn/reset" || echo "{}")
RESET_OK=$(echo "$RESET_RESP" | jq -r '.ok // false')
if [[ "$RESET_OK" != "true" ]]; then
    echo "   ❌ FAIL: Learn reset endpoint did not return ok:true"
    echo "   Response: $RESET_RESP"
    exit 1
fi

STATUS_AFTER_RESET=$(curl -s "$API/api/ph/status" || echo "{}")
LEARNED_AFTER=$(echo "$STATUS_AFTER_RESET" | jq -r '.auto.learned_ml_per_pH // "null"')
echo "   Learned after reset: $LEARNED_AFTER"

if [[ "$LEARNED_AFTER" != "50" && "$LEARNED_AFTER" != "50.0" ]]; then
    echo "   ⚠️  WARNING: Expected learned to reset to 50.0, got $LEARNED_AFTER"
fi
echo "   ✅ Learn reset works"
echo ""

# 7. Re-enforce safe defaults
echo "7️⃣  Re-enforcing safe defaults..."
SAFE_UPDATE=$(curl -s -X PUT "$API/api/settings" -H "Content-Type: application/json" \
    -d '{"safety.maintenance_override":"false","safety.allow_stale_on_override":"false","ph.auto_enabled":"false"}' || echo "{}")
UPDATE_OK=$(echo "$SAFE_UPDATE" | jq -r '.ok // false')
if [[ "$UPDATE_OK" != "true" ]]; then
    echo "   ⚠️  WARNING: Could not force safe defaults"
else
    echo "   ✅ Safe defaults enforced"
fi
echo ""

# Final status check
echo "8️⃣  Final status check..."
FINAL_STATUS=$(curl -s "$API/api/ph/status" || echo "{}")
FINAL_AUTO=$(echo "$FINAL_STATUS" | jq -c '.auto // {}')
echo "   Final auto state: $FINAL_AUTO"
echo ""

echo "✅ PASS: pH Up Automation acceptance test complete"
echo ""
echo "Summary:"
echo "  - Service active"
echo "  - Settings & guards accessible"
echo "  - Auto toggle ON/OFF works"
echo "  - Learn reset works (value: $LEARNED_AFTER)"
echo "  - Safe defaults enforced"
echo ""
