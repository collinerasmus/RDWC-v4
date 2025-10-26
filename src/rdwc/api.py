from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from .config import settings
from .nutrients import get_week_schedule
from .history import read_recent
from .diag import diag_bundle

def build_app(controller, sampler, doser):
    app = FastAPI(title="RDWC", version="0.5.0")

    @app.get("/status")
    def status():
        data = controller.loop_once()
        return {"env": settings.env, "sample_interval_sec": settings.sample_interval_sec, "data": data}

    @app.get("/diag")
    def diag():
        return diag_bundle()

    @app.post("/actuate/{name}/{on}")
    def actuate(name: str, on: int):
        onb = (on == 1)
        controller.relays.set(name, onb)
        return {"ok": True, "pin": name, "state": onb}

    @app.get("/", response_class=HTMLResponse)
    def ui(request: Request):
        data = sampler.latest()
        # Generate relay controls outside f-string
        relay_controls = "".join([
            f"<div class='card'>{n}<br><button onclick=\"fetch('/actuate/{n}/1',{{method:'POST'}})\">ON</button><button onclick=\"fetch('/actuate/{n}/0',{{method:'POST'}})\">OFF</button></div>" 
            for n in controller.relays.pin_map.keys()
        ])
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
          pre {{ text-align:left;white-space:pre-wrap;background:#0f0f0f;padding:0.6em;border-radius:8px; }}
        </style></head><body>
        <h1>🌿 RDWC Control Panel</h1>
        <div class="card"><b>Temperature:</b> {data.get('temperature_c')}°C<br>
        <b>EC:</b> {data.get('ec')} µS/cm<br>
        <b>pH:</b> {data.get('pH')}</div><br><br>

        <h2>Relay Controls</h2>
        {relay_controls}

        <h2>Nutrient Planner</h2>
        <div class="card" style="min-width:340px;">
          <form onsubmit="return false;">
            Week: <input type="number" id="week" min="1" max="52" value="1">
            Volume (L): <input type="number" id="vol" min="1" step="1" value="{settings.total_volume_l}">
            <button onclick="doPlan()">Plan</button>
            <button onclick="doExecute(false)">Execute</button>
            <button onclick="doExecute(true)">Dry-Run</button>
          </form>
          <pre id="planbox"></pre>
        </div>

        <h2>EC Target Dosing</h2>
        <div class="card" style="min-width:340px;">
          Target (µS/cm): <input type="number" id="ectgt" value="{getattr(settings,'ec_target_us',1200)}">
          Tol (±µS): <input type="number" id="ectol" value="{getattr(settings,'ec_tol_us',50)}"><br>
          Step ml/10L: <input type="number" id="ecstep" value="{getattr(settings,'ec_step_ml_per_10l',5)}">
          Max ml/10L: <input type="number" id="ecmax" value="{getattr(settings,'ec_max_ml_per_10l',80)}"><br>
          Stabilize (s): <input type="number" id="ecwait" value="{getattr(settings,'ec_stabilize_wait_sec',45)}"><br>
          <button onclick="doExecuteToEC(false)">Execute to EC</button>
          <button onclick="doExecuteToEC(true)">Dry-Run</button>
          <pre id="ecbox"></pre>
        </div>

        <h2>Recent Readings</h2>
        <iframe src="/history" style="width:90%;height:220px;background:#111;color:#eee;border:none;"></iframe>

        <script>
          async function doPlan(){{
            const w=document.getElementById('week').value, v=document.getElementById('vol').value;
            const r=await fetch(`/dose/plan?week=${{w}}&volume_l=${{v}}`); document.getElementById('planbox').innerText=JSON.stringify(await r.json(),null,2);
          }}
          async function doExecute(dry){{
            const w=document.getElementById('week').value, v=document.getElementById('vol').value;
            const r=await fetch(`/dose/execute?week=${{w}}&volume_l=${{v}}&dry_run=${{dry?1:0}}`,{{method:'POST'}}); document.getElementById('planbox').innerText=JSON.stringify(await r.json(),null,2);
          }}
          async function doExecuteToEC(dry){{
            const w=document.getElementById('week').value, v=document.getElementById('vol').value;
            const tgt=document.getElementById('ectgt').value, tol=document.getElementById('ectol').value;
            const step=document.getElementById('ecstep').value, mx=document.getElementById('ecmax').value, wait=document.getElementById('ecwait').value;
            const url=`/dose/execute_to_ec?week=${{w}}&volume_l=${{v}}&target_us=${{tgt}}&tol_us=${{tol}}&step_ml_per_10l=${{step}}&max_ml_per_10l=${{mx}}&stabilize_wait_sec=${{wait}}&dry_run=${{dry?1:0}}`;
            const r=await fetch(url,{{method:'POST'}}); document.getElementById('ecbox').innerText=JSON.stringify(await r.json(),null,2);
          }}
        </script>
        <br><small><a href="/diag" style="color:#9dfd70;">Diagnostics</a> • Auto-refresh {settings.ui_refresh_sec}s</small>
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

    @app.post("/dose/execute_to_ec")
    def dose_execute_to_ec(
        week: int = Query(..., ge=1, le=52),
        volume_l: float | None = None,
        target_us: int = Query(default=settings.ec_target_us if hasattr(settings,'ec_target_us') else 1200),
        tol_us: int = Query(default=settings.ec_tol_us if hasattr(settings,'ec_tol_us') else 50),
        step_ml_per_10l: int = Query(default=getattr(settings,'ec_step_ml_per_10l',5)),
        max_ml_per_10l: int = Query(default=getattr(settings,'ec_max_ml_per_10l',80)),
        stabilize_wait_sec: int = Query(default=getattr(settings,'ec_stabilize_wait_sec',45)),
        dry_run: int = 0
    ):
        return doser.execute_to_ec(
            week=week, volume_l=volume_l, target_us=target_us, tol_us=tol_us,
            step_ml_per_10l=step_ml_per_10l, max_ml_per_10l=max_ml_per_10l,
            stabilize_wait_sec=stabilize_wait_sec, dry_run=bool(dry_run)
        )

    return app