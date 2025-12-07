#!/usr/bin/env python3
"""Direct test of EC probe without locks."""
import sys
sys.path.insert(0, '.')
from app.ezo_i2c_stabilized import EZO, EC_ADDR
import time

try:
    ec = EZO(1, EC_ADDR, 'EC')
    print('EC probe connected at address 0x{:02x}'.format(EC_ADDR))
    
    # Turn off continuous mode first
    print('\n1. Turning off continuous mode...')
    resp = ec.cmd('C,0', read_len=0, settle=0.3)
    print('Response:', repr(resp))
    time.sleep(0.3)
    
    # Now try reading current value
    print('\n2. Reading current EC value...')
    resp = ec.cmd('R', read_len=32, settle=0.5)
    print('EC Reading:', repr(resp))
    
    # Try dry calibration
    print('\n3. Attempting dry calibration...')
    resp = ec.cmd('Cal,dry', read_len=32, settle=1.2)
    print('Dry cal response:', repr(resp))
    
    # Check calibration status
    print('\n4. Checking calibration status...')
    resp = ec.cmd('Cal,?', read_len=32, settle=0.5)
    print('Cal status:', repr(resp))
    
    ec.close()
    print('\nDone.')
except Exception as e:
    print('Error:', e)
    import traceback
    traceback.print_exc()
