#!/bin/bash
# RDWC-v4 Lights Whitelist System Deployment Script
# Deploys the anti-flap whitelist protection system to eliminate "off dips"

set -e

echo "🚀 RDWC-v4 Lights Whitelist System Deployment"
echo "=============================================="
echo ""

# Configuration
PI_USER="pi"
PI_HOST="192.168.88.49"  # Adjust as needed
REPO_URL="https://github.com/collinerasmus/RDWC-v4.git"
REMOTE_DIR="/home/pi/RDWC-v4"

echo "📋 Deployment Summary:"
echo "   Target: $PI_USER@$PI_HOST"
echo "   Directory: $REMOTE_DIR"
echo "   Purpose: Deploy lights whitelist protection system"
echo ""

# Function to run commands on Pi
run_on_pi() {
    ssh $PI_USER@$PI_HOST "$1"
}

echo "🔄 Step 1: Update code on Pi..."
run_on_pi "cd $REMOTE_DIR && git fetch --all && git reset --hard origin/main"

echo "📦 Step 2: Install/update dependencies..."
run_on_pi "cd $REMOTE_DIR && source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

echo "🔧 Step 3: Restart RDWC service..."
run_on_pi "sudo systemctl restart rdwc.service"

echo "⏳ Step 4: Wait for service to start..."
sleep 5

echo "🔍 Step 5: Check service status..."
run_on_pi "sudo systemctl status rdwc.service --no-pager -l"

echo ""
echo "🧪 Step 6: Test debug endpoints..."
echo "   Testing whitelist endpoint..."
run_on_pi "curl -s http://localhost:8080/debug/lights_allowed | python3 -m json.tool"

echo ""
echo "   Testing event log endpoint..."
run_on_pi "curl -s 'http://localhost:8080/debug/lights_log?last=5' | python3 -m json.tool"

echo ""
echo "✅ Deployment completed successfully!"
echo ""
echo "🔍 Monitoring Instructions:"
echo "   1. Watch event log: curl 'http://192.168.88.49:8080/debug/lights_log?last=20'"
echo "   2. Check for blocked attempts: Look for 'blocked: true' in logs"
echo "   3. Monitor for 'off dips': Should be eliminated with edge-only scheduling"
echo "   4. View allowed reasons: curl 'http://192.168.88.49:8080/debug/lights_allowed'"
echo ""
echo "🎯 Success Criteria:"
echo "   - ✅ No more periodic 'off dips' every ~minute"
echo "   - ✅ All light changes logged with caller identification"
echo "   - ✅ Unauthorized attempts blocked and logged"
echo "   - ✅ Scheduled on/off times work correctly at exact edges"
echo ""
echo "📊 Key Changes Deployed:"
echo "   - WHITELIST_LIGHTS with 8 approved reasons"
echo "   - Event tracing with caller detection (200-event history)"
echo "   - Pure edge-only scheduling (no periodic guards)"
echo "   - Anti-flap protection with cooldowns"
echo "   - Debug endpoints for monitoring"
echo ""