#!/bin/bash
set -euo pipefail

echo "=== Pre-Reboot: Enabled states ==="
systemctl is-enabled rdwc-sensors.service || true
systemctl is-enabled rdwc-sensors-watchdog.timer || true
systemctl is-enabled rdwc.service || true

echo ""
echo "=== Initiating reboot ==="
sudo reboot
