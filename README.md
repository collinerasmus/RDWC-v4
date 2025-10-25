# RDWC v4 — simple & reliable

Single FastAPI service with one control loop for RDWC.
- Sensors: Atlas EZO on I²C (pH=0x63, EC=0x64, RTD=0x66)
- Relays (BCM): 5,6,13,19,26,16,20,21 per your wiring
- Target pH ~5.8–6.2; weekly res maintenance
See `.env.example` for configuration. Start minimal, expand in tiny phases.