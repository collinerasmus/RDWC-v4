def test_debug_relay_on():
    import os
    os.environ['GPIOZERO_PIN_FACTORY'] = 'mock'
    from app.relays_core import set_relay, get_relay_status, get_estop_status
    assert get_estop_status() is False
    r = set_relay('main_pump', True, 'debug')
    print('set_relay result:', r)
    s = get_relay_status()
    print('status main_pump:', s.get('main_pump'))
    assert s.get('main_pump',{}).get('state') is True
