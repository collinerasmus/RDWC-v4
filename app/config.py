import os

# BCM pins (override via env: PUMP_MAIN_PIN, PUMP_CHILLER_PIN)
PUMP_MAIN_PIN = int(os.getenv("PUMP_MAIN_PIN", "17"))      # GPIO17 (pin 11)
PUMP_CHILLER_PIN = int(os.getenv("PUMP_CHILLER_PIN", "27"))# GPIO27 (pin 13)

# Many relay boards are active LOW
RELAY_ACTIVE_LOW = os.getenv("RELAY_ACTIVE_LOW", "1") in ("1","true","True","yes")