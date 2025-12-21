#!/usr/bin/env python3
"""Quick check of what pH targets the controller is using."""
import sys
sys.path.insert(0, '.')
from app.ph_control import _get_ph_targets

targets = _get_ph_targets()
print(f"pH Controller Targets: {targets}")
print(f"  Low:  {targets['low']}")
print(f"  High: {targets['high']}")
print(f"  Band: {targets['high'] - targets['low']:.2f}")
