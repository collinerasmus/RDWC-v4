import uvicorn
from .config import settings
from .hardware import Relays
from .sensors import Sensors, Sampler
from .control import Controller
from .api import build_app
from .history import init_db
from .dosing import Doser

def create_components():
    relays = Relays(settings.relay, active_high=False)
    sensors = Sensors()
    sampler = Sampler(sensors, interval_sec=settings.sample_interval_sec)
    sampler.start()
    controller = Controller(sampler, relays)
    doser = Doser(relays, sampler, is_mock=settings.force_mock_sensors)
    return controller, sampler, doser

def run():
    init_db()
    controller, sampler, doser = create_components()
    app = build_app(controller, sampler, doser)
    uvicorn.run(app, host=settings.host, port=settings.port)

if __name__ == "__main__":
    run()