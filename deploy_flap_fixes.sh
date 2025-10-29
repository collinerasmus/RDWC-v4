#!/bin/bash
# Pi deployment script - single pull and restart
echo "🚀 Deploying relay flap fixes to Pi..."

cd ~/RDWC-v4
echo "📥 Pulling latest changes..."
git pull

echo "🔄 Restarting RDWC service..."
sudo systemctl restart rdwc.service

echo "⏳ Waiting for service to start..."
sleep 5

echo "🩺 Quick health check..."
curl -s http://127.0.0.1:8080/health | jq 2>/dev/null || curl -s http://127.0.0.1:8080/health

echo "✅ Deployment complete! Check /health endpoint for relay states and anti-flap status."