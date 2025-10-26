import uvicorn
from .config import settings
from .hardware import Relays
from .sensors import Sensors, Sampler
from .control import Controller
from .api import build_app

def create_components():
    relays = Relays(settings.relay, active_high=False)
    sensors = Sensors()
    sampler = Sampler(sensors, interval_sec=settings.sample_interval_sec)
    sampler.start()
    controller = Controller(sampler, relays)
    return controller, sampler

def run():
    controller, sampler = create_components()
    app = build_app(controller, sampler)
    uvicorn.run(app, host=settings.host, port=settings.port)

if __name__ == "__main__":
    run()