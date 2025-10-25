import uvicorn
from .config import settings
from .hardware import Relays
from .sensors import Sensors
from .control import Controller
from .api import build_app

def create_controller():
    relays = Relays(settings.relay, active_high=False)
    sensors = Sensors(settings.i2c_bus, settings.ph_addr, settings.ec_addr, settings.rtd_addr)
    return Controller(sensors, relays)

def run():
    controller = create_controller()
    app = build_app(controller)
    uvicorn.run(app, host=settings.host, port=settings.port)

if __name__ == "__main__":
    run()