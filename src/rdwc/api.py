from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from .config import settings
from .nutrients import get_week_schedule
from .history import read_recent

def build_app(controller, sampler, doser):
    app = FastAPI(title="RDWC", version="0.4.0")

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
        plan_example = doser.plan(week=1)  # show something
        
        # Generate relay control buttons
        relay_buttons = []
        for n in controller.relays.pin_map.keys():
            btn_html = f"<div class='card'>{n}<br><button onclick=\"fetch('/actuate/{n}/1',{{method:'POST'}})\">ON</button><button onclick=\"fetch('/actuate/{n}/0',{{method:'POST'}})\">OFF</button></div>"
            relay_buttons.append(btn_html)
        relay_controls = "".join(relay_buttons)
        
        html = f"""
        <html><head>
        <meta http-equiv="refresh" content="{settings.ui_refresh_sec}">
        <title>RDWC Control Panel</title>
        <style>
          body {{ background:#0b0b0b;color:#eee;font-family:sans-serif;text-align:center; }}
          h1 {{ color:#9dfd70; }}
          .card {{ display:inline-block;background:#111;border-radius:12px;padding:1em;margin:0.5em; }}
          button {{ background:#333;color:#eee;border:none;border-radius:6px;padding:0.6em 1em;margin:0.3em;cursor:pointer; }}
          input,select {{ background:#111;color:#eee;border:1px solid #333;border-radius:6px;padding:0.4em 0.6em; }}
        </style></head><body>
        <h1>🌿 RDWC Control Panel</h1>
        <div class="card"><b>Temperature:</b> {data.get('temperature_c')}°C<br>
        <b>EC:</b> {data.get('ec')} µS/cm<br>
        <b>pH:</b> {data.get('pH')}</div><br><br>

        <h2>Relay Controls</h2>
        {relay_controls}

        <h2>Nutrient Planner</h2>
        <div class="card" style="min-width:320px;">
          <form id="planform" onsubmit="doPlan();return false;">
            Week:
            <input type="number" id="week" min="1" max="52" value="1">
            Volume (L):
            <input type="number" id="vol" min="1" step="1" value="{settings.total_volume_l}">
            <button type="submit">Plan</button>
            <button type="button" onclick="doExecute(false)">Execute</button>
            <button type="button" onclick="doExecute(true)">Dry-Run</button>
          </form>
          <pre id="planbox" style="text-align:left;white-space:pre-wrap;background:#0f0f0f;padding:0.6em;border-radius:8px;"></pre>
          <small>Calibrations (ml/s): Grow {settings.ml_per_sec['grow']}, Micro {settings.ml_per_sec['micro']}, Bloom {settings.ml_per_sec['bloom']}.<br>
          Safety: max {settings.dose_max_sec_per_run}s per run, {settings.dose_cooldown_sec}s cooldown.</small>
        </div>

        <h2>Recent Readings</h2>
        <iframe src="/history" style="width:90%;height:220px;background:#111;color:#eee;border:none;"></iframe>

        <script>
          async function doPlan() {{
            const w = document.getElementById('week').value;
            const v = document.getElementById('vol').value;
            const r = await fetch(`/dose/plan?week=${{w}}&volume_l=${{v}}`);
            const j = await r.json();
            document.getElementById('planbox').innerText = JSON.stringify(j, null, 2);
          }}
          async function doExecute(dry) {{
            const w = document.getElementById('week').value;
            const v = document.getElementById('vol').value;
            const r = await fetch(`/dose/execute?week=${{w}}&volume_l=${{v}}&dry_run=${{dry?1:0}}`, {{method:'POST'}});
            const j = await r.json();
            document.getElementById('planbox').innerText = JSON.stringify(j, null, 2);
          }}
        </script>
        </body></html>
        """
        return HTMLResponse(content=html)

    @app.get("/nutrients/{week}")
    def nutrients(week: int):
        return {"week": week, "ml_per_10L": get_week_schedule(week)}

    @app.get("/history")
    def history():
        return {"samples": read_recent(100)}

    @app.get("/dose/plan")
    def dose_plan(week: int = Query(..., ge=1, le=52), volume_l: float | None = None):
        return doser.plan(week, volume_l)

    @app.post("/dose/execute")
    def dose_execute(week: int = Query(..., ge=1, le=52), volume_l: float | None = None, dry_run: int = 0):
        res = doser.execute(week, volume_l, dry_run=bool(dry_run))
        return res

    return app