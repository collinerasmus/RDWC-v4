from fastapi import FastAPI
from .config import settings

def build_app(controller):
    app = FastAPI(title="RDWC", version="0.1.0")

    @app.get("/status")
    def status():
        data = controller.loop()  # one pass per request
        return {"env": settings.env, "data": data}

    @app.post("/actuate/{name}/{on}")
    def actuate(name: str, on: int):
        onb = (on == 1)
        controller.relays.set(name, onb)
        return {"ok": True, "pin": name, "state": onb}

    @app.get("/")
    def root():
        return {"ok": True, "endpoints": ["/status", "/actuate/{name}/{on}"]}

    return app