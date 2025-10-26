from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from .config import settings

def build_app(controller, sampler):
    app = FastAPI(title="RDWC", version="0.3.0")

    @app.get("/status")
    def status():
        data = controller.loop_once()
        return {"env": settings.env, "sample_interval_sec": settings.sample_interval_sec, "data": data}

    @app.post("/actuate/{name}/{on}")
    def actuate(name: str, on: int):
        onb = (on == 1)
        controller.relays.set(name, onb)
        return {"ok": True, "pin": name, "state": onb}

    @app.get("/", response_class=HTMLResponse)
    def ui(request: Request):
        data = sampler.latest()
        html = f"""
        <html><head>
        <meta http-equiv="refresh" content="{settings.ui_refresh_sec}">
        <title>RDWC Control Panel</title>
        <style>
          body {{ background:#0b0b0b;color:#eee;font-family:sans-serif;text-align:center; }}
          h1 {{ color:#9dfd70; }}
          .card {{ display:inline-block;background:#111;border-radius:12px;padding:1em;margin:0.5em; }}
          button {{ background:#333;color:#eee;border:none;border-radius:6px;padding:0.6em 1em;margin:0.3em;cursor:pointer; }}
          button:hover {{ background:#555; }}
        </style></head><body>
        <h1>🌿 RDWC Control Panel</h1>
        <div class="card"><b>Temperature:</b> {data.get('temperature_c')}°C<br>
        <b>EC:</b> {data.get('ec')} µS/cm<br>
        <b>pH:</b> {data.get('pH')}</div><br><br>
        <h2>Relay Controls</h2>
        {"".join([f"<div class='card'>{n}<br><button onclick=\"fetch('/actuate/{n}/1',{{method:'POST'}})\">ON</button><button onclick=\"fetch('/actuate/{n}/0',{{method:'POST'}})\">OFF</button></div>" for n in controller.relays.pin_map.keys()])}
        <br><br><small>Auto-refresh {settings.ui_refresh_sec}s • Lights auto {settings.lights_on_hour}:00–{settings.lights_off_hour}:00</small>
        </body></html>
        """
        return HTMLResponse(content=html)

    return app