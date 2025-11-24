#!/usr/bin/env python3
"""
Ensure Safe Defaults for pH Up Automation

Forces critical safety flags to OFF in runtime settings:
- safety.maintenance_override = false
- safety.allow_stale_on_override = false
- ph.auto_enabled = false

Usage:
    python3 tools/ensure_safe_defaults.py
"""
import sys
try:
    import requests
except ImportError:
    print("ERROR: requests module not found. Install with: pip3 install requests")
    sys.exit(1)

API_BASE = "http://127.0.0.1:8080"

SAFE_DEFAULTS = {
    "safety.maintenance_override": "false",
    "safety.allow_stale_on_override": "false",
    "ph.auto_enabled": "false",
}

def main():
    print("=== Ensure Safe Defaults ===\n")
    
    # Read current settings
    try:
        resp = requests.get(f"{API_BASE}/api/settings", timeout=5)
        resp.raise_for_status()
        settings = resp.json()
    except Exception as e:
        print(f"ERROR: Failed to read settings: {e}")
        sys.exit(1)
    
    # Check and update
    changes = []
    for key, safe_value in SAFE_DEFAULTS.items():
        current = settings.get(key, "")
        if current != safe_value:
            changes.append((key, current, safe_value))
    
    if not changes:
        print("✅ All safe defaults already set:")
        for key, val in SAFE_DEFAULTS.items():
            print(f"   {key} = {val}")
        print("\nNo changes needed.")
        return
    
    print(f"⚠️  Found {len(changes)} setting(s) to update:\n")
    for key, old, new in changes:
        print(f"   {key}: {old!r} → {new!r}")
    
    # Apply changes
    try:
        payload = {k: v for k, _, v in changes}
        resp = requests.put(f"{API_BASE}/api/settings", json=payload, timeout=5)
        resp.raise_for_status()
        result = resp.json()
        
        if result.get("ok"):
            print("\n✅ Safe defaults applied successfully.")
        else:
            print(f"\n❌ Failed to apply: {result}")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR applying settings: {e}")
        sys.exit(1)
    
    # Verify
    try:
        resp = requests.get(f"{API_BASE}/api/settings", timeout=5)
        resp.raise_for_status()
        settings = resp.json()
        
        print("\n📋 Current safe defaults:")
        all_good = True
        for key, expected in SAFE_DEFAULTS.items():
            actual = settings.get(key, "")
            status = "✅" if actual == expected else "❌"
            print(f"   {status} {key} = {actual}")
            if actual != expected:
                all_good = False
        
        if not all_good:
            print("\n⚠️  Some settings did not update correctly!")
            sys.exit(1)
        
        print("\n✅ PASS: All safe defaults verified.")
    except Exception as e:
        print(f"\n❌ ERROR verifying settings: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
