"""
Tests for EC Control v2 features:
- Unified dose_events logging
- Dry-run mode (default ON)
- Schedule-driven ratios
- Centralized guards
- Preview = worker logic parity
"""
import os
import tempfile
import sqlite3
import importlib
import json
from datetime import datetime, timezone


def with_temp_db(test_fn):
    """Decorator to run test with isolated temp database."""
    def wrapper():
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        try:
            # Force reload to avoid state leaking between tests
            import app.ec_control as mod
            importlib.reload(mod)
            original_db = getattr(mod, 'DB_PATH', None)
            mod.DB_PATH = mod.Path(tmp.name)
            
            # Also patch dosing module DB path
            dosing_mod = None
            try:
                import app.dosing as dosing_mod
                dosing_mod.DB_PATH = mod.Path(tmp.name)
            except ImportError:
                pass
            
            try:
                test_fn(mod)
            finally:
                mod.DB_PATH = original_db
                if dosing_mod is not None:
                    try:
                        dosing_mod.DB_PATH = original_db
                    except (NameError, AttributeError):
                        pass
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    return wrapper


@with_temp_db
def test_dry_run_default_off(mod):
    """Verify dry-run is disabled by default (pumps run water only)."""
    # Patch settings to return empty (use fallback default)
    mod._get_settings_dict = lambda: {}
    
    assert mod._is_dry_run_ec() == False


@with_temp_db  
def test_dry_run_can_be_enabled(mod):
    """Verify dry-run can be enabled via settings when nutrients are loaded."""
    mod._get_settings_dict = lambda: {'dosing.dry_run_ec': 'true'}
    
    assert mod._is_dry_run_ec() == True


@with_temp_db
def test_schedule_ratios_equal_split_no_start_date(mod):
    """When no grow_start_date, should return equal split."""
    mod._ensure_dose_events_table()
    
    # Ensure no start date in settings
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("DELETE FROM settings WHERE key = 'general.grow_start_date'")
        conn.commit()
    
    ratios, source = mod._get_schedule_ratios()
    
    assert source.startswith("equal_split")
    assert abs(ratios["grow"] - 1/3) < 0.01
    assert abs(ratios["micro"] - 1/3) < 0.01
    assert abs(ratios["bloom"] - 1/3) < 0.01


