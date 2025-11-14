# EC Tab — UI Spec and Acceptance Criteria

Baseline: commit `235c9f9` (UI: remove legacy app.css, strengthen .kpi specificity, move estop-banner, bump theme v5)
First Tab to Finish: EC Control tab (parity with pH)

## Scope
Finish the EC tab to match the standardized UI patterns already applied to pH and other tabs: minimal header, KPI row, mode controls behavior, content ordering, and chart/controls consistency. Remove deprecated and duplicate UI elements.

## Acceptance Criteria

### 1) Header Parity (match pH)
- Title: `EC Control` (or `EC`) uses the standardized minimal header template.
- Health chip: controller health chip sits next to the title (match pH).
- Mode chips: `AUTO`, `MANUAL`, `MAINT` appear on the right of the header and reflect `/api/system/mode` and EC auto state.
- E‑STOP button: danger variant appears at the far right, disabled state and tooltip when locked.
- No extra items: Remove freshness/age, calibration chips, and K‑factor from the header; these move into meta or Settings.

### 2) KPI Row (theme v5, .kpi)
- Styling: KPIs use the unified `.kpi` styles (no inline CSS). Typography, spacing, and units match pH.
- Content: Show current EC in `mS/cm` as the primary KPI. Secondary mini-KPIs may include ppm@500 hint if already in pH parity style (no “X/Y” shorthand).
- Guards/Color: KPI value coloring reflects guard state consistent with pH (OK/warn/danger) powered by the same health logic.
- Live Update: Values update without reflowing the surrounding KPI structure (preserve inner HTML where applicable per `8842cb0`).

### 3) Chips and Meta (below header)
- Health chip: Shown in the header next to the title (match pH); do not duplicate below.
- Calibration/K‑factor: K and calibration status appear as read-only chips or in the EC Settings collapsible (not in the header).
- No duplicates: Remove the "last-three" recent dose pills row and any duplicate status lines (per `817bc3f`, `177ef74`).

### 4) Controls & Interactions
- Auto enable/disable: Buttons call existing EC auto endpoints; reflect disabled state during requests; show toast on success/failure.
- Manual quick dose: Buttons call existing `/api/ec/dose` endpoints; show short, non-blocking feedback; disabled when guards block dosing; reason surfaced via tooltip or toast.
- E‑STOP behavior: All mutation controls properly disable and show why when E‑STOP is active; header button toggles via `/api/relays/estop/toggle` with GET fallback.
- Mode reassert: Mode chips allow reasserting same mode and reflect server truth on refresh (consistent with pH).

### 5) Content Ordering
- Order: Header → KPI row → health/meta chips → Control card (Auto/Manual) → Chart (Dose history with overlays) → Settings (collapsible; includes calibration/K‑factor).
- Consistency: Mirrors pH ordering and spacing.

### 6) Charts & Controls
- Chart style: Height and container sizing match pH charts; no inline styles.
- Trend controls: Use compact dropdown and date/time inputs consistent with pH/Sensors. Inputs right-aligned in the chart header row.
- Axes/labels: No "X/Y" placeholders anywhere; units shown only where needed (EC mS/cm); axis labels minimal and consistent with pH.
- Data window: Shows full requested time range; server bucketing supported; CSV export available and consistent with pH behavior.

### 7) Empty/Error States
- Stale/offline: EC KPIs and chips reflect stale/offline according to the unified health logic (same precedence and dots as pH/Sensors).
- API errors: Non-blocking toasts and unobtrusive banners; controls disable and re-enable appropriately.
- Maintenance: Clear maintenance explanation when MAINT mode is active.

### 8) Accessibility & Performance
- Keyboard focus order is logical; all interactive elements have accessible names.
- No layout shifts during KPI updates; controls do not jump.
- No inline CSS; all styles via the shared theme/classes.

## Done Means
- Visual parity with pH header and KPI look.
- No deprecated rows or duplicates (e.g., last-three pills removed; no X/Y placeholders; no inline CSS).
- K‑factor and calibration status not in header; available as chips/settings.
- All controls wired to existing endpoints with disabled/guard behaviors and tooltips consistent with pH.
- Chart height/controls, range selection, and CSV mirror pH patterns.

## Validation Checklist
- Header contains only: title, mode chips, E‑STOP button.
- KPI row uses `.kpi` styles; EC units mS/cm; guard color consistent.
- Health chips below header; K/Cal relocated; no header clutter.
- No "last-three" row; no "X/Y" labels/units anywhere.
- Auto/Manual dose buttons work; blocked states show reasons.
- Chart renders full range; trend controls match pH; CSV works.
- E‑STOP disables mutations globally and shows tooltip.
- No inline styles in EC tab; passes quick a11y focus walk.

## Notes / References
- Baseline commit: `235c9f9` (theme v5, KPI specificity, estop-banner move).
- Related EC UI parity commits: `817bc3f`, `177ef74`, `10b05f4`, `8842cb0`.
- Follow UI standardization: minimal headers (`9dbca71`, `315a0f5`), health dots alignment, and KPI/card utilities.
