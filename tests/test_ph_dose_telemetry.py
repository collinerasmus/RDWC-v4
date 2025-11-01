import os
import tempfile
import sqlite3
from datetime import datetime, timedelta, timezone

import importlib


def with_temp_db(test_fn):
    def wrapper():
        # Create temp DB and patch module DB_PATH
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        try:
            mod = importlib.import_module('app.ph_control')
            # Patch DB_PATH
            original = mod.DB_PATH
            mod.DB_PATH = mod.Path(tmp.name)
            try:
                test_fn(mod)
            finally:
                mod.DB_PATH = original
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
    return wrapper


@with_temp_db
def test_ml_conversion_from_ms(mod):
    # Monkeypatch settings getter to a fixed rate 4.0 ml/s
    def fake_get_float(key, default):
        if key == 'dosing.ph_up_ml_per_sec':
            return 4.0
        return default
    mod._settings_get_float = fake_get_float  # type: ignore
    assert mod._volume_ml_from_ms(500) == 2.0
    assert mod._volume_ml_from_ms(0) == 0.0


@with_temp_db
def test_dose_summary_days(mod):
    mod._ensure_tables()
    # Insert two doses on today and yesterday
    now = datetime.now(timezone.utc)
    yday = now - timedelta(days=1)
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO ph_dose_log(ts_utc, action, volume_ml, duration_ms, pre_ph, post_ph, result, reason) VALUES(?,?,?,?,?,?,?,?)",
                    (now.isoformat(), 'dose', 1.5, 500, None, None, 'ok', 'manual'))
        cur.execute("INSERT INTO ph_dose_log(ts_utc, action, volume_ml, duration_ms, pre_ph, post_ph, result, reason) VALUES(?,?,?,?,?,?,?,?)",
                    (yday.isoformat(), 'dose', 2.0, 700, None, None, 'ok', 'manual'))
        conn.commit()
    rows = mod._dose_daily(2)
    # Should have two days, ascending
    assert len(rows) == 2
    assert rows[0]['day'] <= rows[1]['day']
    totals = sum(r['total_ml'] for r in rows)
    assert totals == 3.5
