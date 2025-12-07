#!/usr/bin/env python3
"""Direct EC low calibration test."""
import sys
sys.path.insert(0, '.')
from app.ezo_i2c_stabilized import EZO, EC_ADDR
import time

try:
    ec = EZO(1, EC_ADDR, 'EC')
    print('EC probe connected at address 0x{:02x}'.format(EC_ADDR))
    
    # Clear calibration first
    print('\n1. Clearing calibration...')
    resp = ec.cmd('Cal,clear', read_len=32, settle=1.2)
    print('Clear response:', repr(resp))
    time.sleep(0.5)
    
    # Dry calibration
    print('\n2. Dry calibration (in air)...')
    resp = ec.cmd('Cal,dry', read_len=32, settle=1.2)
    print('Dry response:', repr(resp))
    time.sleep(0.5)
    
    # Now test reading in 84 solution
    print('\n3. Attempting low calibration at 84 µS/cm...')
    resp = ec.cmd('Cal,low,84', read_len=32, settle=1.2)
    print('Low cal response:', repr(resp))
    time.sleep(0.5)
    
    # Check status
    print('\n4. Checking calibration status...')
    resp = ec.cmd('Cal,?', read_len=32, settle=0.5)
    print('Cal status:', repr(resp))
    
    # Take a reading
    print('\n5. Taking EC reading...')
    resp = ec.cmd('R', read_len=32, settle=0.5)
    print('EC reading:', repr(resp))
    
    ec.close()
    print('\nDone.')
except Exception as e:
    print('Error:', e)
    import traceback
    traceback.print_exc()
