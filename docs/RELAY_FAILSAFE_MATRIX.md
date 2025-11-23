# Relay Fail-Safe Matrix

**Document**: RELAY-MATRIX-001  
**Date**: 2025-11-23  
**Revision**: v1.0  

---

## Purpose
Defines the mixed NC / NO relay wiring strategy now implemented in RDWC v4 and the expected physical states when controller logic or power is lost. Serves as a quick reference for commissioning, troubleshooting, and post‑crash recovery.

---

## Summary Table
| Device | Tag | GPIO | Relay Wiring | Fail (Controller / Power Loss) | Intended Fail Outcome | Safety Rationale | Recovery Action |
|--------|-----|------|--------------|--------------------------------|-----------------------|------------------|-----------------|
| Main circulation pump | P-301 | 26 | NC | ON | Maintain circulation | Prevents oxygen depletion & stratification | Verify flow; no action unless maintenance required |
| Chiller circulation pump | P-302 | 16 | NC | ON | Maintain loop circulation | Avoids stagnant warm loop damaging chiller | Confirm loop running; resume control logic |
| Water chiller | C-401 | 20 | NC | ON | Continue cooling | Prevents rapid temp rise risking root health | Check temp; controller will adjust hysteresis |
| Grow lights | L-501 | 21 | NO | OFF | Prevent uncontrolled lighting | Avoids photoperiod disruption / heat | Resume schedule edges if outage crossed a boundary |
| pH UP pump | PP-201 | 5 | NO | OFF | No chemical dosing | Prevents runaway pH correction | Review last dose log; restart auto if safe |
| Micro nutrient pump | PP-202 | 13 | NO | OFF | No nutrient dosing | Prevents concentration spikes | Inspect reservoir; resume recipe if needed |
| Grow nutrient pump | PP-203 | 6 | NO | OFF | No nutrient dosing | Same reasoning | Same as Micro |
| Bloom nutrient pump | PP-204 | 19 | NO | OFF | No nutrient dosing | Same reasoning | Same as Micro |

---

## Design Notes
- NC used only for assets where continuous operation during a controller outage reduces risk (thermal stability, oxygenation).
- NO retained for anything that could cause irreversible changes if uncontrolled (chemicals, light exposure).
- GPIO layer remains active‑low; wiring choice modifies the mechanical default when coil de‑energized.
- Software reconciliation: At startup relay guard compares expected logical state to physical, logs anomalies.

## Commissioning Checklist Additions
1. Simulate controller stop (`systemctl stop rdwc.service`) – verify pumps & chiller stay ON, lights & dosing OFF.
2. Restore service; confirm controller restores any mismatched states gracefully within one control cycle.
3. Record verification in commissioning report JSON under `relay_failsafe_verification`.

## Maintenance
- Monthly: Visual inspection for relay coil heat discoloration (NC channels experience reduced energization time compared to prior design).
- Annual: Functional test of each NC relay by manually energizing/de‑energizing and confirming contact return.

## Change Log
- v1.0 (2025-11-23): Initial matrix added after migration to mixed NC/NO strategy.

---

End of Relay Fail-Safe Matrix
