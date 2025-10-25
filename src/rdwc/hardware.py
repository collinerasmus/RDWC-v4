import os
RUNNING_ON_PI = os.path.exists("/sys/firmware/devicetree/base/model")
try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:
    GPIO = None

class Relays:
    def __init__(self, pin_map: dict, active_high: bool = False):
        self.pin_map = pin_map
        self.active_high = active_high
        self.mock = not RUNNING_ON_PI or GPIO is None
        if not self.mock:
            GPIO.setmode(GPIO.BCM)
            for pin in pin_map.values():
                GPIO.setup(pin, GPIO.OUT)
                # default OFF (most 8ch relay boards are active LOW)
                GPIO.output(pin, GPIO.HIGH if not active_high else GPIO.LOW)

    def set(self, name: str, on: bool):
        pin = self.pin_map[name]
        if self.mock:
            print(f"[MOCK] Relay {name} ({pin}) -> {'ON' if on else 'OFF'}")
            return
        level = GPIO.HIGH if (on != self.active_high) else GPIO.LOW
        GPIO.output(pin, level)

    def cleanup(self):
        if not self.mock:
            GPIO.cleanup()