from fastapi import FastAPI
from .config import settings

def build_app(controller, sampler):
    app = FastAPI(title="RDWC", version="0.2.0")

    @app.get("/status")
    def status():
        data = controller.loop_once()
        return {"env": settings.env, "sample_interval_sec": settings.sample_interval_sec, "data": data}

    @app.post("/actuate/{name}/{on}")
    def actuate(name: str, on: int):
        onb = (on == 1)
        controller.relays.set(name, onb)
        return {"ok": True, "pin": name, "state": onb}

    @app.get("/")
    def root():
        return {"ok": True, "endpoints": ["/status", "/actuate/{name}/{on}"]}

    return app