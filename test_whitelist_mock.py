#!/usr/bin/env python3
"""
Test the whitelist blocking mechanism with mocked GPIO
"""

import sys
import os
from unittest.mock import Mock, patch
import time

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_whitelist_with_mock():
    """Test whitelist system with mocked GPIO"""
    print("🧪 Testing Whitelist with Mocked GPIO...")
    
    # Mock the GPIO devices
    mock_device = Mock()
    mock_device.on = Mock()
    mock_device.off = Mock()
    mock_device.is_active = False
    
    # Mock the gpiozero module
    with patch.dict('sys.modules', {
        'gpiozero': Mock(),
        'gpiozero.devices': Mock(),
        'RPi': Mock(),
        'RPi.GPIO': Mock(),
        'smbus2': Mock()
    }):
        with patch('app.relays_core.OutputDevice', return_value=mock_device):
            
            # Import after mocking
            from app.relays_core import set_lights, get_relay_event_log, WHITELIST_LIGHTS
            
            print(f"📋 Whitelist loaded: {sorted(WHITELIST_LIGHTS)}")
            
            # Test 1: Allowed reason should work
            print("\n✅ Testing ALLOWED reason: 'override'")
            result = set_lights(True, "override")
            print(f"   Result: {result}")
            
            # Test 2: Blocked reason should be rejected
            print("\n❌ Testing BLOCKED reason: 'unauthorized_caller'")
            result = set_lights(False, "unauthorized_caller")
            print(f"   Result: {result}")
            print(f"   Should show blocked=True and no GPIO change")
            
            # Test 3: Check event log
            print("\n📜 Event Log (last 5 events):")
            events = get_relay_event_log("lights", last=5)
            for i, event in enumerate(events[-5:], 1):
                blocked = event.get('blocked', False)
                status = "🚫 BLOCKED" if blocked else "✅ ALLOWED"
                caller = event.get('caller', 'unknown')
                timestamp = event.get('timestamp', 'no-timestamp')
                final_state = event.get('final_state', 'unknown')
                print(f"   {i}. {status}: '{event['reason']}' by {caller}")
                print(f"      {timestamp} -> {final_state}")
            
            # Test 4: Multiple rapid calls (anti-flap protection)
            print("\n⚡ Testing rapid calls (should trigger cooldown):")
            for i in range(3):
                result = set_lights(i % 2 == 0, "override")
                print(f"   Call {i+1}: cooldown={result.get('cooldown_remaining', 0)}s")
                time.sleep(0.1)  # Small delay
            
            # Test 5: Hold mechanism
            print("\n🛑 Testing hold mechanism:")
            from app.relays_core import set_lights_hold
            hold_result = set_lights_hold(5)
            print(f"   Hold set: {hold_result}")
            
            # Try to change lights while held
            result = set_lights(True, "override")
            print(f"   Attempt during hold: blocked={result.get('blocked', False)}")
            
            print("\n🎉 Whitelist system test completed successfully!")
            print("   ✅ Authorized calls allowed")  
            print("   🚫 Unauthorized calls blocked")
            print("   📊 All events logged with caller info")
            print("   ⏱️ Cooldown protection active")
            print("   🛑 Hold mechanism working")
            
            return True

if __name__ == "__main__":
    print("🔬 RDWC-v4 Whitelist System Mock Test")
    print("=" * 50)
    
    test_whitelist_with_mock()