#!/usr/bin/env python3
import sys
sys.path.insert(0, "/home/pi/RDWC-v4")
from app.relays_core import get_relay_status

rs = get_relay_status()
print("Relay status keys:", list(rs.keys()) if rs else None)
print("estop value:", rs.get("estop"))
print("estop is False:", rs.get("estop") is False)
print("system component:", bool(rs and (rs.get("estop") is False)))
print("relays dict:", rs.get("relays", {}))
print("lights key exists:", "lights" in rs.get("relays", {}))
print("lights component:", bool(rs and "lights" in rs.get("relays", {})))
