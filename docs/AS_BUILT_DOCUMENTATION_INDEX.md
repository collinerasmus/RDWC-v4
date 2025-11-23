# RDWC-v4 As-Built Documentation Index

**Version**: 1.0.0-rc1 (Pending Release)  
**Date**: 2025-11-23  
**Status**: Phase 9 Complete; Proceeding to Phase 11 Testing  

---

## Document Status

This index tracks all engineering documentation for the RDWC-v4 system at the "As-Built" milestone.

| Document | File | Status | Notes |
|----------|------|--------|-------|
| **System Architecture** | `SYSTEM_ARCHITECTURE.md` | ✅ Complete | High-level overview |
| **P&ID** | `docs/PID_DIAGRAM.md` | ✅ Complete | Piping & Instrumentation |
| **Electrical Schematic** | `docs/ELECTRICAL_SCHEMATIC.md` | ✅ Complete | GPIO, I²C, power distribution |
| **I/O & Signal List** | `docs/IO_SIGNAL_LIST.md` | ✅ Complete | All inputs/outputs documented |
| **Equipment List** | `docs/EQUIPMENT_LIST.md` | ⚠️ Template Created | Needs actual part numbers |
| **Operating Philosophy** | `docs/OPERATING_PHILOSOPHY.md` | ✅ Complete | Control strategy + mixed NC/NO fail‑safe documented |
| **Operating Manual** | `docs/OPERATING_MANUAL.md` | ⚠️ Template Created | Procedures documented |
| **Maintenance Manual** | `docs/MAINTENANCE_MANUAL.md` | ✅ Complete | PM schedule + NC/NO inspections documented |
| **Relay Fail‑Safe Matrix** | `docs/RELAY_FAILSAFE_MATRIX.md` | ✅ Complete | Quick-reference for NC/NO wiring & recovery |
| **Commissioning Checklist** | `PI_COMMISSIONING_CHECKLIST.md` | ✅ Complete | Ready for use |
| **Commissioning Automation** | `docs/COMMISSIONING_AUTOMATION.md` | ✅ Complete | Automated commissioning scripts |
| **Ops Runbook** | `docs/Ops-Runbook.md` | ✅ Complete | Operational procedures |
| **API Documentation** | `README.md` (API section) | ✅ Complete | Endpoint reference |
| **Deployment Guide** | `deploy/DEPLOYMENT_SUMMARY.md` | ✅ Complete | Pi setup instructions |
| **Quick Reference** | `QUICK_REFERENCE.md` | ✅ Complete | Common tasks & commands |
| **Troubleshooting** | `DEPLOYMENT_TROUBLESHOOTING.md` | ✅ Complete | Common issues & fixes |

---

## Engineering Documentation

### P&ID (docs/PID_DIAGRAM.md) ✅
- **Purpose**: Complete system schematic showing all sensors, actuators, piping, and control logic
- **Contents**:
  - Mermaid flowchart of entire RDWC system
  - Tag nomenclature (ISA-5.1 standard)
  - Control logic descriptions (circulation interlock, E-STOP, dosing, temperature, lights)
  - Alarm & trip conditions
  - Material & energy balance
  - Fail-safe states
- **Status**: Complete, ready for review

### Electrical Schematic (docs/ELECTRICAL_SCHEMATIC.md) ✅
- **Purpose**: Detailed wiring diagrams for all electrical connections
- **Contents**:
  - System architecture ASCII diagram
  - Raspberry Pi GPIO pinout table
  - Relay board wiring (active-low signaling, mixed NC/NO wiring)
  - I²C bus schematic with pull-ups
  - Power distribution (5V, 12V, 120VAC)
  - Fusing & protection recommendations
  - Atlas EZO sensor wiring per device
  - Cable specifications
  - Grounding & safety notes
  - Troubleshooting procedures
- **Status**: Complete, ready for review

### I/O & Signal List (docs/IO_SIGNAL_LIST.md) ✅
- **Purpose**: Comprehensive list of all system inputs, outputs, and control signals
- **Contents**:
  - Input signals table (sensors: RTD, pH, EC)
  - Output signals tables (dosing pumps, circulation, chiller, lights)
  - Control signals (interlocks, dosing guards, mode signals)
  - Alarm signals (high/medium/critical priority)
  - Communication protocols (I²C, GPIO, API, database)
  - Fail-safe summary (updated for mixed NC/NO)
