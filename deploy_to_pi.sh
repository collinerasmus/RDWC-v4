#!/bin/bash
# Deploy latest changes to Pi and restart API

set -e

echo "[Deploy] Pulling latest changes..."
cd /home/pi/RDWC-v4
git pull origin main

echo "[Deploy] Restarting RDWC API service..."
sudo systemctl restart rdwc

echo "[Deploy] Waiting 3 seconds for service to come up..."
sleep 3

echo "[Deploy] Checking service status..."
sudo systemctl status rdwc --no-pager

echo "[Deploy] ✓ Deployment complete!"
echo "[Deploy] Hard-refresh your browser (Ctrl+Shift+R) to load the new pH chart code"
