#!/usr/bin/env python3
"""
Test the interlock logic without GPIO (pure logic test).
Tests the actual if/else paths in set_chiller_power and set_chiller_pump.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_interlock_logic():
    print("=" * 60)
    print("Testing Interlock Logic (No GPIO)")
    print("=" * 60)
    
    from app import relays_core
    
    # Mock the current states
    print("\n1. Test: Chiller ON requires pump ON")
    print("   Setup: Pump=OFF, trying to start Chiller...")
    
    # Manually set pump to OFF
    relays_core._last_state['chiller_pump'] = False
    relays_core._last_state['chiller_power'] = False
    
    # Try to start chiller (pump is OFF)
    # This should trigger the interlock and try to auto-start pump
    # But since we're in test mode, the pump start will fail
    result = relays_core.set_chiller_power(True, "test_interlock", force=False)
    
    print(f"   Result: {result}")
    if result.get('blocked') or result.get('reason') == 'interlock_pump_failed':
        print("   ✅ PASS: Chiller blocked because pump couldn't start")
    else:
        print("   ❌ FAIL: Chiller should have been blocked")
    
    print("\n2. Test: Chiller pump OFF blocked when chiller is ON")
    print("   Setup: Chiller=ON, Pump=ON, trying to turn pump OFF...")
    
    # Manually set states
    relays_core._last_state['chiller_pump'] = True
    relays_core._last_state['chiller_power'] = True
    
    # Try to turn pump OFF while chiller is ON
    result = relays_core.set_chiller_pump(False, "test_interlock", force=False)
    
    print(f"   Result: {result}")
    if result.get('blocked') or result.get('reason') == 'interlock_chiller_running':
        print("   ✅ PASS: Pump OFF blocked because chiller is running")
    else:
        print("   ❌ FAIL: Pump OFF should have been blocked")
    
    print("\n3. Test: Pump OFF allowed when chiller is OFF")
    print("   Setup: Chiller=OFF, Pump=ON, trying to turn pump OFF...")
    
    # Set chiller OFF
    relays_core._last_state['chiller_power'] = False
    relays_core._last_state['chiller_pump'] = True
    
    # Try to turn pump OFF
    result = relays_core.set_chiller_pump(False, "test_normal_off", force=False)
    
    print(f"   Result: {result}")
    # Should not be blocked by interlock (might be blocked by cooldown, but that's OK)
    if result.get('reason') != 'interlock_chiller_running':
        print("   ✅ PASS: Pump OFF not blocked by interlock (chiller is OFF)")
    else:
        print("   ❌ FAIL: Pump OFF should not be blocked by interlock")
    
    print("\n4. Test: Force flag bypasses interlock")
    print("   Setup: Chiller=ON, Pump=ON, trying to turn pump OFF with force...")
    
    # Set states
    relays_core._last_state['chiller_power'] = True
    relays_core._last_state['chiller_pump'] = True
    
    # Try with force flag
    result = relays_core.set_chiller_pump(False, "test_force_bypass", force=True)
    
    print(f"   Result: {result}")
    if result.get('reason') != 'interlock_chiller_running':
        print("   ✅ PASS: Force flag bypassed interlock")
    else:
        print("   ❌ FAIL: Force flag should bypass interlock")
    
    print("\n" + "=" * 60)
    print("Interlock Logic Test Complete")
    print("=" * 60)

if __name__ == "__main__":
    test_interlock_logic()
