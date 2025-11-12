#!/usr/bin/env python3
"""
Test script for the new centralized relay control system.
Tests idempotent control, cooldowns, and anti-flap protection.
"""

import time
from app.relays_core import (
    set_relay, get_relay_status, set_lights,
    REASON_APPLY_SETTINGS, REASON_EMERGENCY
)

def test_is_within_window():
    """Test the lights window logic"""
    from app.scheduler import Scheduler
    from app.hardware import RelayBank
    
    scheduler = Scheduler(RelayBank())
    
    # Test same-day window (8:00 to 18:00)
    assert scheduler.is_within_window(480, 480, 1080) == True   # 8:00 in window
    assert scheduler.is_within_window(900, 480, 1080) == True   # 15:00 in window
    assert scheduler.is_within_window(1080, 480, 1080) == False # 18:00 not in window
    assert scheduler.is_within_window(300, 480, 1080) == False  # 5:00 not in window
    
    # Test midnight wrap (22:00 to 6:00)
    assert scheduler.is_within_window(1320, 1320, 360) == True  # 22:00 in window
    assert scheduler.is_within_window(60, 1320, 360) == True    # 1:00 in window
    assert scheduler.is_within_window(360, 1320, 360) == False  # 6:00 not in window
    assert scheduler.is_within_window(720, 1320, 360) == False  # 12:00 not in window
    
    print("✅ Window logic tests passed")

def test_idempotent_control():
    """Test that repeated identical commands are no-ops"""
    
    # First call should change state
    result1 = set_lights(True, REASON_APPLY_SETTINGS)
    assert result1["changed"] == True
    assert result1["state"] == True
    
    # Second identical call should be no-op
    result2 = set_lights(True, REASON_APPLY_SETTINGS)
    assert result2["changed"] == False
    assert result2["reason"] == "idempotent"
    
    print("✅ Idempotent control test passed")

def test_cooldown_protection():
    """Test that cooldown periods prevent rapid switching"""
    
    # Turn lights on
    result1 = set_lights(True, REASON_APPLY_SETTINGS)
    assert result1["changed"] == True
    
    # Try to turn off immediately - should be blocked by MIN_ON
    result2 = set_lights(False, REASON_APPLY_SETTINGS)
    assert result2["changed"] == False
    assert result2["reason"] == "cooldown"
    assert result2["cooldown_remaining"] > 0
    
    # Force should override cooldown
    result3 = set_lights(False, REASON_EMERGENCY, force=True)
    assert result3["changed"] == True
    
    print("✅ Cooldown protection test passed")

def test_relay_status():
    """Test relay status reporting"""
    
    # Set a relay state
    set_relay("main_pump", True, "test")
    
    # Check status
    status = get_relay_status()
    assert "main_pump" in status
    assert status["main_pump"]["state"] == True
    assert status["main_pump"]["last_reason"] == "test"
    assert status["main_pump"]["seconds_since_change"] >= 0
    
    print("✅ Relay status test passed")

def main():
    """Run all tests"""
    print("🧪 Testing new relay control system...")
    
    try:
        test_is_within_window()
        test_idempotent_control()
        test_cooldown_protection() 
        test_relay_status()
        
        print("\n✅ All tests passed! Relay control system is working correctly.")
        
        # Show current status
        print("\n📊 Current Relay Status:")
        status = get_relay_status()
        for name, info in status.items():
            state_str = "ON" if info["state"] else "OFF"
            print(f"  {name}: {state_str} (reason: {info['last_reason']}, {info['seconds_since_change']}s ago)")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise

if __name__ == "__main__":
    main()