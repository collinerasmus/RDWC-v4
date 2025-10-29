# Alert System Documentation

The RDWC-v4 alert system provides comprehensive monitoring and notifications for your hydroponic system.

## Features

### 🚨 Real-time Monitoring
- Continuous pH, EC, and temperature monitoring
- Configurable thresholds with hysteresis to prevent alert spam
- Debouncing to avoid excessive notifications
- Grace period for recovery to prevent flip-flopping alerts

### 📱 Multiple Alert Channels
- **Telegram**: Instant notifications via Telegram bot
- **Email**: SMTP email alerts with detailed sensor data
- **Morning Reports**: Daily summary reports with 24-hour statistics

### 📊 Smart Thresholds
- pH: 5.5 - 6.3 (typical hydroponic range)
- EC: 1.2 - 2.0 mS/cm (adjustable for your nutrient schedule)
- Temperature: 18 - 22°C (optimal for most plants)
- All thresholds configurable via environment variables

## Configuration

### 1. Environment Setup
Copy the template and configure your settings:
```bash
cp .env.template .env
nano .env
```

### 2. Required Settings

#### Telegram (Optional)
```bash
ALERT_ENABLE_TELEGRAM=true
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

#### Email (Optional)  
```bash
ALERT_ENABLE_EMAIL=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com  
SMTP_PASS=your_app_password_here
ALERT_RECIPIENTS=admin@example.com,user@example.com
```

#### Sensor Thresholds
```bash
PH_LOW_THRESHOLD=5.5
PH_HIGH_THRESHOLD=6.3
EC_LOW_THRESHOLD=1.2
EC_HIGH_THRESHOLD=2.0
TEMP_LOW_THRESHOLD=18.0
TEMP_HIGH_THRESHOLD=22.0
```

## Deployment

### Quick Deploy
```bash
sudo ./tools/deploy_alerts.sh
```

### Manual Steps
1. Install additional Python packages:
   ```bash
   pip install httpx
   ```

2. Copy systemd files:
   ```bash
   sudo cp systemd/rdwc-morning-report.* /etc/systemd/system/
   sudo systemctl daemon-reload
   ```

3. Enable morning report timer:
   ```bash
   sudo systemctl enable rdwc-morning-report.timer
   sudo systemctl start rdwc-morning-report.timer
   ```

## API Endpoints

### Monitor Status
```bash
curl http://192.168.88.49:8080/monitoring/status
```

Returns current alert states, monitoring activity, and sensor health.

### Test Alerts
```bash
curl -X POST http://192.168.88.49:8080/monitoring/test_alerts
```

Sends test messages to all configured alert channels.

## Alert Types

### Sensor Alerts
- **pH Out of Range**: Triggered when pH goes below 5.5 or above 6.3
- **EC Out of Range**: Triggered when EC goes below 1.2 or above 2.0 mS/cm
- **Temperature Out of Range**: Triggered when temperature goes below 18°C or above 22°C
- **Sensor Offline**: Triggered when sensors become unresponsive

### System Alerts
- **Morning Report**: Daily summary at 8:00 AM with 24-hour statistics
- **System Failure**: Critical system component failures
- **Database Issues**: Data logging problems

## Alert Features

### Debouncing
Prevents alert spam by enforcing minimum time between alerts of the same type (default: 60 minutes).

### Hysteresis
Prevents flip-flopping alerts by requiring values to move further from threshold before clearing alerts.

### Grace Period
Allows temporary recoveries without immediately clearing alert state (default: 15 minutes).

### Rich Data
Alerts include current values, target ranges, and relevant sensor data for context.

## Monitoring

### View Logs
```bash
# Morning report logs
journalctl -u rdwc-morning-report.service -f

# Main service logs (includes monitoring)
journalctl -u rdwc.service -f
```

### Timer Status
```bash
systemctl status rdwc-morning-report.timer
systemctl list-timers rdwc-morning-report.timer
```

### Manual Report
```bash
sudo -u pi ./scripts/morning_report.py --send-alerts
```

## Troubleshooting

### No Alerts Received
1. Check configuration: `curl http://192.168.88.49:8080/monitoring/status`
2. Test alert channels: `curl -X POST http://192.168.88.49:8080/monitoring/test_alerts`
3. Verify environment variables: `cat .env`
4. Check service logs: `journalctl -u rdwc.service -n 50`

### False Alerts
1. Adjust thresholds in `.env`
2. Increase hysteresis values to reduce sensitivity
3. Increase debounce time to reduce frequency

### Missing Morning Reports
1. Check timer status: `systemctl status rdwc-morning-report.timer`
2. View timer logs: `journalctl -u rdwc-morning-report.service`
3. Test manually: `sudo -u pi ./scripts/morning_report.py --send-alerts`

## Security Notes

- Store sensitive credentials (API keys, passwords) in `.env` file
- Ensure `.env` file has restricted permissions: `chmod 600 .env`
- Use app passwords for Gmail SMTP, not main account passwords
- Consider IP restrictions for Telegram bots in production

## Customization

### Custom Thresholds
Modify threshold values in `.env` for your specific growing conditions:
- **Seedlings**: Lower EC (0.8-1.2 mS/cm)
- **Flowering**: Higher EC (1.8-2.5 mS/cm)
- **Cool Weather**: Lower temperature range
- **Specific Strains**: pH preferences may vary

### Additional Alert Types
Extend `app/alerts.py` and `app/monitor.py` to add custom monitoring logic for:
- Water level sensors
- Light schedules
- Pump operation time
- Custom sensor integrations