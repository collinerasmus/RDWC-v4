"""
Boot safe-off oneshot entrypoint

Forces all known relays to OFF using relays_core with force=True.
This is intended to run once at boot before the main service.
"""
from app.relays_core import RELAY_PINS, set_relay

def main():
    for name in RELAY_PINS.keys():
        try:
            set_relay(name, False, reason="boot_safe_off", force=True)
        except Exception as e:
            # Continue attempting other relays
            print(f"safeoff: failed to set {name} OFF: {e}")

if __name__ == "__main__":
    main()
