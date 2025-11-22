import types
from app.scheduler import Scheduler
from app.hardware import RelayBank


def test_is_within_window_cross_midnight():
    rb = RelayBank()
    s = Scheduler(rb)
    # 18:00 -> 06:00 spans midnight
    on_min = 18*60
    off_min = 6*60
    # Before window same day
    assert s.is_within_window(17*60, on_min, off_min) is False
    # Inside before midnight
    assert s.is_within_window(23*60, on_min, off_min) is True
    # Inside after midnight
    assert s.is_within_window(0*60 + 30, on_min, off_min) is True
    # After off edge in morning
    assert s.is_within_window(7*60, on_min, off_min) is False