@with_temp_db
def test_schedule_ratios_from_schedule_table(mod):
    """When schedule exists, should return schedule ratios."""
    mod._ensure_dose_events_table()
    
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        # Create settings with start date (week 1)
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('general.grow_start_date', ?)", 
                    (datetime.now(timezone.utc).strftime("%Y-%m-%d"),))
        
        # Create nutrient_schedule with week 1 data
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nutrient_schedule (
                week INTEGER PRIMARY KEY,
                phase TEXT NOT NULL,
                grow_ml10 REAL DEFAULT 0,
                micro_ml10 REAL DEFAULT 0,
                bloom_ml10 REAL DEFAULT 0,
                ec_target REAL DEFAULT 1.0,
                ph_low REAL DEFAULT 5.8,
                ph_high REAL DEFAULT 6.2,
                temp_target REAL DEFAULT 20.0,
                lights TEXT DEFAULT '18/6',
                notes TEXT
            )
        """)
        # Week 1: 3:2:1 ratio = G=0.5, M=0.33, B=0.17
        conn.execute("INSERT INTO nutrient_schedule (week, phase, grow_ml10, micro_ml10, bloom_ml10) VALUES (1, 'seedling', 3.0, 2.0, 1.0)")
        conn.commit()
    
    ratios, source = mod._get_schedule_ratios()
    
    assert "schedule" in source
    assert abs(ratios["grow"] - 0.5) < 0.01
    assert abs(ratios["micro"] - 0.333) < 0.02
    assert abs(ratios["bloom"] - 0.167) < 0.02


@with_temp_db
def test_split_ml_by_ratio(mod):
    """Test ml splitting by ratio."""
    ratios = {"grow": 0.5, "micro": 0.3, "bloom": 0.2}
    
    result = mod._split_ml_by_ratio(100.0, ratios)
    
    assert result["grow"] == 50.0
    assert result["micro"] == 30.0
    assert result["bloom"] == 20.0


@with_temp_db
def test_dose_logs_to_dose_events(mod):
    """Verify dose endpoint logs to dose_events table."""
    mod.time.sleep = lambda s: None  # Skip sleeps
    mod._is_dry_run_ec = lambda: True  # Force dry-run
    
    # Stub settings and guards
    mod._get_settings_dict = lambda: {
        'ec.enabled': 'true',
        'dosing.grow_ml_per_sec': '20',
        'targets.ec_high': '2.0',
        'targets.ec_target': '1.0',
    }
    mod._check_guards = lambda p, s: (True, None, {})
    mod._check_ec_high_guard = lambda: (True, None)
    mod._check_interval_guard = lambda now: (True, None)
    mod._check_daily_cap = lambda now: (True, None)
    
    mod._ensure_dose_events_table()
    
    # Call dose endpoint
    body = {"pump": "grow", "seconds": 1.0, "reason": "test"}
    result = mod.dose_ec(body)
    
    assert result.get("ok") == True
    assert result.get("dry_run") == True
    
    # Check dose_events table
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT pump, actor, seconds FROM dose_events ORDER BY ts DESC LIMIT 1")
        row = cur.fetchone()
    
    assert row is not None
    assert row[0] == "grow"
    assert row[1] == "dry-run"
    assert row[2] == 1.0


@with_temp_db
def test_dose_blocked_logs_blocked_by(mod):
    """Verify blocked doses log blocked_by to dose_events."""
    mod.time.sleep = lambda s: None
    
    # Stub to block with estop
    mod._get_settings_dict = lambda: {
        'ec.enabled': 'true',
        'dosing.grow_ml_per_sec': '20',
    }
    mod._check_guards = lambda p, s: (False, "estop", {})
    mod._ensure_dose_events_table()
    
    body = {"pump": "grow", "seconds": 1.0, "reason": "test"}
    result = mod.dose_ec(body)
    
    # Should be blocked
    assert hasattr(result, 'status_code')
    assert result.status_code == 409
    
    # Check blocked_by in dose_events
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT blocked_by FROM dose_events ORDER BY ts DESC LIMIT 1")
        row = cur.fetchone()
    
    assert row is not None
    assert row[0] == "estop"


@with_temp_db
def test_preview_includes_ratios(mod):
    """Verify preview endpoint returns ratio information."""
    mod._get_settings_dict = lambda: {
        'targets.ec_low': '0.8',
        'targets.ec_high': '1.2',
        'targets.ec_target': '1.0',
        'dosing.ec_safety_factor': '0.6',
        'dosing.dry_run_ec': 'true',
    }
    mod._get_latest_ec = lambda: (0.5, int(datetime.now(timezone.utc).timestamp()))
    mod._check_guards = lambda p, s: (True, None, {})
    mod._check_ec_high_guard = lambda: (True, None)
    mod._check_interval_guard = lambda now: (True, None)
    mod._check_daily_cap = lambda now: (True, None)
    mod._get_schedule_ratios = lambda: ({"grow": 0.4, "micro": 0.3, "bloom": 0.3}, "schedule:week_4")
    
    result = mod.get_ec_control_preview()
    
    assert result.get("would_dose") == True
    assert result.get("ratio_source") == "schedule:week_4"
    assert "ratios" in result
    assert result["ratios"]["grow"] == 0.4
    assert "proposed_action" in result
    assert "mix" in result["proposed_action"]


@with_temp_db
def test_recent_doses_reads_from_dose_events(mod):
    """Verify /api/ec/dose/recent reads from dose_events."""
    mod._ensure_dose_events_table()
    
    # Insert test data into dose_events
    ts = int(datetime.now(timezone.utc).timestamp())
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        conn.execute("""
            INSERT INTO dose_events (ts, pump, seconds, reason, actor, ec_before, ec_after)
            VALUES (?, 'grow', 1.5, 'test', 'manual', 0.8, 0.9)
        """, (ts,))
        conn.commit()
    
    mod._get_settings_dict = lambda: {'dosing.grow_ml_per_sec': '20'}
    
    result = mod.ec_dose_recent(limit=10)
    
    assert "events" in result
    assert len(result["events"]) >= 1
    event = result["events"][0]
    assert event["pump"] == "grow"
    assert event["seconds"] == 1.5
    assert event["actor"] == "manual"


@with_temp_db  
def test_compute_volume_ml(mod):
    """Test volume computation from pump and seconds."""
    mod._get_settings_dict = lambda: {'dosing.grow_ml_per_sec': '25'}
    
    result = mod._compute_volume_ml("grow", 2.0)
    
    assert result == 50.0  # 25 ml/s * 2s = 50 ml


@with_temp_db
def test_today_total_ml_from_dose_events(mod):
    """Verify _today_total_ml reads from dose_events."""
    mod._ensure_dose_events_table()
    mod._get_settings_dict = lambda: {'dosing.grow_ml_per_sec': '20'}
    
    # Insert test data from today
    ts = int(datetime.now(timezone.utc).timestamp())
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        # 2 seconds of grow = 40ml
        conn.execute("""
            INSERT INTO dose_events (ts, pump, seconds, actor)
            VALUES (?, 'grow', 2.0, 'manual')
        """, (ts,))
        conn.commit()
    
    result = mod._today_total_ml(datetime.now(timezone.utc))
    
    assert result == 40.0


@with_temp_db
def test_last_ok_ts_from_dose_events(mod):
    """Verify _last_ok_ts reads from dose_events."""
    mod._ensure_dose_events_table()
    
    ts = int(datetime.now(timezone.utc).timestamp()) - 100
    with sqlite3.connect(str(mod.DB_PATH)) as conn:
        conn.execute("""
            INSERT INTO dose_events (ts, pump, seconds, actor)
            VALUES (?, 'micro', 1.0, 'auto')
        """, (ts,))
        conn.commit()
    
    result = mod._last_ok_ts()
    
    assert result is not None
    assert abs(result.timestamp() - ts) < 1


@with_temp_db
def test_ec_high_guard_blocks_when_above_threshold(mod):
    """Verify EC high guard blocks dosing when EC is high."""
    mod._get_settings_dict = lambda: {
        'targets.ec_target': '1.0',
        'targets.ec_tolerance': '0.2',
        'targets.ec_high': '1.2',
    }
    # EC at 1.3 is above target+tolerance (1.2)
    mod._get_latest_ec = lambda: (1.3, int(datetime.now(timezone.utc).timestamp()))
    
    ok, reason = mod._check_ec_high_guard()
    
    assert ok == False
    assert "ec_high_guard" in reason


@with_temp_db
def test_ec_high_guard_allows_when_below_threshold(mod):
    """Verify EC high guard allows dosing when EC is below threshold."""
    mod._get_settings_dict = lambda: {
        'targets.ec_target': '1.0',
        'targets.ec_tolerance': '0.2',
        'targets.ec_high': '1.2',
    }
    # EC at 0.8 is below threshold
    mod._get_latest_ec = lambda: (0.8, int(datetime.now(timezone.utc).timestamp()))
    
    ok, reason = mod._check_ec_high_guard()
    
    assert ok == True
    assert reason is None
