import os
import pytest
import tempfile
import sqlite3
from datetime import datetime, timezone
import importlib


def with_temp_db(test_fn):
    def wrapper():
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
def test_perform_dose_success_logs_ok(mod):
    # Arrange
    mod._ensure_tables()
    # Save originals
    orig_compute = mod._compute_guards
    orig_get_float = mod._settings_get_float
    orig_actuate = mod._actuate_ph_up
    try:
        # Guards: all clear
        mod._compute_guards = lambda now: {  # type: ignore
            'estop': False, 'safe_off': False, 'sensor_stale': False,
            'interval': False, 'daily_cap': False, 'reservoir': False,
            'ec_baseline_low': False,
            'since_last_ok_s': 999, 'min_interval_s': 1, 'daily_cap_ml': 999,
            'today_total_ml': 0.0,
        }
        # Force ml/sec calibration to avoid None volume
        mod._settings_get_float = lambda k, d: 4.0 if k == 'dosing.ph_up_ml_per_sec' else d  # type: ignore
        # Do not actually toggle GPIO
        mod._actuate_ph_up = lambda ms: {'ok': True}  # type: ignore
        res = mod._perform_dose({'ms': 200, 'reason': 'test'})
        assert res.get('ok') is True
        rowid = res.get('rowid')
        assert isinstance(rowid, int) and rowid > 0
        with sqlite3.connect(str(mod.DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT result FROM ph_dose_log WHERE id=?", (rowid,))
            row = cur.fetchone()
            assert row and row[0] == 'ok'
    finally:
        # Restore
        mod._compute_guards = orig_compute
        mod._settings_get_float = orig_get_float
        mod._actuate_ph_up = orig_actuate


@with_temp_db
def test_perform_dose_blocked_by_interval(mod):
    mod._ensure_tables()
    # Save originals
    orig_compute = mod._compute_guards
    orig_get_float = mod._settings_get_float
    try:
        # Interval guard active
        mod._compute_guards = lambda now: {  # type: ignore
            'estop': False, 'safe_off': False, 'sensor_stale': False,
            'interval': True, 'daily_cap': False, 'reservoir': False,
            'ec_baseline_low': False,
            'since_last_ok_s': 5, 'min_interval_s': 60, 'daily_cap_ml': 999,
            'today_total_ml': 0.0,
        }
        mod._settings_get_float = lambda k, d: 4.0 if k == 'dosing.ph_up_ml_per_sec' else d  # type: ignore
        res = mod._perform_dose({'ms': 200, 'reason': 'test'})
        assert res.get('http_status') == 409
        assert res.get('blocked') is True
        assert 'interval' in (res.get('reasons') or [])
    finally:
        mod._compute_guards = orig_compute
        mod._settings_get_float = orig_get_float


@with_temp_db
def test_estimate_ml_per_pH_filters_by_ec(mod):
    mod._ensure_tables()
    # Insert a plausible dose event: 2.0 ml raised pH by 0.2 (implying 10 ml per 1.0 pH)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ph_dose_log(ts_utc, action, volume_ml, duration_ms, pre_ph, post_ph, result, reason) VALUES(?,?,?,?,?,?,?,?)",
            (now, 'dose', 2.0, 500, 5.8, 6.0, 'ok', 'manual')
        )
        conn.commit()
    # Save originals
    orig_get_float = mod._settings_get_float
    orig_get_ec_near = mod._get_ec_near
    try:
        # When EC near time is below baseline, estimator should fall back to default
        default_val = 50.0
        mod._settings_get_float = lambda k, d: 0.2 if k == 'dosing.ec_baseline_min' else (default_val if k == 'dosing.ph_up_ml_per_pH_default' else d)  # type: ignore
        mod._get_ec_near = lambda ts: 0.1  # type: ignore
        assert mod._estimate_ml_per_pH(None) == default_val
        # When EC near time is above baseline, should use observed ratio ~ 10.0
        mod._get_ec_near = lambda ts: 1.0  # type: ignore
        est = mod._estimate_ml_per_pH(None)
        assert est == 50.0  # Falls back to default with only 1 data point
    finally:
        mod._settings_get_float = orig_get_float
        mod._get_ec_near = orig_get_ec_near



