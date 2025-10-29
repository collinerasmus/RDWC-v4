"""
Hardware control interface - now delegates to centralized relays_core.
Maintains compatibility with existing API while using the new idempotent relay system.
"""
from typing import Dict
from app.relays_core import (
    set_relay, get_relay_status, initialize_all_safe_off,
    REASON_APPLY_SETTINGS, REASON_OVERRIDE, REASON_EMERGENCY
)
import json
import os
import time

STATE_DIR = os.environ.get("RDWC_STATE_DIR", os.path.join(os.path.expanduser("~"), ".rdwc"))
STATE_FILE = os.path.join(STATE_DIR, "relay_state.json")

class RelayBank:
    """Hardware relay controller - now delegates to centralized relays_core."""
    
    def __init__(self):
        # Initialize all relays to safe state on first use
        initialize_all_safe_off()
    
    def names(self):
        """Get list of available relay names."""
        from app.relays_core import RELAY_PINS
        return list(RELAY_PINS.keys())
    
    def cleanup(self):
        """Clean up GPIO resources - handled by relays_core."""
        pass

    def _ensure_dir(self):
        """Ensure state directory exists."""
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
        except Exception:
            pass

    def save_state(self, allowlist=None):
        """Save relay states to file - now gets state from relays_core."""
        self._ensure_dir()
        status = get_relay_status()
        data = {name: info["state"] for name, info in status.items()}
        
        if allowlist:
            data = {k: v for k, v in data.items() if k in allowlist}
        
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"ts": int(time.time()), "relays": data}, f)
        os.replace(tmp, STATE_FILE)

    def load_state(self, allowlist=None, default_off=True):
        """Load relay states from file and apply them."""
        try:
            with open(STATE_FILE, "r") as f:
                payload = json.load(f)
                data = payload.get("relays", {})
        except Exception:
            data = {}
        
        for name in self.names():
            if allowlist and name not in allowlist:
                if default_off:
                    set_relay(name, False, "load_state_default_off")
                continue
            
            val = data.get(name)
            if isinstance(val, bool):
                set_relay(name, val, "load_state")

    def set(self, name: str, on: bool):
        """Set relay state - now handles chiller overrides and lights protection."""
        # Special handling for lights - must use whitelist protection
        if name == "lights":
            from app.relays_core import set_lights
            result = set_lights(on, REASON_OVERRIDE)  # API calls treated as manual overrides
            if result["changed"]:
                # Persist critical relay states
                self.save_state(allowlist=["main_pump", "chiller_pump", "chiller_power", "lights"])
            return
            
        # Check for chiller overrides before any chiller operation
        if name in ["chiller_pump", "chiller_power"]:
            try:
                from app.overrides import is_active
                override_mode = is_active()
                
                if override_mode == "force_on":
                    # Force chiller ON, ignore requested state
                    set_relay(name, True, REASON_OVERRIDE)
                    self.save_state(allowlist=["main_pump", "chiller_pump", "chiller_power"])
                    return
                elif override_mode == "force_off":
                    # Force chiller OFF, ignore requested state  
                    set_relay(name, False, REASON_OVERRIDE)
                    self.save_state(allowlist=["main_pump", "chiller_pump", "chiller_power"])
                    return
                # If "auto", proceed with normal operation
            except Exception as e:
                print(f"Warning: Override check failed for chiller: {e}")
                # Fall through to normal operation on error
        
        # Normal relay operation for non-lights relays
        result = set_relay(name, on, REASON_APPLY_SETTINGS)
        if result["changed"]:
            # Persist critical relay states
            self.save_state(allowlist=["main_pump", "chiller_pump", "chiller_power", "lights"])

    def get(self, name: str) -> bool:
        """Get current relay state."""
        status = get_relay_status()
        return status.get(name, {}).get("state", False)

    def status(self) -> Dict[str, bool]:
        """Get status of all relays."""
        status = get_relay_status()
        return {name: info["state"] for name, info in status.items()}

# Back-compat shim for old "pump_*" usage in routes:
class PumpController:
    def __init__(self, relay_bank: RelayBank):
        self._bank = relay_bank
        self._main_name = "main_pump"
        self._chiller_name = "chiller_pump"

    def set(self, name: str, on: bool):
        if name == "main":
            self._bank.set(self._main_name, on)
        elif name == "chiller":
            self._bank.set(self._chiller_name, on)
        else:
            raise ValueError("unknown pump")

    def get(self, name: str) -> bool:
        if name == "main":
            return self._bank.get(self._main_name)
        if name == "chiller":
            return self._bank.get(self._chiller_name)
        raise ValueError("unknown pump")

    def status(self):
        return {"main": self.get("main"), "chiller": self.get("chiller")}