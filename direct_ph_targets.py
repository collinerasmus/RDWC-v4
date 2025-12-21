#!/usr/bin/env python3
"""Direct test of _get_ph_targets."""
import sys
sys.path.insert(0, '.')

# Patch to avoid import issues
import os
os.environ['RDWC_MOCK'] = '1'

from app.ph_control import _get_ph_targets

targets = _get_ph_targets()
print(f"Controller returns: {targets}")
print(f"This should match what the chart receives from /api/ph/status")
