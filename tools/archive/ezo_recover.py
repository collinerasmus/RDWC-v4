from smbus2 import SMBus, i2c_msg
from time import sleep
from app.ezo_i2c_stabilized import EZO, PH_ADDR, EC_ADDR, RTD_ADDR

def ping(bus, addr):
    try:
        bus.i2c_rdwr(i2c_msg.write(addr, b""))
        return True
    except Exception:
        return False

if __name__ == "__main__":
    bus_num = 1
    with SMBus(bus_num) as bus:
        found = [hex(a) for a in (PH_ADDR, EC_ADDR, RTD_ADDR) if ping(bus, a)]
        print("Found:", found)

    for addr, name in [(PH_ADDR,"pH"), (EC_ADDR,"EC"), (RTD_ADDR,"RTD")]:
        try:
            dev = EZO(bus_num, addr, name)
            dev.init_once()
            try: print(name, "I:", dev.cmd("i"))
            except Exception: pass
            try: print(name, "Status:", dev.cmd("Status"))
            except Exception: pass
        except Exception as e:
            print(name, "error:", e)
        sleep(0.1)

    print("Recovery complete.")