# AI handoff: Dashboard UI + Settings Reorg (2025-11-02)

This document briefs the next AI/engineer on the current state of the RDWC v4 dashboard, how controller settings are wired, and what to watch out for when making changes.

## TL;DR
- Tabs fixed (single active view); final order: Overview, Sensors, pH, EC, Temperature, Lights, Circulation, Relays, Schedule, Settings.
- Camera merged into Overview.
- Controller settings moved out of System Settings into each controller tab under collapsible sections.
- Saving now uses PUT /api/settings with dotted keys and server-side validation; errors surface in UI toasts.
- Global CSS added so inputs/selects are consistent height and never overlap.
- EC UI shows ppm; backend stores mS/cm with conversion in JS.

## Frontend map
- `app/static/index.html`
  - Global CSS variables for controls and consistent sizing.
  - Collapsible controller settings sections in pH/EC/Temperature/Circulation.
  - Schedule inputs (time + duration) still use legacy `/settings` API for lights window.
  - Dynamic script loader: `controller_settings.js` is included in the chain.
- `app/static/js/controller_settings.js`
  - Loads from GET `/api/settings` (grouped namespaces).
  - Saves to PUT `/api/settings` with dotted keys.
  - pH: updates band text after save; validates low < high.
  - EC: UI in ppm ↔ converts to mS/cm for save; updates band.
  - Temperature: updates the target display after save.
  - Circulation: saves min off times for main/chiller pumps.
- `app/static/js/settings.js`
  - System Settings now focuses on General, Safety flags, Alerts (email/cooldown), UI, Calibration; controller-specific targets/dosing removed from here.

## Backend map
- `app/main.py`
  - GET `/api/settings` → grouped namespaces; values are strings.
  - PUT `/api/settings` → partial updates; returns `{ok, updated, requires_restart}` or 422 `{field, message}` on validation failure.
  - PUT `/settings` (legacy) → system volume + lights schedule; returns preview window for the day.
- `app/settings.py`
  - DEFAULTS expanded with namespaced keys.
  - `validate_partial(partial)` enforces ranges/types and cross-field checks.
  - `upsert_settings(partial)` writes dotted keys to SQLite key/value store and busts legacy cache.

## Validation highlights (from `validate_partial`)
- pH targets: `targets.ph_low` and `targets.ph_high` in 4.0–7.5 and `ph_low < ph_high`.
- EC targets: 0.0–4.0 mS/cm; `target±tolerance` must remain within 0–4.
- Temp target: `targets.temp_target_c` 15–28°C.
- Pump/chiller min on/off: 0–3600s.
- Dosing calibration and safety ranges enforced (see file for details).
- General: `general.reservoir_liters` 1–1000, `general.grow_start_date` YYYY-MM-DD and not in future.

## Example payloads to PUT /api/settings
pH controller:
```json
{
  "targets.ph_low": 5.8,
  "targets.ph_high": 6.2,
  "dosing.pulse_ml_grow": 1.0,
  "dosing.pulse_ml_micro": 0.5,
  "dosing.pulse_ml_bloom": 1.5,
  "dosing.max_ml_hour_": 20,
  "dosing.max_ml_day_": 80,
  "dosing.mix_delay_s": 600,
  "dosing.ph_up_ml_per_sec": 25,
  "alerts.ph_lo_alert": 5.5,
  "alerts.ph_hi_alert": 6.8
}
```

EC controller (ppm shown in UI → mS/cm here):
```json
{
  "targets.ec_target": 1.8,
  "targets.ec_tolerance": 0.2,
  "alerts.ec_lo_alert": 1.2,
  "alerts.ec_hi_alert": 2.2
}
```

Temperature & chiller:
```json
{
  "targets.temp_target_c": 19,
  "alerts.temp_lo_alert": 16,
  "alerts.temp_hi_alert": 24,
  "safety.chiller_min_off_s": 600,
  "safety.chiller_min_on_s": 300
}
```

Circulation (pump safety):
```json
{
  "safety.main_pump_min_off_s": 5,
  "safety.chiller_pump_min_off_s": 5
}
```

## Global CSS notes
Inputs/selects/textarea are normalized via variables in `index.html`:
- `--control-h: 36px`, padding `6px 10px`, bg `#1f2937`, border `#374151`, fg `#e0e0e0`, radius `6px`.
- `*, *::before, *::after { box-sizing: border-box }` avoids overflow.
- `details > summary input/select` are compact and not full-width to prevent collisions in headers.

## Deployment
- Static assets: copy changed files to `/home/pi/RDWC-v4/app/static/...`.
- No backend restart required for static changes.
- Service name: `rdwc.service`; check with `systemctl status rdwc.service` if needed.
- Dashboard default port: 8080; camera stream via `/camera/stream`.

## Known constraints and UX notes
- EC UI uses ppm but backend persists in mS/cm; conversions handled in `controller_settings.js`.
- Schedule tab still uses legacy `/settings` for lights window; immediate preview is returned.
- Save buttons show spinner, then success pulse; on error, a toast displays `{field} {message}` from server.

## Quick acceptance checks
- Saving controller settings returns 200 with `{ok:true}` and updates bands/displays.
- Invalid inputs (e.g., `ph_low >= ph_high`) return 422; UI shows which field failed.
- Inputs look consistent height across all tabs, including inside collapsibles.

## Next steps (suggested)
1. Mobile polish: confirm layout at < 480px, adjust grid min widths if needed.
2. Consolidate duplicate `.btn-secondary` declarations in `index.html` (two variants exist) into one source of truth.
3. Add smoke tests for `/api/settings` validations (Python unit tests) and a tiny front-end harness for save flows.
4. Consider migrating Schedule to namespaced settings for consistency, or leave legacy as-is with clear comments.
5. Document EC ppm↔mS/cm conversions in the Settings UI tooltip for clarity.

---
Last verified: 2025-11-02
Commit hint: `index.html` contains `<meta name="version" content="20251102c"/>` for cache busting.
