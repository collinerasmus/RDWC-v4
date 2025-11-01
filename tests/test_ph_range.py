"""Tests for pH dose range endpoints and grow preset logic"""
import pytest
from datetime import datetime, timezone, timedelta


def test_range_validation_start_equals_end():
    """start=end should return 422"""
    from app.ph_control import _dose_events_range
    
    now_iso = datetime.now(timezone.utc).isoformat()
    with pytest.raises(ValueError, match="start must be before end"):
        _dose_events_range(start=now_iso, end=now_iso)


def test_range_validation_start_after_end():
    """start>end should return 422"""
    from app.ph_control import _dose_events_range
    
    now = datetime.now(timezone.utc)
    later = now + timedelta(hours=1)
    with pytest.raises(ValueError, match="start must be before end"):
        _dose_events_range(start=later.isoformat(), end=now.isoformat())


def test_grow_preset_with_date():
    """Grow preset should compute start from settings date"""
    # This would need proper settings mock; placeholder test
    pass


def test_summary_totals_match_log():
    """Daily summary totals should equal sum of individual dose volumes"""
    # This would need a temp DB with seeded data; placeholder test
    pass


def test_csv_range_parity():
    """CSV rows should match JSON range for same parameters"""
    # This would need a temp DB with seeded data; placeholder test
    pass
