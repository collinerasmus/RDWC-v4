#!/bin/bash
# Deploy sensor_controller consolidation to Raspberry Pi

PiHost="${1:-pi@raspberrypi.local}"
RepoPath="/home/pi/rdwc"

echo "=========================================="
echo "Deploying sensor_controller consolidation"
echo "=========================================="
echo "Target: $PiHost:$RepoPath"
echo ""

# Test connectivity
echo "Testing SSH connectivity..."
if ! ssh -o ConnectTimeout=5 "$PiHost" "echo OK" >/dev/null 2>&1; then
    echo "✗ Cannot connect to $PiHost"
    echo ""
    echo "Usage: ./deploy_sensor_controller.sh pi@192.168.88.49"
    exit 1
fi
echo "✓ Connected"
echo ""

# Pull changes
echo "Pulling latest changes..."
ssh "$PiHost" "cd $RepoPath && git pull origin main" || {
    echo "✗ Pull failed"
    exit 1
}
echo "✓ Pull complete"
echo ""

# Verify
echo "Verifying sensor_controller..."
ssh "$PiHost" "cd $RepoPath && python3 -c 'from app.sensor_controller import read_sensors, set_ec_k_factor, get_ec_calibration_status'" || {
    echo "✗ Module verification failed"
    exit 1
}
echo "✓ sensor_controller verified"
echo ""

# Restart services
echo "Restarting RDWC services..."
ssh "$PiHost" "sudo systemctl restart rdwc-sensors rdwc-api" || true
echo "✓ Services restarted"
echo ""

echo "=========================================="
echo "✓ Deployment complete!"
echo "=========================================="
echo ""
echo "Next steps - Test EC calibration:"
echo "  1. Open http://raspberrypi.local:8080"
echo "  2. Go to Settings > EC Calibration"
echo "  3. Clear calibration"
echo "  4. Place probe in 1413 µS/cm buffer"
echo "  5. Click 'Low Point (1413 µS/cm)'"
echo "  6. Verify reading ~1.413 mS/cm (K=0.1)"
