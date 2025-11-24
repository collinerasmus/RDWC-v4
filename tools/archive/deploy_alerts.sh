#!/bin/bash
# RDWC-v4 Alert System Deployment
# Deploys monitoring, alerts, and morning report with systemd timers

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="/home/pi/venv"
SERVICE_USER="pi"

echo "🚀 RDWC-v4 Alert System Deployment"
echo "======================================"

# Ensure we're running as root for systemd operations
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   exit 1
fi

# Check if main RDWC service exists
if ! systemctl list-unit-files | grep -q "rdwc.service"; then
    echo "⚠️  Main RDWC service not found. Deploy main system first."
    exit 1
fi

echo "📦 Installing additional Python packages..."
sudo -u $SERVICE_USER $VENV_PATH/bin/pip install httpx

echo "📋 Copying systemd files..."
cp "$PROJECT_ROOT/systemd/rdwc-morning-report.service" /etc/systemd/system/
cp "$PROJECT_ROOT/systemd/rdwc-morning-report.timer" /etc/systemd/system/

echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

echo "⚡ Enabling and starting morning report timer..."
systemctl enable rdwc-morning-report.timer
systemctl start rdwc-morning-report.timer

echo "📊 Checking timer status..."
systemctl status rdwc-morning-report.timer --no-pager -l

echo "📅 Timer schedule:"
systemctl list-timers rdwc-morning-report.timer --no-pager

echo ""
echo "✅ Alert system deployment complete!"
echo ""
echo "📋 Configuration Steps:"
echo "1. Copy .env.template to .env and configure your settings:"
echo "   cp $PROJECT_ROOT/.env.template $PROJECT_ROOT/.env"
echo "   nano $PROJECT_ROOT/.env"
echo ""
echo "2. Test the alert system:"
echo "   curl -X POST http://192.168.88.49:8080/monitoring/test_alerts"
echo ""
echo "3. Check monitoring status:"
echo "   curl http://192.168.88.49:8080/monitoring/status"
echo ""
echo "4. View morning report timer logs:"
echo "   journalctl -u rdwc-morning-report.service -f"
echo ""
echo "5. Manually run morning report:"
echo "   sudo -u pi $PROJECT_ROOT/scripts/morning_report.py --send-alerts"
echo ""
echo "⏰ Morning reports will be sent daily at 8:00 AM"
echo "🔧 Monitoring is now active with configured thresholds"
echo ""
echo "For help: https://github.com/yourusername/RDWC-v4/wiki/Alert-System"