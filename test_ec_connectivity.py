#!/usr/bin/env python3
"""Test if EC probe is responding at all."""
import sys
sys.path.insert(0, '.')
from app.ezo_i2c_stabilized import EZO, EC_ADDR
import time

try:
    ec = EZO(1, EC_ADDR, 'EC')
    print('Testing EC probe connectivity...\n')
    
    # Test basic read
    print('1. Basic read (should get all zeros initially)')
    raw = ec._read(32)
    print(f'   Raw: {raw.hex() if raw else "empty"}')
    
    # Test writing and reading
    print('\n2. Send "i" (info) command')
    ec._write(b'i')
    time.sleep(0.5)
    raw = ec._read(32)
    print(f'   Raw: {raw.hex() if raw else "empty"}')
    print(f'   String: {raw.decode("ascii", errors="ignore").strip() if raw else "N/A"}')
    
    # Test reading again
    print('\n3. Send "R" (read) command')
    ec._write(b'R')
    time.sleep(0.5)
    raw = ec._read(32)
    print(f'   Raw: {raw.hex() if raw else "empty"}')
    print(f'   String: {raw.decode("ascii", errors="ignore").strip() if raw else "N/A"}')
    
    ec.close()
    print('\nDone.')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
