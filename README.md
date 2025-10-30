# RDWC v4 — simple & reliable

Single FastAPI service with one control loop for RDWC.
- Sensors: Atlas EZO on I²C (pH=0x63, EC=0x64, RTD=0x66)
- Relays (BCM): 5,6,13,19,26,16,20,21 per your wiring
- Target pH ~5.8–6.2; weekly res maintenance
See `.env.example` for configuration. Start minimal, expand in tiny phases.

## Settings

The system supports configurable settings via the web dashboard or API:

### System Volume
- **Default**: 25.0 litres
- **Range**: 0.1+ litres  
- **Usage**: Used for nutrient dosing calculations

### Lights Schedule
- **Start Time**: Default 20:00 (configurable HH:MM format)
- **Duration**: Default 16 hours (range: 1-24 hours)
- **Behavior**:
  - Exactly two edges per day: ON at start time, OFF after duration
  - ±5s guards after each edge to re-assert intended state (idempotent)
  - Recomputes at startup, midnight, and after PUT /settings
  - No minute “catch-up” loop (prevents periodic dips)

### Configuration Methods

#### Web Dashboard
1. Navigate to http://192.168.88.49:8080
2. Find the "Settings" section
3. Adjust values as needed
4. Click "Save Settings"

#### API Endpoints
```bash
# Get current settings
curl http://192.168.88.49:8080/settings

# Update settings
curl -X PUT http://192.168.88.49:8080/settings \
  -H "Content-Type: application/json" \
  -d '{
    "system_volume_liters": 30.0,
    "lights_on_time": "20:00", 
    "lights_duration_hours": 18
  }'
```

#### Health & Debug Endpoints
```bash
# Health (readiness) summary
curl -s http://192.168.88.49:8080/health | jq .

# Relay status (per-relay state, reasons, timers)
curl -s http://192.168.88.49:8080/relay/status | jq .

# Last 50 relay toggle attempts (ts/name/on/via/result)
curl -s http://192.168.88.49:8080/debug/relay_requests | jq .
```

#### Alerts

Alerts (Telegram/Email) are OFF by default and only activate if configured via `.env`.
See `docs/alerts.md` for setup and testing instructions.

#### Database Migration
Settings are stored in SQLite. Run migration once:
```bash
sudo python3 /home/pi/RDWC-v4/scripts/migrate_settings.py
```

### Examples

**Evening Light Schedule** (avoids day heat):
- Start Time: `20:00` 
- Duration: `16` hours
- Result: Lights on 20:00 → 12:00 next day

**Large System Dosing**:
- System Volume: `50.0` litres
- Effect: Nutrient doses automatically scale to 2× standard amounts

**Seedling Schedule**:
- Start Time: `08:00`
- Duration: `14` hours  
- Result: Gentler 14-hour photoperiod for young plants