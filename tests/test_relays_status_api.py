def test_relays_status_shape():
    # Inject stubs for Linux-only deps to allow import on Windows CI/dev
    import sys
    import types
    if 'fcntl' not in sys.modules:
        sys.modules['fcntl'] = types.ModuleType('fcntl')
    if 'smbus2' not in sys.modules:
        sm = types.ModuleType('smbus2')
        setattr(sm, 'SMBus', object)
        setattr(sm, 'i2c_msg', object)
        setattr(sm, 'I2cFunc', object)
        sys.modules['smbus2'] = sm
    from app.main import api_relays_status
    data = api_relays_status()
    assert isinstance(data, dict)
    assert data.get('mode') in ('manual', 'auto', 'maintenance')
    assert isinstance(data.get('estop'), bool)
    relays = data.get('relays')
    assert isinstance(relays, dict)
    # Ensure known keys are present
    expected_subset = {
        'dosing_ph_up', 'dosing_grow', 'dosing_micro', 'dosing_bloom',
        'main_pump', 'chiller_pump', 'chiller_power', 'lights'
    }
    assert expected_subset.issubset(set(relays.keys()))
    # Check one relay entry shape
    r = relays['dosing_ph_up']
    assert 'pin_bcm' in r and 'active_low' in r and 'is_on' in r and 'label' in r
    assert isinstance(r['pin_bcm'], int)
    assert r['active_low'] is True
