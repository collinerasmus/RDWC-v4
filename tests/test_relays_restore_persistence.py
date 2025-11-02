import importlib

def test_boot_safe_off_does_not_persist(monkeypatch):
    rc = importlib.import_module('app.relays_core')

    calls = []
    orig_save = rc._save_state
    def fake_save():
        calls.append(1)
    monkeypatch.setattr(rc, '_save_state', fake_save, raising=True)

    # Ensure a clean device map for this test
    rc._devices.clear()
    rc._last_state.clear()
    rc._last_change_ts.clear()
    rc._antiflap_until.clear()

    # Normal change should persist once
    rc.set_relay('main_pump', True, rc.REASON_OVERRIDE, force=True)
    assert len(calls) == 1

    # Boot safe-off should NOT persist
    calls.clear()
    rc.initialize_all_safe_off()
    assert len(calls) == 0

    # Restore original
    monkeypatch.setattr(rc, '_save_state', orig_save, raising=True)
