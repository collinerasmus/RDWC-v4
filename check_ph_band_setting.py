#!/usr/bin/env python3
"""Check pH band setting."""
import sys
sys.path.insert(0, '.')
from app.settings import get_all_settings

settings = get_all_settings()
print("=== pH Related Settings ===")
print(f"targets.ph_low: {settings.get('targets.ph_low')}")
print(f"targets.ph_high: {settings.get('targets.ph_high')}")
print(f"targets.ph_band: {settings.get('targets.ph_band')}")
print(f"general.grow_start_date: {settings.get('general.grow_start_date')}")
