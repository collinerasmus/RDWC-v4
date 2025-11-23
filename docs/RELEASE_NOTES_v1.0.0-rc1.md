# RDWC v4 — Release Notes (v1.0.0-rc1)

Date: 2025-11-23
Status: Release Candidate (as-built)

---

## Highlights
- Mixed NC/NO relay strategy implemented for fail-safe behavior:
  - NC (fail-ON): Main pump (P-301), Chiller pump (P-302), Water chiller (C-401)
  - NO (fail-OFF): Lights (L-501), all dosing pumps (PP-201..204)
- Documentation package completed/updated:
  - Operating Philosophy, P&ID, Electrical Schematic, I/O & Signal List
  - New: Relay Fail-Safe Matrix (quick-reference)
  - Maintenance Manual expanded with NC/NO checks
  - Final Verification guide updated with Phase 11 checklist
- Backend remains green: 171/171 tests passing

## Changes
- Relay wiring strategy migrated to mixed NC/NO to optimize fail states during controller/power loss
- Docs updated to reflect new behavior and recovery steps
- Version bumped to 1.0.0-rc1 in VERSION and pyproject.toml

## Verification
- Automated: All tests pass (171/171)
- Manual: Follow Phase 11 checklist in `FINAL_VERIFICATION.md`, including:
  - UI consistency checks across all tabs
  - Interlock behavior (main pump gating chiller/pump)
  - Dosing guards (press caps, daily caps, stale checks)
  - Fail-safe verification by stopping API service (pumps/chiller ON; lights/dosing OFF)

## Upgrade / Deployment Notes
- No DB migrations required
- After deploy, verify sensor freshness (<120s) and reconcile relay states in guard endpoint
- If outage crossed a light edge, manually confirm lights state and upcoming schedule

## Known Items / Next Steps
- Proceed with 48-hour soak testing on Pi
- Tag v1.0.0 stable following successful Phase 11 validation

## Acknowledgements
- UI standardization locked (Phase 8). System tab layout fix and consistent KPI/cards are in place.

---

End of Release Notes
