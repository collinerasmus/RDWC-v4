#!/bin/bash
# Test script for new RDWC-v4 features using curl
# Tests both chiller override system and temperature compensation

PI_IP="192.168.88.49"
API_BASE="http://${PI_IP}:8000"

echo "=== Testing RDWC-v4 New Features ==="

# Test 1: Check current overrides status
echo -e "\n[Test 1] Checking current overrides status..."
curl -s -X GET "${API_BASE}/overrides" | jq . || echo "ERROR: Could not get overrides status"

# Test 2: Set chiller to force_on for 30 minutes
echo -e "\n[Test 2] Setting chiller to force_on for 30 minutes..."
curl -s -X PUT "${API_BASE}/overrides" \
  -H "Content-Type: application/json" \
  -d '{"chiller_mode": "force_on", "hold_minutes": 30}' | jq . || echo "ERROR: Could not set override"

# Test 3: Check sensor readings (should show temperature compensation)
echo -e "\n[Test 3] Checking sensor readings with temperature compensation..."
curl -s -X GET "${API_BASE}/sensors" | jq . || echo "ERROR: Could not get sensor readings"

# Test 4: Wait a moment then clear the override
sleep 5
echo -e "\n[Test 4] Clearing chiller override..."
curl -s -X PUT "${API_BASE}/overrides" \
  -H "Content-Type: application/json" \
  -d '{"chiller_mode": "auto", "hold_minutes": 0}' | jq . || echo "ERROR: Could not clear override"

echo -e "\n=== Test Complete ==="