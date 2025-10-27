import os

# Relay polarity (most 4/8-ch boards are active-LOW). Override via env if needed.
RELAY_ACTIVE_LOW = os.getenv("RELAY_ACTIVE_LOW", "1") in ("1","true","True","yes")

# Canonical GPIO map from project docs (BCM numbering)
PINMAP = {
    "ph_up":        int(os.getenv("PIN_PH_UP",        "5")),   # phys 29
    "grow_pump":    int(os.getenv("PIN_GROW_PUMP",    "6")),   # phys 31
    "micro_pump":   int(os.getenv("PIN_MICRO_PUMP",   "13")),  # phys 33
    "bloom_pump":   int(os.getenv("PIN_BLOOM_PUMP",   "19")),  # phys 35
    "main_pump":    int(os.getenv("PIN_MAIN_PUMP",    "26")),  # phys 37
    "chiller_pump": int(os.getenv("PIN_CHILLER_PUMP", "16")),  # phys 36
    "water_chiller":int(os.getenv("PIN_WATER_CHILLER","20")),  # phys 38
    "grow_lights":  int(os.getenv("PIN_GROW_LIGHTS",  "21")),  # phys 40
}

# Back-compat for old endpoints that used only "main/chiller":
DEFAULT_MAIN   = PINMAP["main_pump"]
DEFAULT_CHILLER= PINMAP["chiller_pump"]