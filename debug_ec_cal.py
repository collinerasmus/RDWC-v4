#!/usr/bin/env python3
"""Detailed EC calibration debugging."""
import sys
sys.path.insert(0, '.')
from app.ezo_i2c_stabilized import EZO, EC_ADDR
import time

def hex_dump(data, label=""):
    if label:
        print(f"{label}:", end=" ")
    print(" ".join(f"{b:02x}" for b in data[:20]), "...")

try:
    ec = EZO(1, EC_ADDR, 'EC')
    print('=== EC Calibration Debugging ===\n')
    
    # 1. Read initial status
    print('1. Reading initial Cal status...')
    resp = ec.cmd('Cal,?', read_len=32, settle=0.5)
    print(f'   Response: {repr(resp)}')
    
    # 2. Clear calibration with explicit verification
    print('\n2. Clearing calibration...')
    resp = ec.cmd('Cal,clear', read_len=32, settle=1.5)
    print(f'   Response: {repr(resp)}')
    time.sleep(0.5)
    
    resp = ec.cmd('Cal,?', read_len=32, settle=0.5)
    print(f'   Status after clear: {repr(resp)}')
    
    # 3. Dry calibration
    print('\n3. Dry calibration (in air)...')
    resp = ec.cmd('Cal,dry', read_len=32, settle=1.5)
    print(f'   Response: {repr(resp)}')
    time.sleep(0.5)
    
    resp = ec.cmd('Cal,?', read_len=32, settle=0.5)
    print(f'   Status after dry: {repr(resp)}')
    
    # 4. Read value in air
    print('\n4. EC reading in air...')
    resp = ec.cmd('R', read_len=32, settle=0.5)
    print(f'   Reading: {repr(resp)}')
    
    # 5. Now attempt low calibration
    print('\n5. Low calibration at 84 µS/cm...')
    print('   Ensure probe is in 84 solution!')
    input('   Press ENTER when ready...')
    
    # Disable continuous mode first
    resp = ec.cmd('C,0', read_len=0, settle=0.3)
    print(f'   Continuous mode off: {repr(resp)}')
    time.sleep(0.3)
    
    # Read the current value to verify probe is responsive
    resp = ec.cmd('R', read_len=32, settle=0.5)
    print(f'   Current reading: {repr(resp)}')
    
    # Send low calibration with LONG settle time
    print('   Sending Cal,low,84...')
    resp = ec.cmd('Cal,low,84', read_len=32, settle=2.0)
    print(f'   Response: {repr(resp)}')
    time.sleep(1.0)
    
    # Verify status
    resp = ec.cmd('Cal,?', read_len=32, settle=0.5)
    print(f'   Status after low cal: {repr(resp)}')
    
    # Read new value
    resp = ec.cmd('R', read_len=32, settle=0.5)
    print(f'   Reading after low cal: {repr(resp)}')
    
    ec.close()
    print('\nDone.')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
