#!/usr/bin/env python3
"""
Test script for the lights whitelist system
Tests the debug endpoints and blocking mechanism
"""

import sys
import os
import time
import requests
from typing import Dict, Any

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_debug_endpoints():
    """Test the debug endpoints"""
    print("\n🔍 Testing Debug Endpoints...")
    
    base_url = "http://localhost:8080"
    
    try:
        # Test lights allowed reasons endpoint
        print("📋 Testing /debug/lights_allowed...")
        response = requests.get(f"{base_url}/debug/lights_allowed")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Allowed reasons: {data['allowed_reasons']}")
            print(f"   Total: {data['total']}")
        else:
            print(f"❌ Failed: {response.status_code}")
    
        # Test lights log endpoint
        print("\n📊 Testing /debug/lights_log...")
        response = requests.get(f"{base_url}/debug/lights_log?last=10")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Event log retrieved: {data['total_events']} events")
            for event in data['events'][-3:]:  # Show last 3 events
                print(f"   {event['timestamp']}: {event['reason']} -> {event['final_state']} (blocked: {event.get('blocked', False)})")
        else:
            print(f"❌ Failed: {response.status_code}")
            
        # Test lights hold endpoint
        print("\n🛑 Testing /debug/lights_hold...")
        response = requests.post(f"{base_url}/debug/lights_hold", json={"seconds": 10})
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Hold set: {data['message']}")
        else:
            print(f"❌ Failed: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - make sure the server is running")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
        
    return True

def test_unauthorized_access():
    """Test that unauthorized access is blocked"""
    print("\n🚫 Testing Unauthorized Access Blocking...")
    
    base_url = "http://localhost:8080"
    
    try:
        # Try to control lights via /relay/lights endpoint
        print("🔐 Testing /relay/lights with unauthorized state change...")
        response = requests.post(f"{base_url}/relay/lights", json={"state": "on"})
        if response.status_code == 200:
            print("✅ Relay endpoint accessible (should be whitelisted as 'override')")
        else:
            print(f"❌ Relay endpoint failed: {response.status_code}")
            
        # Check the event log to see if it was logged
        response = requests.get(f"{base_url}/debug/lights_log?last=3")
        if response.status_code == 200:
            data = response.json()
            print("📜 Recent events:")
            for event in data['events']:
                blocked = event.get('blocked', False)
                status = "🚫 BLOCKED" if blocked else "✅ ALLOWED"
                print(f"   {status}: {event['reason']} by {event.get('caller', 'unknown')}")
        
    except Exception as e:
        print(f"❌ Error testing unauthorized access: {e}")
        return False
        
    return True

def test_whitelist_system():
    """Test the whitelist system directly"""
    print("\n🛡️ Testing Whitelist System Directly...")
    
    try:
        # Import the relays_core module to test directly
        from app.relays_core import set_lights, WHITELIST_LIGHTS, get_relay_event_log
        
        print(f"📋 Whitelist: {sorted(WHITELIST_LIGHTS)}")
        
        # Test allowed reason
        print("\n✅ Testing allowed reason: 'override'")
        result = set_lights(True, "override")
        print(f"   Result: {result}")
        
        # Test blocked reason
        print("\n❌ Testing blocked reason: 'unauthorized_test'")
        result = set_lights(False, "unauthorized_test")
        print(f"   Result: {result}")
        
        # Check event log
        print("\n📜 Recent events from direct calls:")
        events = get_relay_event_log("lights", last=5)
        for event in events[-2:]:  # Show last 2 events
            blocked = event.get('blocked', False)
            status = "🚫 BLOCKED" if blocked else "✅ ALLOWED"
            print(f"   {status}: {event['reason']} -> {event['final_state']}")
            
    except ImportError as e:
        print(f"❌ Cannot import modules (expected on Windows): {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing whitelist directly: {e}")
        return False
        
    return True

if __name__ == "__main__":
    print("🔬 RDWC-v4 Lights Whitelist System Test")
    print("=" * 50)
    
    # First try to test the whitelist system directly (will fail on Windows)
    test_whitelist_system()
    
    # Then test the API endpoints (requires server to be running)
    server_running = test_debug_endpoints()
    
    if server_running:
        test_unauthorized_access()
        print("\n✅ Tests completed! Check the /debug/lights_log endpoint for event history.")
    else:
        print("\n⚠️  API tests skipped - server not running")
        print("💡 To test API endpoints:")
        print("   1. Start server: python -m app.main")
        print("   2. Run this test script again")
    
    print("\n🎯 Next steps:")
    print("   - Deploy to Pi for real hardware testing")
    print("   - Monitor /debug/lights_log for unauthorized attempts")
    print("   - Check that 'off dips' are eliminated")