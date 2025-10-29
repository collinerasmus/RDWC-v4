#!/bin/bash
# RDWC-v4 Lights Monitoring Script
# Monitors the whitelist protection system and tracks light control events

PI_HOST="192.168.88.49"  # Adjust as needed
API_BASE="http://$PI_HOST:8080"

show_help() {
    echo "🔍 RDWC-v4 Lights Monitoring Script"
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  log [N]      Show last N light events (default: 20)"
    echo "  allowed      Show whitelisted reasons"
    echo "  watch        Continuously monitor for new events"
    echo "  blocked      Show only blocked attempts"
    echo "  stats        Show event statistics"
    echo "  hold [S]     Set debugging hold for S seconds"
    echo "  status       Show system status"
    echo ""
}

show_log() {
    local count=${1:-20}
    echo "📜 Last $count lights events:"
    curl -s "$API_BASE/debug/lights_log?last=$count" | python3 -c "
import json, sys
data = json.load(sys.stdin)
events = data.get('events', [])
print(f'Total events in log: {data.get(\"total_events\", 0)}')
print('---')
for i, event in enumerate(events, 1):
    blocked = '🚫 BLOCKED' if event.get('blocked') else '✅ ALLOWED'
    reason = event.get('reason', 'unknown')
    state = event.get('final_state', 'unknown')
    caller = event.get('caller', 'unknown')
    timestamp = event.get('timestamp', 'no-time')
    cooldown = event.get('cooldown_remaining', 0)
    
    print(f'{i:2d}. {blocked} {reason} -> {state}')
    print(f'    📞 {caller}')
    print(f'    🕐 {timestamp} (cooldown: {cooldown}s)')
    print()
"
}

show_allowed() {
    echo "✅ Whitelisted reasons for lights control:"
    curl -s "$API_BASE/debug/lights_allowed" | python3 -c "
import json, sys
data = json.load(sys.stdin)
reasons = data.get('allowed_reasons', [])
for i, reason in enumerate(reasons, 1):
    print(f'{i:2d}. {reason}')
print(f'\\nTotal: {len(reasons)} allowed reasons')
"
}

show_blocked() {
    echo "🚫 Blocked light control attempts:"
    curl -s "$API_BASE/debug/lights_log?last=50" | python3 -c "
import json, sys
data = json.load(sys.stdin)
events = data.get('events', [])
blocked_events = [e for e in events if e.get('blocked', False)]

if not blocked_events:
    print('✅ No blocked attempts found!')
else:
    for i, event in enumerate(blocked_events, 1):
        reason = event.get('reason', 'unknown')
        caller = event.get('caller', 'unknown')
        timestamp = event.get('timestamp', 'no-time')
        print(f'{i}. BLOCKED: \"{reason}\" by {caller} at {timestamp}')
"
}

show_stats() {
    echo "📊 Light control event statistics:"
    curl -s "$API_BASE/debug/lights_log?last=100" | python3 -c "
import json, sys
from collections import Counter

data = json.load(sys.stdin)
events = data.get('events', [])

if not events:
    print('No events found')
    sys.exit()

# Count by reason
reasons = Counter(e.get('reason', 'unknown') for e in events)
blocked_count = sum(1 for e in events if e.get('blocked', False))
allowed_count = len(events) - blocked_count

print(f'Total events: {len(events)}')
print(f'✅ Allowed: {allowed_count} ({allowed_count/len(events)*100:.1f}%)')
print(f'🚫 Blocked: {blocked_count} ({blocked_count/len(events)*100:.1f}%)')
print()
print('Top reasons:')
for reason, count in reasons.most_common(10):
    print(f'  {reason}: {count}')

# Count by caller
callers = Counter(e.get('caller', 'unknown') for e in events)
print()
print('Top callers:')  
for caller, count in callers.most_common(5):
    print(f'  {caller}: {count}')
"
}

watch_events() {
    echo "👀 Watching for new light control events (Ctrl+C to stop)..."
    local last_count=0
    
    while true; do
        local current_data=$(curl -s "$API_BASE/debug/lights_log?last=1")
        local current_count=$(echo "$current_data" | python3 -c "import json, sys; print(json.load(sys.stdin).get('total_events', 0))")
        
        if [ "$current_count" -gt "$last_count" ]; then
            echo "🔔 New event detected at $(date):"
            echo "$current_data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
events = data.get('events', [])
if events:
    event = events[-1]
    blocked = '🚫 BLOCKED' if event.get('blocked') else '✅ ALLOWED'
    reason = event.get('reason', 'unknown')
    state = event.get('final_state', 'unknown')
    caller = event.get('caller', 'unknown')
    print(f'  {blocked} {reason} -> {state} by {caller}')
"
            echo
        fi
        
        last_count=$current_count
        sleep 2
    done
}

set_hold() {
    local seconds=${1:-10}
    echo "🛑 Setting lights hold for $seconds seconds..."
    curl -s -X POST "$API_BASE/debug/lights_hold" -H "Content-Type: application/json" -d "{\"seconds\": $seconds}" | python3 -m json.tool
}

show_status() {
    echo "📊 RDWC System Status:"
    curl -s "$API_BASE/health" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'System OK: {data.get(\"ok\", False)}')
print(f'Uptime: {data.get(\"uptime_s\", 0):.0f}s')

relay_states = data.get('relay_states', {})
if 'lights' in relay_states:
    lights = relay_states['lights']
    state = 'ON' if lights.get('state') else 'OFF'
    reason = lights.get('last_reason', 'unknown')
    since = lights.get('seconds_since_change', 0)
    print(f'Lights: {state} (reason: {reason}, {since}s ago)')

antiflap = data.get('antiflap_active', [])
if antiflap:
    print(f'Anti-flap active: {antiflap}')
else:
    print('Anti-flap: OK')
"
}

# Main command handling
case "${1:-help}" in
    "log")
        show_log "$2"
        ;;
    "allowed")
        show_allowed
        ;;
    "watch")
        watch_events
        ;;
    "blocked")
        show_blocked
        ;;
    "stats")
        show_stats
        ;;
    "hold")
        set_hold "$2"
        ;;
    "status")
        show_status
        ;;
    "help"|*)
        show_help
        ;;
esac