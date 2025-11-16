"""Test flags of commissioning_readiness script using subprocess exit codes."""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "tools" / "commissioning_readiness.py"
PY = sys.executable


def run_script(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run([PY, str(SCRIPT), *args], capture_output=True, text=True)
    return result


def test_require_sensors_flag_fails_without_hardware():
    r = run_script("--compact", "--require-sensors")
    # Expect sensors not online -> exit code 2
    assert r.returncode == 2, f"Expected exit 2 for sensors requirement, got {r.returncode}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"


def test_compact_no_requirements_succeeds():
    r = run_script("--compact")
    assert r.returncode == 0, f"Expected success exit code 0, got {r.returncode}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"