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

    # Stub guards to allow dosing (v2 signature returns 3 values)
    mod._check_guards = lambda p, s: (True, None, {})
    mod._check_ec_high_guard = lambda: (True, None)
    mod._check_interval_guard = lambda now: (True, None)
    mod._check_daily_cap = lambda now: (True, None)
    mod._is_dry_run_ec = lambda: False  # Disable dry-run for this test
    mod._get_dose_lock = lambda: type('MockLock', (), {'acquire': lambda self, **k: True, 'release': lambda self: None, 'locked': lambda self: False})()

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
    # V2: Now reads from dose_events table
    mod._ensure_dose_events_table()
    mod._get_settings_dict = lambda: {'dosing.grow_ml_per_sec': '10'}  # 10 ml/s for easy math
    
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    yday = now - timedelta(days=1)
    yday_ts = int(yday.timestamp())
    
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        cur = conn.cursor()
        # Insert into dose_events: 1 second of 'grow' at 10 ml/s = 10ml
        cur.execute("INSERT INTO dose_events(ts, pump, seconds, actor) VALUES(?,?,?,?)",
                    (now_ts, 'grow', 1.0, 'manual'))
        # Insert yesterday: 2 seconds = 20ml
        cur.execute("INSERT INTO dose_events(ts, pump, seconds, actor) VALUES(?,?,?,?)",
                    (yday_ts, 'grow', 2.0, 'manual'))
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
