
import importlib
import tempfile
import os
from app import unified_mode as mod


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
    # Note: manual and maintenance now map to "hold" for simplified system
    for ctrl in ['ph', 'ec', 'chiller', 'circulation', 'lights']:
        # Test auto mode
        mod.set_controller_mode(ctrl, 'auto')
        assert mod.get_controller_mode(ctrl) == 'auto'
        
        # Test hold mode
        mod.set_controller_mode(ctrl, 'hold')
        assert mod.get_controller_mode(ctrl) == 'hold'
        
        # Test legacy modes map to hold
        mod.set_controller_mode(ctrl, 'manual')
        assert mod.get_controller_mode(ctrl) == 'hold'
        
        mod.set_controller_mode(ctrl, 'maintenance')
        assert mod.get_controller_mode(ctrl) == 'hold'

@with_temp_db
def test_get_all_modes():
    # Set modes and verify get_all_modes returns correct dict
    # Note: manual and maintenance now map to "hold"
    mod.set_controller_mode('ph', 'auto')
    mod.set_controller_mode('ec', 'manual')  # Maps to hold
    mod.set_controller_mode('chiller', 'maintenance')  # Maps to hold
    modes = mod.get_all_modes()
    assert modes['ph'] == 'auto'
    assert modes['ec'] == 'hold'
    assert modes['chiller'] == 'hold'

@with_temp_db
def test_mode_persistence():
    # Set mode, reload module, verify persistence
    # Note: manual now maps to hold
    mod.set_controller_mode('ph', 'manual')
    assert mod.get_controller_mode('ph') == 'hold'
    # Simulate reload
    mod2 = importlib.reload(mod)
    assert mod2.get_mode('ph') == 'hold'
