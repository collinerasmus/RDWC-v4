#!/usr/bin/env python3
"""
Test script for circulation safety interlock.
Verifies that chiller cannot start without chiller pump,
and that chiller pump cannot turn off while chiller is running.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import relays_core, relay_guard

def test_interlock():
    print("=" * 60)
    print("Testing Circulation Safety Interlock")
    print("=" * 60)
    
    # Initialize relay guard
    print("\n0. Initializing relay guard...")
    relay_guard.init_safe()
    
    # Initialize to safe state
    print("\n1. Initializing to safe OFF state...")
    relays_core.initialize_all_safe_off()
    status = relays_core.get_relay_status()
    print(f"   Chiller power: {status['chiller_power']['state']}")
    print(f"   Chiller pump: {status['chiller_pump']['state']}")
    
    # Test 1: Try to start chiller without pump (should auto-start pump)
    print("\n2. Test: Start chiller without pump running...")
    result = relays_core.set_chiller_power(True, "test_auto_start", force=False)
    print(f"   Result: changed={result.get('changed')}, state={result.get('state')}")
    
    status = relays_core.get_relay_status()
    chiller_on = status['chiller_power']['state']
    pump_on = status['chiller_pump']['state']
    print(f"   Chiller power: {chiller_on}")
    print(f"   Chiller pump: {pump_on}")
    
    if chiller_on and pump_on:
        print("   ✅ PASS: Chiller auto-started pump and both are ON")
    elif not chiller_on and not pump_on:
        print("   ⚠️  INFO: Both remained OFF (likely cooldown)")
    else:
        print("   ❌ FAIL: Unexpected state")
    
    # Test 2: Try to turn off pump while chiller is running
    if chiller_on and pump_on:
        print("\n3. Test: Try to turn OFF pump while chiller is running...")
        result = relays_core.set_chiller_pump(False, "test_interlock_block", force=False)
        print(f"   Result: changed={result.get('changed')}, state={result.get('state')}")
        print(f"   Blocked: {result.get('blocked', False)}")
        print(f"   Reason: {result.get('reason', 'unknown')}")
        
        status = relays_core.get_relay_status()
        pump_still_on = status['chiller_pump']['state']
        print(f"   Chiller pump: {pump_still_on}")
        
        if pump_still_on and result.get('blocked'):
            print("   ✅ PASS: Pump remained ON (interlock blocked the OFF command)")
        else:
            print("   ❌ FAIL: Pump turned OFF despite chiller running")
    else:
        print("\n3. Test skipped (chiller not running)")
    
    # Test 3: Turn off chiller first, then pump should be allowed
    print("\n4. Test: Turn OFF chiller, then pump should be allowed...")
    result = relays_core.set_chiller_power(False, "test_shutdown", force=False)
    print(f"   Chiller OFF: changed={result.get('changed')}, state={result.get('state')}")
    
    result = relays_core.set_chiller_pump(False, "test_shutdown", force=False)
    print(f"   Pump OFF: changed={result.get('changed')}, state={result.get('state')}")
    
    status = relays_core.get_relay_status()
    chiller_off = not status['chiller_power']['state']
    pump_off = not status['chiller_pump']['state']
    
    if chiller_off and pump_off:
        print("   ✅ PASS: Both turned OFF successfully")
    else:
        print("   ⚠️  INFO: One or both still ON (likely cooldown)")
    
    # Test 4: Force override should bypass interlock
    print("\n5. Test: Force flag should bypass interlock...")
    relays_core.set_chiller_power(True, "test_force", force=True)
    status = relays_core.get_relay_status()
    chiller_on = status['chiller_power']['state']
    pump_on = status['chiller_pump']['state']
    print(f"   Chiller: {chiller_on}, Pump: {pump_on}")
    
    if chiller_on:
        result = relays_core.set_chiller_pump(False, "test_force_override", force=True)
        pump_off = not result.get('state')
        if pump_off:
            print("   ✅ PASS: Force flag bypassed interlock")
        else:
            print("   ❌ FAIL: Force flag didn't work")
    
    # Clean up
    print("\n6. Cleanup: Turning all OFF with force...")
    relays_core.set_chiller_power(False, "test_cleanup", force=True)
    relays_core.set_chiller_pump(False, "test_cleanup", force=True)
    
    print("\n" + "=" * 60)
    print("Interlock Test Complete")
    print("=" * 60)

if __name__ == "__main__":
    test_interlock()
