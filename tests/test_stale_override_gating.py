import os
import tempfile
import importlib
import json
from fastapi.responses import JSONResponse


def _decode_json_response(resp):
    if isinstance(resp, JSONResponse):
        try:
            raw = resp.body
            if isinstance(raw, (bytes, bytearray)):
                return json.loads(raw.decode('utf-8'))
            # memoryview or other buffer-protocol
            return json.loads(bytes(raw).decode('utf-8'))
        except Exception:
            return {}
    return resp


def test_blocks_stale_even_with_maintenance_override():
    # Setup temp DB for ph_control
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    mod = importlib.import_module('app.ph_control')
    original_db = mod.DB_PATH
    mod.DB_PATH = mod.Path(tmp.name)  # type: ignore[attr-defined]
    # Force sensor_stale by ensuring no readings table (default path)
    # Patch settings: maintenance_override=true, allow_stale_on_override=false
    import app.settings as settings
    orig = settings.get_setting_key
    def fake_get_setting_key(key, default=None):
        overrides = {
            'safety.maintenance_override': 'true',
            'safety.allow_stale_on_override': 'false',
            'safety.allow_force': 'false',
        }
        return overrides.get(key, default)
    settings.get_setting_key = fake_get_setting_key  # type: ignore
    try:
        resp = mod.ph_dose({'seconds': 0.2, 'reason': 'unit-stale-block'})
        data = _decode_json_response(resp)
        assert data.get('ok') is False and data.get('blocked') is True
        reasons = data.get('reasons') or []
        assert 'sensor_stale' in reasons
    finally:
        settings.get_setting_key = orig  # type: ignore
        mod.DB_PATH = original_db  # type: ignore[attr-defined]
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def test_allows_when_both_flags_true_and_gpio_finally(capsys, monkeypatch):
    # Setup temp DB for ph_control
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    mod = importlib.import_module('app.ph_control')
    original_db = mod.DB_PATH
    mod.DB_PATH = mod.Path(tmp.name)  # type: ignore[attr-defined]
    
    # Mock relay_guard.safe_set to bypass GPIO mismatch issues in test environment
    guard_module = importlib.import_module('app.relay_guard')
    def fake_guard_set(name, desired_on, reason="", actor="system"):
        return {"changed": True, "ok": True, "coerced": False, "mismatch_retries": 0, "shadow": desired_on}
    monkeypatch.setattr(guard_module, 'safe_set', fake_guard_set)
    
    # Patch settings: maintenance_override=true AND allow_stale_on_override=true
    import app.settings as settings
    orig = settings.get_setting_key
    def fake_get_setting_key(key, default=None):
        overrides = {
            'safety.maintenance_override': 'true',
            'safety.allow_stale_on_override': 'true',
            'safety.allow_force': 'false',
            'dosing.ph_up_max_ms': '5000',
            'dosing.ph_up_ml_per_sec': '25',
        }
        return overrides.get(key, default)
    settings.get_setting_key = fake_get_setting_key  # type: ignore
    try:
        resp = mod.ph_dose({'seconds': 0.2, 'reason': 'unit-override-ok'})
        data = _decode_json_response(resp)
        assert data.get('ok') is True
        # Ensure GPIO LOW then HIGH printed (finally executed)
        out = capsys.readouterr().out
        assert 'GPIO LOW' in out and 'GPIO HIGH' in out
    finally:
        settings.get_setting_key = orig  # type: ignore
        mod.DB_PATH = original_db  # type: ignore[attr-defined]
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
