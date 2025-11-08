#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/pi/RDWC-v4')

from smbus2 import SMBus, i2c_msg
from time import sleep

def test_ezo_raw(addr, name):
    print(f"\n=== Testing {name} at 0x{addr:02X} ===")
    bus = SMBus(1)
    
    try:
        # Test 1: Send "i" command (info)
        print("Sending 'i' command...")
        cmd = b"i\x00"
        msg_w = i2c_msg.write(addr, cmd)
        bus.i2c_rdwr(msg_w)
        sleep(0.5)
        
        # Read response
        msg_r = i2c_msg.read(addr, 32)
        bus.i2c_rdwr(msg_r)
        response = bytes(msg_r)
        status = response[0]
        data = response[1:].rstrip(b'\x00').decode('ascii', errors='ignore')
        print(f"  Status: {status}, Data: '{data}'")
        
        # Test 2: Disable continuous mode
        print("Disabling continuous mode (C,0)...")
        cmd = b"C,0\x00"
        msg_w = i2c_msg.write(addr, cmd)
        bus.i2c_rdwr(msg_w)
        sleep(0.3)
        
        msg_r = i2c_msg.read(addr, 32)
        bus.i2c_rdwr(msg_r)
        response = bytes(msg_r)
        print(f"  C,0 response status: {response[0]}")
        
        # Test 3: Try read command
        print("Sending 'R' command...")
        cmd = b"R\x00"
        msg_w = i2c_msg.write(addr, cmd)
        bus.i2c_rdwr(msg_w)
        sleep(1.5)
        
        msg_r = i2c_msg.read(addr, 32)
        bus.i2c_rdwr(msg_r)
        response = bytes(msg_r)
        status = response[0]
        data = response[1:].rstrip(b'\x00').decode('ascii', errors='ignore')
        print(f"  Status: {status}, Data: '{data}'")
        
    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        bus.close()

if __name__ == "__main__":
    test_ezo_raw(0x66, "RTD")
    test_ezo_raw(0x63, "pH")
    test_ezo_raw(0x64, "EC")
