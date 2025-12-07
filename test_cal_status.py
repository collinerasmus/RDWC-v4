#!/usr/bin/env python3
"""Test calibration command status codes."""
import sys
sys.path.insert(0, '.')
from app.ezo_i2c_stabilized import EZO, EC_ADDR
import time

try:
    ec = EZO(1, EC_ADDR, 'EC')
    print('Testing calibration command status codes...\n')
    
    # Test 1: Cal,clear
    print('1. Cal,clear')
    ec._write(b'Cal,clear')
    time.sleep(1.5)
    raw = ec._read(32)
    print(f'   Raw: {raw.hex() if raw else "empty"}')
    print(f'   Status byte: 0x{raw[0]:02x} ({raw[0]}) if raw else "N/A"')
    print(f'   String: {raw[1:].decode("ascii", errors="ignore").strip() if raw else "N/A"}')
    
    time.sleep(0.5)
    
    # Test 2: Cal,dry (in air)
    print('\n2. Cal,dry')
    ec._write(b'Cal,dry')
    time.sleep(1.5)
    raw = ec._read(32)
    print(f'   Raw: {raw.hex() if raw else "empty"}')
    print(f'   Status byte: 0x{raw[0]:02x} ({raw[0]}) if raw else "N/A"')
    print(f'   String: {raw[1:].decode("ascii", errors="ignore").strip() if raw else "N/A"}')
    
    time.sleep(0.5)
    
    # Test 3: Cal,? (check status)
    print('\n3. Cal,? (check calibration status)')
    ec._write(b'Cal,?')
    time.sleep(0.5)
    raw = ec._read(32)
    print(f'   Raw: {raw.hex() if raw else "empty"}')
    print(f'   Status byte: 0x{raw[0]:02x} ({raw[0]}) if raw else "N/A"')
    print(f'   String: {raw[1:].decode("ascii", errors="ignore").strip() if raw else "N/A"}')
    
    ec.close()
    print('\nDone.')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
