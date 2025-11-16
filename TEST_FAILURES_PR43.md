# Pre-existing Test Failures from PR #43

## Summary

While stabilizing CI in [PR #43](https://github.com/collinerasmus/RDWC-v4/pull/43) (Stabilize CI by adding timeouts to pytest tests, fixing test deadlock, and restoring UI layout), local and CI runs completed in ~31s but 4 pre-existing failing tests were identified that are unrelated to the CI stabilization changes.

**Test Results:** 37 passed, 4 failed, 3 warnings in 31.27s

**Branch:** `copilot/stabilize-ci-tests` (PR #43)

**Test Command:** `pytest --timeout=120 --durations=25 -q --tb=short`

---

## Failing Tests Details

### 1. test_relays_restore_persistence.py::test_boot_safe_off_does_not_persist

**Node ID:** `tests/test_relays_restore_persistence.py::test_boot_safe_off_does_not_persist`

**Failure:**
```
AssertionError: assert 0 == 1
 +  where 0 = len([])
```

**Description:** 
This test verifies that the `initialize_all_safe_off()` function does NOT persist state to disk (no call to `_save_state()`). The test expects exactly 1 call to `_save_state()` after a normal relay change, but expects 0 calls after `initialize_all_safe_off()`.

**Root Cause:**
The first assertion `assert len(calls) == 1` (line 20) is failing, indicating that `set_relay()` is not calling `_save_state()` at all. This could be due to:
- The relay guard system preventing the state change
- The mock/monkeypatch setup not working correctly
- A change in the relay persistence behavior

**Test Code (excerpt):**
```python
# Normal change should persist once
rc.set_relay('main_pump', True, rc.REASON_OVERRIDE, force=True)
assert len(calls) == 1  # FAILING HERE: calls is empty []
```

**Priority:** Medium - This is a relay persistence test that validates boot safety behavior.

**Recommendation:** 
- Investigate why `set_relay()` is not calling `_save_state()` 
- Check if relay guard initialization or state is preventing the change
- Review recent changes to `app/relays_core.py` that might affect persistence

---

### 2. test_sensor_freshness.py::test_sensor_freshness_120s_aged

**Node ID:** `tests/test_sensor_freshness.py::test_sensor_freshness_120s_aged`

**Failure:**
```
AssertionError: Expected yellow (60-300s), got red
assert 'red' == 'yellow'
  
  - yellow
  + red
```

**Description:**
This test validates sensor health state indicators for aged readings. A 120-second-old reading should return `health_state="yellow"` (stale but <300s), but is returning `"red"` instead.

**Test Logic:**
- Insert reading with age=120s
- Expected: `health_state="yellow"` (60s < age < 300s)
- Actual: `health_state="red"`

**Root Cause:**
The health state thresholds may have been adjusted or the calculation logic changed:
- Yellow range should be: 60s ≤ age < 300s
- Red range should be: age ≥ 300s
- The 120s reading is incorrectly categorized as red

**Priority:** Medium - Sensor health indicators are important for UI feedback but not critical for functionality.

**Recommendation:**
- Review `/api/sensors` endpoint health state logic in `app/main.py`
- Check if health state thresholds were modified (should be: green <60s, yellow 60-300s, red ≥300s)
- Consider if this is intentional behavior change that requires test update

---

### 3. test_stale_override_gating.py::test_allows_when_both_flags_true_and_gpio_finally

**Node ID:** `tests/test_stale_override_gating.py::test_allows_when_both_flags_true_and_gpio_finally`

**Failure:**
```
AssertionError: assert False is True
 +  where False = <built-in method get of dict object>('ok')
 +    where {'error': 'ph_dose', 'ok': False, 'rowid': 1}.get
```

**Description:**
This test validates that pH dosing is allowed when BOTH `maintenance_override=true` AND `allow_stale_on_override=true` are set, even with stale sensor data. The test expects `ok=True` but gets `ok=False` with error `'ph_dose'`.

**Test Setup:**
```python
'safety.maintenance_override': 'true',
'safety.allow_stale_on_override': 'true',
```

**Expected Behavior:**
- When both flags are true, pH dose should proceed despite stale sensors
- GPIO operations should execute (LOW then HIGH)

**Actual Behavior:**
- Dose blocked with `ok=False, error='ph_dose'`
- Response includes `rowid=1` suggesting DB write occurred but operation failed

**Console Output Present:**
```
[pH] GPIO LOW (ON) ms=200 on dosing_ph_up
[pH] GPIO HIGH (OFF) dosing_ph_up
```

**Relay Guard Logs:**
```
WARNING [GuardSet] GUARD_MISMATCH initial name=dosing_ph_up bcm=5 expected=LOW actual=HIGH reason=ph_dose
ERROR [GuardSet] GUARD_MISMATCH persistent name=dosing_ph_up bcm=5 expected=LOW actual=HIGH reason=ph_dose COERCE_SHADOW
```

**Root Cause:**
The relay guard system is detecting a GPIO mismatch where the pin is HIGH when it expects LOW. This is likely a test fixture issue with GPIO mocking:
- The test uses mock GPIO pins
- The guard verification is reading HIGH when it expects LOW after setting the relay
- This causes the operation to appear failed even though GPIO operations printed correctly

**Priority:** High - This tests critical safety override behavior for maintenance operations.

**Recommendation:**
- Review relay_guard GPIO state verification logic in mock environments
- Ensure test fixtures properly initialize GPIO mock state
- Consider if guard verification should be relaxed in test/mock mode
- Check if `GPIOZERO_PIN_FACTORY=mock` is properly configured

---

### 4. tmp_debug_test.py::test_debug_relay_on

**Node ID:** `tests/tmp_debug_test.py::test_debug_relay_on`

**Failure:**
```
AssertionError: assert False is True
 +  where False = <built-in method get of dict object>('state')
```

**Description:**
Simple debug test that attempts to turn on `main_pump` relay and verify its state. The relay state remains `False` after attempting to set it to `True`.

**Test Code:**
```python
assert get_estop_status() is False
r = set_relay('main_pump', True, 'debug')
print('set_relay result:', r)
s = get_relay_status()
assert s.get('main_pump',{}).get('state') is True  # FAILS: state is False
```

**Console Output:**
```
set_relay result: {'changed': False, 'state': False, 'reason': 'debug', 'cooldown_remaining': 0, 'guard': {'ok': False, 'coerced': True, 'retries': 1}}
status main_pump: {'state': False, 'last_reason': 'unknown', 'seconds_since_change': 1000, ...}
```

**Relay Guard Logs:**
```
WARNING [GuardSet] GUARD_MISMATCH initial name=main_pump bcm=26 expected=LOW actual=HIGH reason=debug
ERROR [GuardSet] GUARD_MISMATCH persistent name=main_pump bcm=26 expected=LOW actual=HIGH reason=debug COERCE_SHADOW
```

**Root Cause:**
Same as test #3 - GPIO guard mismatch in mock environment:
- `set_relay()` returns `changed=False, state=False` with `guard={'ok': False, 'coerced': True}`
- The relay guard detects persistent HIGH when expecting LOW
- This is a mock GPIO setup issue, not actual relay logic issue

**Test File Location:**
The file is named `tmp_debug_test.py`, suggesting it may be a temporary debug test that should potentially be:
- Removed if no longer needed
- Fixed to work with mock GPIO
- Moved to a proper location with better naming

**Priority:** Low - This appears to be a temporary debug test. Consider removing if not essential.

**Recommendation:**
- Same as test #3: Fix GPIO mock state initialization
- Consider removing this test if it was only for debugging
- If keeping, move to proper test location and rename appropriately

---

## Common Patterns

### GPIO Mock Issues (Tests #3, #4)
Tests #3 and #4 both fail due to relay guard GPIO state verification mismatches in mock environments. The relay guard system expects LOW after setting a relay ON (active-low logic), but reads HIGH from the mock.

**Suggested Fix:**
- Review `conftest.py` for GPIO mock initialization
- Ensure `GPIOZERO_PIN_FACTORY=mock` is set early in test setup
- Verify mock GPIO pins return expected values after state changes
- Consider if relay_guard should have a test mode that skips verification

### Relay Persistence (Test #1)
Test #1 indicates `_save_state()` is not being called when expected, possibly related to the same guard issues preventing state changes.

**Suggested Fix:**
- Fix GPIO mock setup to allow state changes
- Verify monkeypatch is applied before relay initialization
- Check test isolation - ensure relay_guard is reset between tests

---

## Next Steps

1. **Immediate:** Mark tests as `@pytest.mark.xfail` with references to this document
2. **Short-term:** Fix GPIO mock initialization in conftest.py
3. **Review:** Determine if test #2 (sensor freshness) threshold change was intentional
4. **Clean-up:** Remove or properly integrate `tmp_debug_test.py`

---

## Test Environment Details

- **Python Version:** 3.12
- **Pytest Version:** 8.4.2
- **pytest-timeout:** 2.4.0
- **Test Duration:** 31.27s (slowest: `test_commissioning_sim.py::test_commissioning_flow` at 30.04s)
- **Platform:** Linux (GitHub Actions runner)

---

## Labels

- `test-failure`
- `needs-triage`
- `relay-guard`
- `gpio-mock`

---

**Generated:** 2025-11-16  
**PR Reference:** [#43](https://github.com/collinerasmus/RDWC-v4/pull/43)
