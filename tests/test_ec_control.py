import os
import tempfile
import sqlite3
import importlib
from datetime import datetime, timedelta, timezone


def with_temp_db(test_fn):
    def wrapper():
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        try:
            mod = importlib.import_module('app.ec_control')
            # Patch DB_PATH
            original_db = getattr(mod, 'DB_PATH', None)
            mod.DB_PATH = mod.Path(tmp.name)  # type: ignore[attr-defined]
            try:
                test_fn(mod)
            finally:
                mod.DB_PATH = original_db  # type: ignore[attr-defined]
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
    return wrapper


@with_temp_db
def test_status_shape(mod):
    # Monkeypatch settings to known values
    mod._get_settings_dict = lambda: {
        'targets.ec_low': '0.8',
        'targets.ec_high': '1.2',
        'ec.auto_enabled': 'false',
        'dosing.ec_min_interval_s': '60',
        'dosing.ec_max_ml_day': '0',
    }
    # No readings seeded -> sensor_stale likely true
    resp = mod.get_ec_status()
    assert 'ec_ms_cm' in resp
    assert 'targets' in resp and 'low' in resp['targets'] and 'high' in resp['targets']
    assert 'auto' in resp and 'enabled' in resp['auto']
    assert 'guards' in resp and isinstance(resp['guards'], dict)
    assert 'today_ml' in resp
    assert 'recent' in resp and isinstance(resp['recent'], list)


@with_temp_db
def test_manual_custom_mix_split(mod):
    # Speed test by skipping actual sleeps
    mod.time.sleep = lambda s: None

    # Stub guards to allow dosing
    mod._check_guards = lambda: (True, None)
    mod._check_interval_guard = lambda now: (True, None)
    mod._check_daily_cap = lambda now: (True, None)

    # Stub actuator to capture values
    captured = {}
    def fake_actuate(g, m, b):
        captured['grow'] = g
        captured['micro'] = m
        captured['bloom'] = b
        return ('ok', 0)
    mod._actuate_mix = fake_actuate

    body = {
        'ml': 90,
        'mix_ratio': 'custom',
        'custom': {'grow': 3, 'micro': 2, 'bloom': 1},
        'reason': 'test'
    }
    out = mod.dose_ec(body)
    assert out['ok'] is True
    # 3:2:1 -> 6 parts; 90ml => G=45, M=30, B=15
    assert abs(captured['grow'] - 45) < 1e-6
    assert abs(captured['micro'] - 30) < 1e-6
    assert abs(captured['bloom'] - 15) < 1e-6


@with_temp_db
def test_dose_reject_invalid_ml(mod):
    resp = mod.dose_ec({'ml': 0})
    # JSONResponse on error
    assert hasattr(resp, 'status_code')
    assert resp.status_code == 400


@with_temp_db
def test_daily_summary_totals(mod):
    mod._ensure_tables()
    now = datetime.now(timezone.utc)
    yday = now - timedelta(days=1)
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO ec_dose_log(ts_utc, action, volume_ml, duration_ms, pre_ec, post_ec, result, reason) VALUES(?,?,?,?,?,?,?,?)",
                    (now.isoformat(), 'dose', 10.0, 1000, None, None, 'ok', 'manual'))
        cur.execute("INSERT INTO ec_dose_log(ts_utc, action, volume_ml, duration_ms, pre_ec, post_ec, result, reason) VALUES(?,?,?,?,?,?,?,?)",
                    (yday.isoformat(), 'dose', 20.0, 1000, None, None, 'ok', 'manual'))
        conn.commit()
    rows = mod._dose_daily_range(days=2)
    assert len(rows) >= 2
    totals = sum(r['total_ml'] for r in rows[-2:])
    assert abs(totals - 30.0) < 1e-6


@with_temp_db
def test_reset_learner(mod):
    mod._learned_ml_per_mScm = 123.0
    out = mod.reset_ec_learner()
    assert out['ok'] is True
    assert mod._learned_ml_per_mScm is None
