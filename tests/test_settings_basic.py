import os
import tempfile
from pathlib import Path

from app import settings


def temp_db_path():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    return Path(tmp.name)


def test_upsert_and_get_all_settings_isolated():
    original = settings.DB_PATH
    original_seeded = settings._defaults_seeded
    tmp_path = temp_db_path()
    settings.DB_PATH = tmp_path
    # Reset the seeded flag to ensure table initialization for temporary DB
    settings._defaults_seeded = False
    try:
        # Initialize the table before using it
        settings._ensure_table_seed_defaults()
        
        changed = settings.upsert_settings({
            'general.grow_name': 'TestGrow',
            'targets.ph_low': '5.7'
        })
        assert changed['general.grow_name'] == 'TestGrow'
        assert changed['targets.ph_low'] == '5.7'
        all_flat = settings.get_all_settings()
        assert all_flat['general.grow_name'] == 'TestGrow'
        assert all_flat['targets.ph_low'] == '5.7'
        grouped = settings.get_settings_grouped()
        assert grouped['general']['grow_name'] == 'TestGrow'
        assert grouped['targets']['ph_low'] == '5.7'
    finally:
        settings.DB_PATH = original
        settings._defaults_seeded = original_seeded
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def test_validate_partial_bounds():
    ok, err = settings.validate_partial({'targets.ph_low': 3.0})
    assert ok is False and err and err.get('field') == 'targets.ph_low'
    ok, err = settings.validate_partial({'targets.ph_low': 5.5, 'targets.ph_high': 5.4})
    assert ok is False and err and err.get('field') == 'targets.ph_low'
    ok, err = settings.validate_partial({'targets.ph_low': 5.5, 'targets.ph_high': 6.2})
    assert ok is True and err is None


def test_validate_partial_success():
    ok, err = settings.validate_partial({'general.reservoir_liters': 100})
    assert ok is True


def test_import_all_rejects_invalid():
    resp = settings.import_all({'targets.ph_low': 3.0})
    assert resp['field'] == 'targets.ph_low'


def test_import_all_success():
    original = settings.DB_PATH
    original_seeded = settings._defaults_seeded
    tmp_path = temp_db_path()
    settings.DB_PATH = tmp_path
    # Reset the seeded flag to ensure table initialization for temporary DB
    settings._defaults_seeded = False
    try:
        # Initialize the table before using it
        settings._ensure_table_seed_defaults()
        
        resp = settings.import_all({'targets.ph_low': 5.8, 'targets.ph_high': 6.2})
        assert resp['ok'] is True
        all_flat = settings.get_all_settings()
        assert all_flat['targets.ph_low'] == '5.8'
        assert all_flat['targets.ph_high'] == '6.2'
    finally:
        settings.DB_PATH = original
        settings._defaults_seeded = original_seeded
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def test_validate_partial_grow_start_time_format():
    ok, err = settings.validate_partial({'general.lights_on_time': '25:00'})
    assert ok is False and err and err.get('field') == 'general.lights_on_time'

    ok, err = settings.validate_partial({'general.lights_on_time': '15:00'})
    assert ok is True and err is None


def test_upsert_settings_empty_grow_start_time_defaults_to_1500():
    original = settings.DB_PATH
    original_seeded = settings._defaults_seeded
    tmp_path = temp_db_path()
    settings.DB_PATH = tmp_path
    settings._defaults_seeded = False
    try:
        settings._ensure_table_seed_defaults()

        changed = settings.upsert_settings({'general.lights_on_time': ''})
        assert changed['general.lights_on_time'] == '15:00'
        assert changed['lights_on_time'] == '15:00'

        all_flat = settings.get_all_settings()
        assert all_flat['general.lights_on_time'] == '15:00'
        assert all_flat['lights_on_time'] == '15:00'
    finally:
        settings.DB_PATH = original
        settings._defaults_seeded = original_seeded
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def test_default_ec_target_matches_seedling_band():
    ec_low = float(settings.DEFAULTS['targets.ec_low'])
    ec_high = float(settings.DEFAULTS['targets.ec_high'])
    ec_target = float(settings.DEFAULTS['targets.ec_target'])

    assert ec_low < ec_high
    assert ec_low <= ec_target <= ec_high
