from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from .config import settings
from .nutrients import get_week_schedule
from .history import read_recent
from .diag import i2c_scan, probe_now, atlas
from .atlas_helper import run_fixer
from .sensors import Sensors

import subprocess
import json

def cam_status():
    try:
        out = subprocess.check_output(["systemctl","is-active","mjpg-streamer.service"], text=True).strip()
    except Exception:
        out = "unknown"
    # check port
    try:
        head = subprocess.check_output(["bash","-lc","curl -s -I http://127.0.0.1:8081/?action=stream | head -n1"], text=True).strip()
    except Exception as e:
        head = f"curl_error:{e}"
    # get last few log lines
    try:
        logs = subprocess.check_output(["bash","-lc","journalctl -u mjpg-streamer.service -n 20 --no-pager"], text=True)
    except Exception:
        logs = ""
    return {"service": out, "http_head": head, "logs_tail": logs}

def build_app(controller, sampler, doser):
    app = FastAPI(title="RDWC", version="0.5.1")

    @app.get("/status")
    def status():
        data = controller.loop_once()
        return {"env": settings.env, "sample_interval_sec": settings.sample_interval_sec, "data": data}

    @app.get("/diag")
    def diag():
        return {"env": settings.env, "force_mock": settings.force_mock_sensors, "i2c": i2c_scan(), "now": probe_now()}

    # --- NEW: force a fresh sensor read now (no cache) ---
    @app.get("/read_now")
    def read_now():
        s = Sensors()
        try:
            data = s.sample_once()
            return {"ok": True, "data": data}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # --- NEW: camera status endpoint ---
    @app.get("/cam_status")
    def camstat():
        return cam_status()

    # accept both GET and POST for convenience
    @app.get("/fix_ezo")
    @app.post("/fix_ezo")
    def fix_ezo():
        return run_fixer()

    @app.get("/atlas")
    @app.post("/atlas")
    def atlas_cmd(addr: str, cmd: str):
        """Send a raw Atlas I2C command. Example: /atlas?addr=0x63&cmd=I"""
        return atlas(addr, cmd)

    @app.post("/actuate/{name}/{on}")
    def actuate(name: str, on: int):
        onb = (on == 1)
        controller.relays.set(name, onb)
        return {"ok": True, "pin": name, "state": onb}

    @app.get("/", response_class=HTMLResponse)
    def ui(request: Request):
        data = sampler.latest()
        cam = cam_status()
        # Generate relay controls outside f-string to avoid backslash issues
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
          pre {{ text-align:left;white-space:pre-wrap;background:#0f0f0f;padding:0.6em;border-radius:8px; max-height:240px; overflow:auto; }}
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

        <h2>Live Camera</h2>
        <div class="card">
          <div><small>Service: {cam['service']} • HTTP: {cam['http_head']}</small></div>
          <img src="http://{request.client.host}:8081/?action=stream" style="max-width:90%;border-radius:8px;" onerror="this.replaceWith(Object.assign(document.createElement('div'),{{innerText:'Camera Offline',style:'padding:1em'}}))">
          <details style="margin-top:8px;"><summary>Logs</summary><pre>{cam['logs_tail']}</pre></details>
        </div>

        <h2>System Diagnostics</h2>
        <div class="card" style="min-width:340px;">
          <button onclick="fetch('/diag').then(r=>r.json()).then(j=>diagbox.innerText=JSON.stringify(j,null,2))">Refresh Diagnostics</button>
          <button onclick="fetch('/read_now').then(r=>r.json()).then(j=>diagbox.innerText=JSON.stringify(j,null,2))">Test Atlas Sensors</button>
          <button onclick="fetch('/fix_ezo').then(r=>r.json()).then(j=>diagbox.innerText=JSON.stringify(j,null,2))">Run Atlas Fixer</button>
          <div>
            Atlas Command: <input id="acmd" value="I" size="10"> Address: <input id="aaddr" value="0x63" size="6">
            <button onclick="doAtlas()">Send</button>
          </div>
          <pre id="diagbox"></pre>
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
          async function loadDiag(){{
            const r=await fetch('/diag'); document.getElementById('diagbox').innerText=JSON.stringify(await r.json(),null,2);
          }}
          async function testAtlas(){{
            const addrs=['0x63','0x64','0x66']; let results={{}};
            for(const addr of addrs){{
              try{{
                const r=await fetch(`/atlas?addr=${{addr}}&cmd=I`,{{method:'POST'}});
                results[addr]=await r.json();
              }}catch(e){{results[addr]={{error:e.message}};}}
            }}
            document.getElementById('diagbox').innerText=JSON.stringify(results,null,2);
          }}
          async function doAtlas(){{
            const a=document.getElementById('aaddr').value, c=document.getElementById('acmd').value;
            const r=await fetch(`/atlas?addr=${{a}}&cmd=${{encodeURIComponent(c)}}`); diagbox.innerText=JSON.stringify(await r.json(),null,2);
          }}
        </script>
        <br><small>Auto-refresh {settings.ui_refresh_sec}s</small>
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
        target_us: int = getattr(settings,'ec_target_us',1200),
        tol_us: int = getattr(settings,'ec_tol_us',50),
        step_ml_per_10l: int = getattr(settings,'ec_step_ml_per_10l',5),
        max_ml_per_10l: int = getattr(settings,'ec_max_ml_per_10l',80),
        stabilize_wait_sec: int = getattr(settings,'ec_stabilize_wait_sec',45),
        dry_run: int = 0
    ):
        return doser.execute_to_ec(
            week=week, volume_l=volume_l, target_us=target_us, tol_us=tol_us,
            step_ml_per_10l=step_ml_per_10l, max_ml_per_10l=max_ml_per_10l,
            stabilize_wait_sec=stabilize_wait_sec, dry_run=bool(dry_run)
        )

    return app