"""
Test calibration flag logic fix for /api/sensors endpoint
"""


def test_ph_calibration_logic():
    """Test the improved pH calibration detection logic"""
    
    # Mock settings with various scenarios
    test_cases = [
        # (ph_mid, ph_low, expected_result, description)
        ("7.0", "4.0", True, "Both mid and low present"),
        ("7.0", "", True, "Only mid present"),
        ("", "4.0", True, "Only low present"),
        (None, "4.0", True, "Mid is None, low present"),
        ("7.0", None, True, "Low is None, mid present"),
        ("", "", False, "Both empty strings"),
        (None, None, False, "Both None"),
        ("0", "0", False, "Both zero (uncalibrated)"),
        ("0", "4.0", True, "Mid is zero, low is valid"),
        ("7.0", "0", True, "Low is zero, mid is valid"),
        ("", None, False, "Mixed empty/None"),
    ]
    
    for ph_mid, ph_low, expected, desc in test_cases:
        # Original buggy logic
        old_calibrated = bool(ph_mid or ph_low)
        
        # New fixed logic
        new_calibrated = bool(ph_mid and ph_mid != "0") or bool(ph_low and ph_low != "0")
        
        print(f"{desc}: mid={ph_mid}, low={ph_low}")
        print(f"  Old logic: {old_calibrated}, New logic: {new_calibrated}, Expected: {expected}")
        
        assert new_calibrated == expected, f"Failed for {desc}"
        

def test_ec_calibration_logic():
    """Test the improved EC calibration detection logic"""
    
    test_cases = [
        # (ec_low_us, expected_result, description)
        ("1413", True, "Standard 1413 µS/cm calibration"),
        ("0", False, "Zero means uncalibrated"),
        ("", False, "Empty string"),
        (None, False, "None value"),
        ("12880", True, "High standard solution"),
        ("100", True, "Custom low value"),
        ("invalid", False, "Non-numeric string"),
        ("0.0", False, "Float zero"),
    ]
    
    for ec_low_us, expected, desc in test_cases:
        # Original logic
        old_calibrated = (ec_low_us != "0" and ec_low_us != "" and ec_low_us is not None)
        
        # New fixed logic
        try:
            new_calibrated = bool(ec_low_us and ec_low_us != "0" and ec_low_us != "" and float(ec_low_us) > 0)
        except (ValueError, TypeError):
            new_calibrated = False
        
        print(f"{desc}: ec_low_us={ec_low_us}")
        print(f"  Old logic: {old_calibrated}, New logic: {new_calibrated}, Expected: {expected}")
        
        assert new_calibrated == expected, f"Failed for {desc}"


def test_cache_age_logic():
    """Test the improved cache age calculation"""
    import time
    
    test_cases = [
        # (_last_t, expected_age_is_none, description)
        (0.0, True, "Uninitialized _last_t"),
        (0, True, "Zero _last_t (int)"),
        (time.time() - 30, False, "Recent update 30s ago"),
        (time.time() - 600, False, "Old update 10min ago"),
    ]
    
    for _last_t, age_should_be_none, desc in test_cases:
        # Old logic (buggy for _last_t = 0)
        old_age = max(0.0, time.time() - _last_t)
        
        # New fixed logic
        new_age = max(0.0, time.time() - _last_t) if _last_t > 0 else None
        
        print(f"{desc}: _last_t={_last_t}")
        print(f"  Old age: {old_age}, New age: {new_age}")
        
        if age_should_be_none:
            assert new_age is None, f"Expected None for {desc}"
            assert old_age > 1000000000, f"Old logic gives huge age for {desc}"  # 31+ years
        else:
            assert new_age is not None and new_age < 700, f"Expected reasonable age for {desc}"


if __name__ == "__main__":
    print("=== Testing pH Calibration Logic ===")
    test_ph_calibration_logic()
    print("\n=== Testing EC Calibration Logic ===")
    test_ec_calibration_logic()
    print("\n=== Testing Cache Age Logic ===")
    test_cache_age_logic()
    print("\n✅ All logic tests passed!")
