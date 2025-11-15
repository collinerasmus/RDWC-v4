#!/usr/bin/env python3
"""Quick script to reset sensor mode to auto and clear any stale state."""
from app.sensors_mode import get_sensor_mode, set_sensor_mode

print(f"Current mode: {get_sensor_mode()}")
set_sensor_mode("auto")
print(f"Reset to: {get_sensor_mode()}")
