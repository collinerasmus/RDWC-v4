#!/usr/bin/env python3
"""Direct low-level I2C test."""
from smbus2 import SMBus, i2c_msg
import time

bus = SMBus(1)
try:
    # Write 'i' command
    print('Writing i (ID) command to 0x64...')
    msg = i2c_msg.write(0x64, b'i')
    bus.i2c_rdwr(msg)
    time.sleep(0.5)
    
    # Read response
    print('Reading 32 bytes...')
    msg = i2c_msg.read(0x64, 32)
    bus.i2c_rdwr(msg)
    resp = bytes(msg)
    print('Raw response:', resp)
    print('String:', resp.decode('ascii', errors='ignore').strip())
finally:
    bus.close()