- **Status**: Complete, ready for review

### Equipment List (docs/EQUIPMENT_LIST.md) ⚠️
- **Purpose**: Bill of materials with manufacturer specs, part numbers, sources
- **Contents** (Template):
  - Raspberry Pi 4 Model B specifications
  - Atlas Scientific EZO sensors (RTD, pH, EC)
  - Relay board (8-channel, active-low)
  - Dosing pumps (peristaltic, 12VDC)
  - Circulation pumps (main, chiller)
  - Water chiller unit
  - Grow lights
  - Power supplies
  - Cables, connectors, enclosures
- **Status**: Template created, needs actual part numbers from user
- **Action Required**: User to provide manufacturer/model numbers for all hardware

### Operating Philosophy (docs/OPERATING_PHILOSOPHY.md) ⚠️
- **Purpose**: High-level control strategy and safety hierarchy
- **Contents** (Template):
  - Control strategy overview (cascading loops, setpoint tracking)
  - Safety system hierarchy (E-STOP > interlocks > mode > automation)
  - Alarm management (priorities, escalation, acknowledgment)
  - Mode logic (auto/manual/maintenance per controller)
  - Dosing strategy (pH auto-learning, EC recipe-based)
  - Temperature control strategy (hysteresis, MIN_ON/OFF)
  - Lights schedule strategy (edge-only, midnight crossover)
- **Status**: Template created with existing logic documented
- **Action Required**: Review and validate against operational intent

### Operating Manual (docs/OPERATING_MANUAL.md) ⚠️
- **Purpose**: Step-by-step procedures for normal and emergency operation
- **Contents** (Template):
  - Startup sequence (power on, verify sensors, check relays, calibrate if needed)
  - Normal operation (monitoring, dosing, adjusting setpoints)
  - Shutdown sequence (safe power down, E-STOP if needed)
  - Emergency procedures (E-STOP activation, power loss recovery, leak detection)
  - Troubleshooting guide (sensor failures, relay issues, communication errors)
  - Web UI navigation guide
- **Status**: Template created with key procedures documented
- **Action Required**: Expand with user-specific operational preferences

### Maintenance Manual (docs/MAINTENANCE_MANUAL.md) ⚠️
- **Purpose**: Preventive maintenance and calibration procedures
- **Contents** (Template):
  - Calibration procedures:
    - pH: 3-point (4.0/7.0/10.0) or 2-point (4.0/7.0)
    - EC: 2-point (dry/1413µS) or 1-point (1413µS)
    - Dosing pumps: prime, run, measure, commit
  - Preventive maintenance schedule:
    - Daily: Check sensor readings, verify automation
    - Weekly: Clean pH probe, check EC cell
    - Monthly: Vacuum database, check relay contacts
    - Quarterly: Full system calibration, backup database
  - Sensor cleaning procedures (pH probe KCl storage, EC cell rinsing)
  - Database maintenance (`VACUUM`, `ANALYZE`, backup/restore)
  - Software updates (Git pull, systemd restart, rollback procedure)
- **Status**: Template created with existing procedures documented
- **Action Required**: Add PM schedule intervals based on user's grow cycle

---

## Operational Documentation

### Commissioning Checklist (PI_COMMISSIONING_CHECKLIST.md) ✅
- **Purpose**: Step-by-step commissioning verification
- **Contents**:
  - Pre-startup inspection
  - Sensor verification (I²C scan, online status)
  - Calibration confirmation (pH flags, EC status)
  - Relay functional testing (manual control, E-STOP)
  - Controller mode testing (auto/manual/maintenance)
  - Interlock verification (circulation safety)
  - Dosing pump calibration
  - Schedule verification (lights edges)
- **Status**: Complete and tested

### Commissioning Automation (docs/COMMISSIONING_AUTOMATION.md) ✅
- **Purpose**: Automated commissioning scripts and API flows
- **Contents**:
  - `tools/commission.ps1` script documentation
  - API endpoint sequences for commissioning
  - Acceptance criteria per step
  - JSON report format
  - Error handling and recovery
- **Status**: Complete, scripts operational

### Ops Runbook (docs/Ops-Runbook.md) ✅
- **Purpose**: Operational procedures and common tasks
- **Contents**:
  - Daily operations checklist
  - Sensor reading interpretation
  - Dosing procedures (manual and auto)
  - Setpoint adjustment procedures
  - Mode switching procedures
  - Backup and recovery procedures
