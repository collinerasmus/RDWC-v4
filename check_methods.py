from smbus2 import SMBus
b = SMBus(1)
print(f"write_i2c_block_data: {hasattr(b, 'write_i2c_block_data')}")
print(f"read_i2c_block_data: {hasattr(b, 'read_i2c_block_data')}")
print(f"i2c_rdwr: {hasattr(b, 'i2c_rdwr')}")
b.close()
