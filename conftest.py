import os
import time
import pytest

# Use gpiozero's MockFactory so tests run on non-Pi hosts (e.g., Windows/macOS)
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")
os.environ.setdefault("GPIOZERO_PIN_NUMBERING", "BCM")

# Stateful GPIO mock for active-low relays (LOW=ON, HIGH=OFF)
# This ensures relay_guard verification passes after state changes
class StatefulGPIOShim:
    """Mock GPIO that tracks pin state changes for active-low relays."""
    BCM = 11
    BOARD = 10
    OUT = 0
    IN = 1
    HIGH = 1
    LOW = 0
    
    def __init__(self):
        self._pin_states = {}  # pin_number -> level (HIGH or LOW)
        self._pin_modes = {}   # pin_number -> mode (OUT or IN)
    
    def setmode(self, mode):
        pass
    
    def setwarnings(self, flag):
        pass
    
    def setup(self, pin, direction, initial=None):
        self._pin_modes[pin] = direction
        if initial is not None:
            self._pin_states[pin] = initial
        elif pin not in self._pin_states:
            # Default to HIGH (OFF for active-low)
            self._pin_states[pin] = self.HIGH
    
    def output(self, pin, level):
        self._pin_states[pin] = level
    
    def input(self, pin):
        # Return current state, default to HIGH (safe OFF) if not set
        return self._pin_states.get(pin, self.HIGH)
    
    def cleanup(self):
        self._pin_states.clear()
        self._pin_modes.clear()

# Install stateful GPIO mock before any imports that use GPIO
import sys
if 'RPi.GPIO' not in sys.modules:
    sys.modules['RPi.GPIO'] = StatefulGPIOShim()
else:
    # If already imported, replace it
    sys.modules['RPi.GPIO'] = StatefulGPIOShim()

# Reset relay state between tests to avoid inter-test coupling and set predictable lockouts
@pytest.fixture(autouse=True)
def reset_relays_between_tests():
    try:
        from app import relays_core as rc
        from app import relay_guard
        # Initialize relay_guard to prevent REJECTED errors
        relay_guard.init_safe()
        rc.initialize_all_safe_off()
        # Clear anti-flap and backdate last change to avoid MIN_OFF blocking first ON
        rc._antiflap_until.clear()
        rc._last_change_ts["lights"] = time.monotonic() - 1000
        # Predictable lockouts for tests: allow immediate ON, block immediate OFF
        rc.MIN_OFF["lights"] = 0
        rc.MIN_ON["lights"] = 10
    except Exception:
        # If import fails in some contexts, ignore to not break unrelated tests
        pass
    yield
