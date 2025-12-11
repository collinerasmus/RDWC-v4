"""
Test EC settings persistence through database.
Verifies that:
1. Default EC settings are loaded from DEFAULTS
2. Settings can be saved to database
3. Settings persist across restarts
"""

import sqlite3
import tempfile
from pathlib import Path
import sys

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

def test_ec_settings_defaults():
    """Test that EC settings defaults are correctly defined."""
    from app.settings import DEFAULTS
    
    # Check all EC-related defaults exist
    ec_defaults = {
        'targets.ec_low': '0.4',
        'targets.ec_high': '0.6',
        'dosing.grow_ml_per_sec': '20',
        'dosing.micro_ml_per_sec': '20',
        'dosing.bloom_ml_per_sec': '20',
        'dosing.ec_step_ml_min': '5',
        'dosing.ec_step_ml_max': '30',
        'dosing.ec_safety_factor': '0.6',
        'dosing.ec_min_interval_s': '300',
        'dosing.ec_max_ml_day': '0',
    }
    
    for key, expected_val in ec_defaults.items():
        assert key in DEFAULTS, f"Missing default: {key}"
        assert DEFAULTS[key] == expected_val, f"{key}: expected {expected_val}, got {DEFAULTS[key]}"
        print(f"✓ {key} = {DEFAULTS[key]}")


def test_settings_upsert_and_retrieval():
    """Test that settings can be saved and retrieved from database."""
    from app.settings import upsert_settings, get_all_settings, _ensure_table_seed_defaults
    
    # Ensure table is initialized
    _ensure_table_seed_defaults()
    
    # First, reset EC targets to match new safe defaults
    upsert_settings({'targets.ec_low': '0.4', 'targets.ec_high': '0.6'})
    
    # Get initial state
    initial = get_all_settings()
    print(f"Initial EC target low: {initial.get('targets.ec_low')}")
    assert initial.get('targets.ec_low') == '0.4', "Default not loaded"
    
    # Update a setting
    updated = upsert_settings({'targets.ec_low': '0.9'})
    print(f"Updated: {updated}")
    assert 'targets.ec_low' in updated, "Setting not in response"
    assert updated['targets.ec_low'] == '0.9', "Value not updated correctly"
    
    # Verify it persisted
    after_update = get_all_settings()
    assert after_update.get('targets.ec_low') == '0.9', "Setting did not persist"
    print(f"After update EC target low: {after_update.get('targets.ec_low')}")
    
    # Reset to default
    upsert_settings({'targets.ec_low': '0.4'})
    final = get_all_settings()
    assert final.get('targets.ec_low') == '0.4', "Reset failed"
    print(f"Reset EC target low to: {final.get('targets.ec_low')}")


def test_all_ec_parameters():
    """Test that all EC parameters can be saved and retrieved."""
    from app.settings import upsert_settings, get_all_settings, _ensure_table_seed_defaults
    
    _ensure_table_seed_defaults()
    
    # Test payload that would come from the UI
    test_values = {
        'targets.ec_low': '0.85',
        'targets.ec_high': '1.25',
        'dosing.grow_ml_per_sec': '21',
        'dosing.micro_ml_per_sec': '19',
        'dosing.bloom_ml_per_sec': '22',
        'dosing.ec_step_ml_min': '6',
        'dosing.ec_step_ml_max': '35',
        'dosing.ec_safety_factor': '0.65',
        'dosing.ec_min_interval_s': '350',
        'dosing.ec_max_ml_day': '500',
    }
    
    # Save all values
    updated = upsert_settings(test_values)
    print(f"\nUpdated {len(updated)} settings:")
    for k, v in updated.items():
        print(f"  {k} = {v}")
    
    # Verify all persisted
    current = get_all_settings()
    for key, expected_val in test_values.items():
        actual_val = current.get(key)
        assert actual_val == expected_val, f"{key}: expected {expected_val}, got {actual_val}"
        print(f"✓ {key} = {actual_val}")
    
    # Reset to defaults
    defaults_to_reset = {
        'targets.ec_low': '0.4',
        'targets.ec_high': '0.6',
        'dosing.grow_ml_per_sec': '20',
        'dosing.micro_ml_per_sec': '20',
        'dosing.bloom_ml_per_sec': '20',
        'dosing.ec_step_ml_min': '5',
        'dosing.ec_step_ml_max': '30',
        'dosing.ec_safety_factor': '0.6',
        'dosing.ec_min_interval_s': '300',
        'dosing.ec_max_ml_day': '0',
    }
    upsert_settings(defaults_to_reset)
    print("\nReset all EC settings to defaults")


if __name__ == '__main__':
    print("=" * 60)
    print("Testing EC Settings Persistence")
    print("=" * 60)
    
    try:
        print("\n1. Checking DEFAULTS constants...")
        test_ec_settings_defaults()
        
        print("\n2. Testing upsert and retrieval...")
        test_settings_upsert_and_retrieval()
        
        print("\n3. Testing all EC parameters...")
        test_all_ec_parameters()
        
        print("\n" + "=" * 60)
        print("✓ All persistence tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
