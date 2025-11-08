#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/pi/RDWC-v4')

from smbus2 import SMBus, i2c_msg
from time import sleep

bus = SMBus(1)
EC_ADDR = 0x64

print("=== EC Sensor Deep Diagnostic ===")

# Test 1: Factory reset?
print("\n1. Checking device info...")
cmd = b"i\x00"
bus.i2c_rdwr(i2c_msg.write(EC_ADDR, cmd))
sleep(0.5)
msg_r = i2c_msg.read(EC_ADDR, 32)
bus.i2c_rdwr(msg_r)
print(f"  Info: {bytes(msg_r)}")

# Test 2: Check status
print("\n2. Checking status...")
cmd = b"Status\x00"
bus.i2c_rdwr(i2c_msg.write(EC_ADDR, cmd))
sleep(0.5)
msg_r = i2c_msg.read(EC_ADDR, 32)
bus.i2c_rdwr(msg_r)
response = bytes(msg_r)
data = response[1:30].rstrip(b'\x00')
print(f"  Status response: {response[0]}, Data: {data}")

# Test 3: Check continuous mode status
print("\n3. Checking continuous mode...")
cmd = b"C,?\x00"
bus.i2c_rdwr(i2c_msg.write(EC_ADDR, cmd))
sleep(0.3)
msg_r = i2c_msg.read(EC_ADDR, 32)
bus.i2c_rdwr(msg_r)
response = bytes(msg_r)
data = response[1:30].rstrip(b'\x00')
print(f"  Continuous query: {response[0]}, Data: {data}")

# Test 4: Disable continuous aggressively
print("\n4. Disabling continuous mode...")
cmd = b"C,0\x00"
bus.i2c_rdwr(i2c_msg.write(EC_ADDR, cmd))
sleep(0.5)
msg_r = i2c_msg.read(EC_ADDR, 32)
bus.i2c_rdwr(msg_r)
print(f"  C,0 response: {bytes(msg_r)[0]}")

# Test 5: Try read with LONG settle (EC needs 900ms+)
print("\n5. Trying read with 1.5s settle...")
cmd = b"R\x00"
bus.i2c_rdwr(i2c_msg.write(EC_ADDR, cmd))
sleep(1.5)

# Poll multiple times
for attempt in range(5):
    msg_r = i2c_msg.read(EC_ADDR, 32)
    bus.i2c_rdwr(msg_r)
    response = bytes(msg_r)
    status = response[0]
    data = response[1:].rstrip(b'\\x00').decode('ascii', errors='ignore')
    print(f"  Poll #{attempt+1}: status={status}, data='{data}'")
    if status == 1:  # SUCCESS
        break
    sleep(0.3)

# Test 6: Check calibration status
print("\n6. Checking calibration...")
cmd = b"Cal,?\x00"
bus.i2c_rdwr(i2c_msg.write(EC_ADDR, cmd))
sleep(0.5)
msg_r = i2c_msg.read(EC_ADDR, 32)
bus.i2c_rdwr(msg_r)
response = bytes(msg_r)
data = response[1:30].rstrip(b'\x00')
print(f"  Cal status: {response[0]}, Data: {data}")

# Test 7: Check K value
print("\n7. Checking K value (probe constant)...")
cmd = b"K,?\x00"
bus.i2c_rdwr(i2c_msg.write(EC_ADDR, cmd))
sleep(0.5)
msg_r = i2c_msg.read(EC_ADDR, 32)
bus.i2c_rdwr(msg_r)
response = bytes(msg_r)
data = response[1:30].rstrip(b'\x00')
print(f"  K value: {response[0]}, Data: {data}")

bus.close()
print("\nDone.")
