#!/usr/bin/env python3
"""Test cmd() method vs raw I/O."""
import sys
sys.path.insert(0, '.')
from app.ezo_i2c_stabilized import EZO, EC_ADDR

ec = EZO(1, EC_ADDR, 'EC')
print('Using cmd() method:')
resp = ec.cmd('i', read_len=32, settle=0.5)
print(f'Info: {repr(resp)}')
resp = ec.cmd('R', read_len=32, settle=0.5)
print(f'Reading: {repr(resp)}')
ec.close()
