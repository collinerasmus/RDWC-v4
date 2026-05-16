# RDWC-v4 Documentation and Housekeeping Fact-Check Audit

Date: 2026-05-16
Scope: repository first-party docs and core runtime logic checks
Method: static fact-check against current repository files and API routes plus full test run

## Executive Summary

- First-party markdown files scanned: 112
- Active (non-archive) markdown files: 51
- Archive markdown files: 61
- Active docs with broken local links: 3 unique
- Active docs with stale file-path references: 134
- Active docs with references to backend endpoints confirmed missing: 18
- Full test suite result: 209 passed
- Editor diagnostics: none

Conclusion: codebase is stable under tests, but documentation and housekeeping are not at a 100% professional baseline yet.

## Critical Findings (Fix First)

### C1) Core docs describe removed/renamed UI tabs and architecture
- README still describes Sensors and Calibration tabs as active top-level tabs, while live nav no longer includes Sensors and only includes Overview, Camera, pH, EC, Temperature, Circulation, Lights, Schedule, System.
- HMI_SHOWCASE describes React app and old tab model; UI is currently server-rendered HTML + modular JS.
- SYSTEM_ARCHITECTURE diagrams include outdated tab and controller naming details.

### C2) High-visibility docs contain dead file references
- SCHEDULER_FIX_COMPLETE references app/static/js/scheduler_manager.js (file does not exist).
- HANDOVER_COMPLETE and docs/screenshots/README reference docs/screenshots/overview.png with wrong relative path context.
- CHANGELOG references docs/CHILLER_CHART_GUIDE.md (file missing).

### C3) Active docs reference endpoints that do not exist in backend
Confirmed missing in app/**/*.py:
- /api/chiller/auto/enable
- /api/chiller/hysteresis
- /api/circulation/chiller_pump
- /api/circulation/main_pump
- /api/lights/on
- /api/lights/off
- /api/lights/status
- /api/mode
- /api/diary
- /api/frontend-logs
- /api/frontend/logs/trim
- /api/sensors/readings
- /api/system/mode

### C4) Service naming and operations guidance is inconsistent
- Docs and scripts use both rdwc and rdwc-api service names.
- PI_DEPLOY_GUIDE references rdwc-watchdog.service, which is not present in repository systemd units.
- This creates operational risk for deployment and maintenance procedures.

## Major Findings

### M1) Environment/IP drift across active docs
- Many active docs hardcode 192.168.88.49 while current ops context frequently uses 192.168.88.55.
- Hardcoded addresses appear in README, QUICK_REFERENCE, PI_DEPLOY_GUIDE, START_HERE, STATUS_AT_A_GLANCE, tools/README and others.

### M2) Active docs reference non-existent implementation files
Examples:
- app/chiller.py
- app/circulation.py
- app/lights.py
- app/mode.py
- app/system_mode.py
- app/sensors_mode.py
- app/diary_api.py
- app/circulation_coordinator.py
- app/static/js/chiller.js
- app/static/js/temp_chart.js
- tools/commission_all.py
- tools/deploy_alerts.sh
- tools/sensor_health.ps1
- systemd/system/rdwc.service
- data/relay_state.js

### M3) Test documentation references obsolete test modules
- Multiple docs reference old test file names no longer present under tests/ (for example tests/test_ph_control.py and older per-controller suites).

### M4) Readme status metadata is stale
- Last deploy commit/date in README is stale versus current main branch.
- Status statements claim professional completeness while multiple drift issues remain.

## Housekeeping Findings (Code/Runtime)

### H1) Hidden calibration section still exists in UI markup
- app/static/index.html still contains section data-tab="calibration" with no top-level nav entry.
- This creates ambiguity between intended IA and actual rendered navigation.

### H2) Sensors modules still load and poll aggressively after Sensors tab removal
- sensors.js is still loaded globally and runs setInterval(simplePoll, 2000).
- This may be intentional for cross-module events, but currently adds background work and potential console noise despite tab removal.

### H3) Script bundle still loads removed-tab modules
- index.html loader includes sensors.js and sensors_chart.js even after Sensors tab removal.
- Keep if intentionally required for shared telemetry, otherwise trim for cleaner startup and less client overhead.

## Archive Documentation Findings

- Archive content contains substantial historical references to old endpoints, old files, and old workflow assumptions.
- Not all archive drift is a bug, but current archive files should be clearly marked as historical and non-authoritative.

## Verified Positives

- Backend route coverage is broad and core modern endpoints are present (for example /api/relays/status, /api/sensors/status, /api/system_mode, /api/controllers/status, /api/scheduler/*).
- Full automated tests pass: 209/209.
- No current editor diagnostics reported.

## Complete Action Backlog (No fixes applied in this pass)

1. Create a single canonical operator doc and demote conflicting root docs to archive.
2. Normalize service naming across docs and scripts (rdwc vs rdwc-api) and remove references to non-existent watchdog unit.
3. Replace hardcoded IP references with placeholders and one canonical env/config variable source.
4. Update README to current UI IA, architecture, and deployment reality.
5. Remove or rewrite stale docs that assert removed files/endpoints.
6. Fix all broken local markdown links in active docs.
7. Replace dead file references with current file names or explicitly mark as historical.
8. Replace stale endpoint docs with current routes from app/main.py.
9. Reconcile calibration-tab documentation with current UX (calibration in pH/EC tabs).
10. Decide whether hidden calibration-card section should be removed or reintroduced in nav intentionally.
11. Decide whether sensors.js/sensors_chart.js should remain loaded globally post Sensors-tab removal.
12. Run a second validation pass after cleanup and enforce doc linting/link checking in CI.

## Suggested Execution Order

Phase 1 (Safety/Operations): C4, C3, M1
Phase 2 (Primary docs): C1, C2, M4
Phase 3 (Housekeeping): H1, H2, H3
Phase 4 (Archive policy): archive bannering and index hygiene
Phase 5 (Guardrails): add automated doc checks in CI