- **Status**: Complete

### Deployment Guide (deploy/DEPLOYMENT_SUMMARY.md) ✅
- **Purpose**: Raspberry Pi setup and deployment procedures
- **Contents**:
  - Fresh Pi OS installation
  - Python environment setup
  - SystemD service configuration
  - Database initialization
  - First-time calibration workflow
  - Service management (`systemctl` commands)
- **Status**: Complete

---

## Quick Reference Documentation

### Quick Reference (QUICK_REFERENCE.md) ✅
- One-page reference for common tasks
- API endpoints
- Git commands
- SystemD service management
- Calibration quick steps

### Quick Answers (QUICK_ANSWERS.md) ✅
- FAQ format
- Common questions and answers
- Troubleshooting tips

### Troubleshooting (DEPLOYMENT_TROUBLESHOOTING.md) ✅
- Common issues and solutions
- Sensor failures
- Relay problems
- Network issues
- Database corruption recovery

---

## Code Documentation

### System Architecture (SYSTEM_ARCHITECTURE.md) ✅
- **Purpose**: Software architecture overview
- **Contents**:
  - Module structure
  - Data flow diagrams
  - API endpoint tree
  - Database schema
  - Background processes
  - Control loop descriptions
- **Status**: Complete

### README.md ✅
- **Purpose**: Project overview and API reference
- **Contents**:
  - Feature summary
  - Installation instructions
  - API endpoint reference
  - Configuration (environment variables)
  - Development setup
- **Status**: Complete

### Copilot Instructions (.github/copilot-instructions.md) ✅
- **Purpose**: AI agent guidance for code modifications
- **Contents**:
  - Architecture overview
  - Key endpoint patterns
  - Project conventions (active-low relays, GPIO centralization)
  - Common workflows
  - Guardrails for safe code changes
- **Status**: Complete

---

## Testing Documentation

### Test Coverage
- **171 tests** passing (100% pass rate)
- **Coverage areas**:
  - Controllers (pH, EC, Chiller, Lights, Circulation)
  - Mode system (auto/manual/maintenance)
  - Scheduler (midnight window crossover)
  - Dosing safety (caps, guards, interlocks)
  - Relay system (persistence, E-STOP, cooldowns)
  - Sensors (freshness, staleness, calibration)
  - API endpoints (all major routes)
  - Commissioning automation

### Test Files
- `tests/test_*.py` (171 test functions across 40+ test files)
- All pytest-based with fixtures and mocks
- Run via: `python -m pytest --tb=short -v`

---

## Version Control

### Current State
- **Branch**: main
- **Commit**: Latest (Phase 8 UI standardization complete)
- **Tag**: None yet (pending `v1.0.0-as-built`)

### Pending Actions (Phase 10)
- Tag as `v1.0.0-as-built` after documentation review
- Create GitHub release with notes
- Update CHANGELOG.md with full version history
- Archive development docs to `docs/archive/`

---

## Action Items Before Release

### Required by User
1. **Equipment List**: Provide manufacturer/model/part numbers for all hardware
2. **Operating Philosophy**: Review and validate control strategies match operational intent
3. **Operating Manual**: Add user-specific procedures and preferences
4. **Maintenance Manual**: Define PM intervals based on grow cycle (e.g., every 2 weeks vs. every grow)

### Optional Enhancements
1. **Physical E-STOP**: If hardware button installed, document GPIO wiring and software polling
2. **Sensor Power Control**: If GPIO-controlled sensor power relay installed, document pin and usage
3. **Flow Meters**: If installed, document addresses and integration
4. **Level Switches**: If installed, document GPIO pins and alarm logic

---

## Document Revision History

| Date | Revision | Changes | Author |
|------|----------|---------|--------|
| 2025-11-22 | 1.0 | Initial as-built documentation index created | GitHub Copilot |
| TBD | 1.1 | Equipment list populated with actual part numbers | User |
| TBD | 1.2 | Operating philosophy validated | User |
| TBD | 1.3 | Operating and maintenance manuals expanded | User |
| TBD | 2.0 | Final review and v1.0.0-as-built release | User + Copilot |

---

## Contact & Support

- **GitHub Repository**: https://github.com/collinerasmus/RDWC-v4
- **Issues**: Use GitHub Issues for bug reports and feature requests
- **Discussions**: Use GitHub Discussions for questions and community support

---

**End of As-Built Documentation Index**
