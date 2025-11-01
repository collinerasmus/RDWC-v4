import os
import time
import pytest

# Use gpiozero's MockFactory so tests run on non-Pi hosts (e.g., Windows/macOS)
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")
os.environ.setdefault("GPIOZERO_PIN_NUMBERING", "BCM")

# Reset relay state between tests to avoid inter-test coupling and set predictable lockouts
@pytest.fixture(autouse=True)
def reset_relays_between_tests():
    try:
        from app import relays_core as rc
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
