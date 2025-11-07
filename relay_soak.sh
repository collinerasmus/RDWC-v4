#!/usr/bin/env bash
set -euo pipefail

echo "=== A) Restart services (safe-off should run) ==="
sudo systemctl restart rdwc.service rdwc-sensors.service
sleep 5
sudo journalctl -u rdwc.service -n 40 --no-pager

echo
echo "=== B) Shadow vs actual ==="
curl -s http://127.0.0.1:8080/api/relays/guard/status | jq || true
raspi-gpio get 5,6,13,19,26,16,20,21

echo
echo "=== C) Open UI and click through tabs slowly (no control clicks) ==="
echo "   Overview → Live Sensors → pH → EC → Schedule → Environment → Lights → Circulation → Relays → Calibration → System & Alerts → History"
read -p "Press Enter after tab walk-through..."

echo
echo "=== D) Request audit (last 80 lines — should show GET/OPTIONS only) ==="
sudo journalctl -u rdwc.service -n 80 --no-pager | sed -n 's/.*\(GET\|POST\|PUT\).*/\0/p'

echo
echo "=== E) 10-minute soak with watchdog active ==="
sleep 600

echo
echo "=== F) Watchdog anomalies during soak (should be 0) ==="
sudo journalctl -u rdwc.service --since '10 minutes ago' | grep -i 'RelayWatchdog.*ANOMALY' || echo "No watchdog anomalies found ✓"

echo
echo "=== G) Final anomaly count and shadow state ==="
curl -s http://127.0.0.1:8080/api/relays/guard/status | jq '.anomalies // "no-anomaly-field"'

echo
echo "=== H) Final relay status ==="
curl -s http://127.0.0.1:8080/api/relays/status | jq '.relays | to_entries[] | {name: .key, is_on: .value.is_on}'
