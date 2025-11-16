import importlib

def test_boot_safe_off_does_not_persist(monkeypatch):
    """Verify that boot_safe_off reason skips persistence via _SKIP_PERSIST_REASONS."""
    rc = importlib.import_module('app.relays_core')

    # Verify skip-persist list includes boot_safe_off
    assert "boot_safe_off" in rc._SKIP_PERSIST_REASONS, "boot_safe_off must be in _SKIP_PERSIST_REASONS"
    
    # Mock _save_state to count calls
    calls = []
    def fake_save():
        calls.append(1)
    monkeypatch.setattr(rc, '_save_state', fake_save, raising=True)

    # Mock relay_guard.safe_set to always return a state change (bypass GPIO mismatch complexity)
    def fake_guard_set(name, desired_on, reason="", actor="system"):
        # Simulate successful state change
        return {"changed": True, "ok": True, "coerced": False, "mismatch_retries": 0, "shadow": desired_on}
    
    guard_module = importlib.import_module('app.relay_guard')
    monkeypatch.setattr(guard_module, 'safe_set', fake_guard_set, raising=True)

    # Clear state
    rc._devices.clear()
    rc._last_state.clear()
    rc._last_change_ts.clear()
    rc._antiflap_until.clear()

    # Test 1: Normal reason should persist
    calls.clear()
    rc.set_relay('main_pump', True, "apply_settings", force=True)
    assert len(calls) == 1, f"Expected 1 _save_state call for normal reason, got {len(calls)}"

    # Test 2: boot_safe_off should NOT persist
    calls.clear()
    rc.set_relay('main_pump', False, "boot_safe_off", force=True)
    assert len(calls) == 0, f"Expected 0 _save_state calls for boot_safe_off reason, got {len(calls)}"
