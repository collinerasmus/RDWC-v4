from app.infra.i2c_bus import get_bus
b = get_bus()
print(f"Bus type: {type(b)}")
print(f"Has write_i2c_block_data: {hasattr(b, 'write_i2c_block_data')}")
print(f"Has read_i2c_block_data: {hasattr(b, 'read_i2c_block_data')}")
print(f"Methods: {[m for m in dir(b) if 'write' in m or 'read' in m]}")
