
import importlib
import tempfile
import os
from app import controller_modes as mod


def with_temp_db(test_fn):
    def wrapper():
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        os.environ["RDWC_CONTROLLER_MODES_DB"] = tmp.name
        try:
            test_fn()
        finally:
            del os.environ["RDWC_CONTROLLER_MODES_DB"]
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
    return wrapper

@with_temp_db
def test_set_and_get_mode():
    # Set mode for each controller and verify get_mode returns it
    for ctrl in ['ph', 'ec', 'chiller', 'circulation', 'lights']:
        for mode in ['auto', 'manual', 'maintenance']:
            mod.set_mode(ctrl, mode)
            assert mod.get_mode(ctrl) == mode

@with_temp_db
def test_get_all_modes():
    # Set modes and verify get_all_modes returns correct dict
    mod.set_mode('ph', 'auto')
    mod.set_mode('ec', 'manual')
    mod.set_mode('chiller', 'maintenance')
    modes = mod.get_all_modes()
    assert modes['ph'] == 'auto'
    assert modes['ec'] == 'manual'
    assert modes['chiller'] == 'maintenance'

@with_temp_db
def test_mode_persistence():
    # Set mode, reload module, verify persistence
    mod.set_mode('ph', 'manual')
    assert mod.get_mode('ph') == 'manual'
    # Simulate reload
    mod2 = importlib.reload(mod)
    assert mod2.get_mode('ph') == 'manual'
