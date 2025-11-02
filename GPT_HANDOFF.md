# RDWC-v4 — Handover Brief (2025-11-02)

## Project rules (read first)

* **VS-first, GitHub is source of truth.** Pi only pulls & runs.
* **Do not break working features.** If unsure, branch and PR.
* **Relays are active-low.** Always return HIGH (OFF) in `finally`.
* **Safety first:** E-STOP & empty reservoir are hard stops.
  Maintenance Override bypasses **interval & daily-cap only** (stale/estop/reservoir still block). Test-only "allow stale on override" exists and is **OFF** by default.
* **Settings API uses dotted keys**; values are strings; server validates.

## Environment

* **Pi:** `pi@192.168.88.49`
* **GPIO (BCM):** pH Up=5, Grow=6, Micro=13, Bloom=19, Main Pump=26, Chiller Pump=16, Water Chiller=20, Grow Lights=21
* **I²C sensors:** pH 0x63, EC 0x64, RTD 0x66
* **Service:** `rdwc.service` (FastAPI + Uvicorn)
* **Web:** `http://192.168.88.49:8080`

## Current status (golden)

* **pH Up Automation v1.0 – COMPLETE & TAGGED** (`ph-auto-v1.0`)
  * Auto worker with warm-up, dose lock, backoff.
  * Learning estimator (ml per 1.0 pH) with reset endpoint.
  * UI badges: Disabled / Holding:reason / Ready + learned effect.
  * Endpoints:
    * `GET  /api/ph/status`
    * `POST /api/ph/dose`
    * `POST /api/ph/auto` `{ "enable": true|false }`
    * `POST /api/ph/auto/learn/reset`
    * `GET  /api/ph/auto/debug`
* **Dashboard/UI**
  * Tabs stable; camera in Overview.
  * Controller settings live under each controller tab.
  * `PUT /api/settings` with dotted keys; validation errors surfaced in toasts.
  * Static cache-buster meta is present (update when changing JS/CSS).

## Key files to touch

* Backend: `app/ph_control.py`, `app/settings.py`, `app/main.py`
* UI: `app/static/index.html`, `app/static/js/ph.js`, `app/static/js/controller_settings.js`
* Tests: `tests/*` (pytest)
* Tools: `tools/accept_ph_auto.sh`, `tools/ensure_safe_defaults.py`

## Deploy & verify snippets

```bash
# Pull & restart
ssh pi@192.168.88.49 "cd ~/RDWC-v4 && git pull && sudo systemctl restart rdwc && sleep 2"

# pH status (shows auto + guards)
ssh pi@192.168.88.49 "curl -s http://127.0.0.1:8080/api/ph/status | jq"

# Reset learner
ssh pi@192.168.88.49 "curl -s -X POST http://127.0.0.1:8080/api/ph/auto/learn/reset | jq"
```

## Acceptance checklist (10 min)

1. `GET /api/ph/status` shows `auto.enabled`, `holding_reason`, `learned_ml_per_pH`.
2. Manual **Prime** dose toggles BCM5 LOW→HIGH in `journalctl`.
3. With override **OFF**, cooldown blocks rapid repeat.
4. With override **ON**, only interval/daily-cap are bypassed (E-STOP/reservoir still block).
5. UI shows **Holding** reason when a guard is active.
6. `PUT /api/settings` with bad values returns 422 and UI toast displays the field.

---

## Next feature: **EC Control v1.0 (Manual + Automation, G/M/B mix dosing)**

**Goal:** Feature-parity with pH; automate raising EC using Grow/Micro/Bloom pumps in **sequential mix** (G → M → B) with configurable delay and learning of **ml per 1.0 mS/cm**. Respect all guards & existing dose lock.

**Create branch:** `feat/ec-control-v1`

### Backend (`app/ec_control.py`)

* Endpoints (mirror pH):
  * `GET  /api/ec/status` → `ec`, `targets:{low,high}`, `auto:{enabled,holding_reason,learned_ml_per_mScm}`, guards, recent, totals.
  * `POST /api/ec/dose` body:
    ```json
    { "ml": 30, "mix_ratio":"schedule|custom",
      "custom":{"grow":x,"micro":y,"bloom":z}, "reason":"manual" }
    ```
    Splits ml by ratio, actuates G→M→B with `dosing.mix_delay_s`.
  * `POST /api/ec/auto` `{ "enable": true|false }`
  * `POST /api/ec/auto/learn/reset`
  * `GET  /api/ec/auto/debug`
* **Guards:** `estop`, `safe_off`, `sensor_stale`(EC), `interval`, `daily_cap`, `reservoir`, plus `mix_lock` when the dose lock is held.
* **Learning:** estimate ml per 1.0 mS/cm from valid doses (observed pre/post EC), clamp [20, 400].
* **Planner:** aim midpoint of band, safety factor (0.6), clamp per-step to `[ec_step_ml_min, ec_step_ml_max]`.
* **Lock & warm-up:** reuse pH `_dose_lock`; one poll warm-up after enable.

### Settings (add to `app/settings.py`)

```python
"ec.auto_enabled": "false",
"targets.ec_low":  "0.8",
"targets.ec_high": "1.2",

"dosing.ec_step_ml_min": "10",
"dosing.ec_step_ml_max": "120",
"dosing.ec_safety_factor": "0.6",
"dosing.mix_delay_s": "2",

# Optional calib (0 = unknown)
"dosing.grow_ml_per_sec":  "0",
"dosing.micro_ml_per_sec": "0",
"dosing.bloom_ml_per_sec": "0",
```

### UI

* New **EC Control** card (Status / Manual / Automation).
* Manual: `+ step ml`, Custom ml, **Mix source** selector: Schedule ratio (from `nutrient_schedule` active week) or Custom (G/M/B).
* Automation: toggle + **State badge** & learned badge `≈ X ml per 0.1 mS/cm`.
* Chart: blue points (tooltip shows split G/M/B + pre/post EC), purple cumulative, green daily.
* Settings tab adds EC dosing fields + pump calibrations. Update cache-buster.

### Tests (pytest)

* `test_ec_status_fields_present`
* `test_ec_manual_mix_split_custom`
* `test_ec_automation_holds_on_interval_and_mix_lock`
* `test_ec_learner_applies_and_clamps`
* `test_ec_reset_endpoint`

### Safety wiring

* Pumps (BCM): Grow=6, Micro=13, Bloom=19 (active-low).
* Always `finally: HIGH (OFF)` per pump; total dose honored even if one component is zero.
* Respect E-STOP & reservoir guards everywhere.

### Deploy quick-check

```bash
ssh pi@192.168.88.49 '
cd ~/RDWC-v4 && git pull && sudo systemctl restart rdwc && sleep 2;
curl -s http://127.0.0.1:8080/api/ec/status | jq ".auto, .guards";
curl -s -X POST http://127.0.0.1:8080/api/ec/dose \
 -H "Content-Type: application/json" \
 -d "{\"ml\":30,\"mix_ratio\":\"schedule\",\"reason\":\"manual-test\"}" | jq;
sleep 35; curl -s http://127.0.0.1:8080/api/ec/status | jq ".auto";
'
```

---

## Known gotchas

* **JSON quoting over SSH from PowerShell** can mangle payloads; prefer running the provided shell scripts directly **on the Pi** or use single-quoted heredocs.
* **Cache busting:** update `<meta name="version" content="...">` in `index.html` when changing JS/CSS.
* **EC units:** UI may show ppm, backend stores **mS/cm**; conversions live in JS.

---
Last verified: 2025-11-02
Ready for: EC Control v1.0 (branch `feat/ec-control-v1`)
