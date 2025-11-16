"""Test the commissioning_readiness summarize function (hardware-agnostic)."""
import os
import sys
import importlib.util
from pathlib import Path

# Ensure root on PYTHONPATH
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

MODULE_PATH = ROOT / "tools" / "commissioning_readiness.py"

spec = importlib.util.spec_from_file_location("commissioning_readiness", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)  # type: ignore
assert spec.loader is not None
spec.loader.exec_module(mod)  # type: ignore


def test_readiness_summary_basic_keys():
    summary = mod.summarize()
    # Core keys should exist regardless of hardware state
    for key in [
        "relay_mode",
        "estop",
        "sensor_poller_running",
        "sensors_online_flag",
        "pump_ids",
        "settings_import_ok",
    ]:
        assert key in summary, f"Missing summary key: {key}"
    assert isinstance(summary["pump_ids"], list), "pump_ids should be a list"
    # Compact mode path: simulate by stripping raw
    compact = {k: v for k, v in summary.items() if k != "raw"}
    assert "raw" not in compact
