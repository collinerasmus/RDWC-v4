# MASTER CLEANUP PLAN
**Date:** 2025-11-24
**Status:** Ready to execute after system is operational

## Current Chaos

**Documentation:** 32 MD files (many duplicates/obsolete)
**Tools/Scripts:** 60+ files (many unused, duplicates, or broken)
**Result:** Impossible to find current info, multiple conflicting implementations

## Cleanup Strategy

### Phase 1: Documentation (Keep 8, Archive 24)

**KEEP (Active):**
1. `README.md` - Main entry point
2. `START_HERE.md` - Quick start guide
3. `SYSTEM_ARCHITECTURE.md` - Technical overview
4. `HMI_SETUP_GUIDE.md` - HMI laptop setup
5. `EMERGENCY_DIAGNOSTIC.md` - Troubleshooting
6. `CHANGELOG.md` - Version history
7. `CONTRIBUTING.md` - Development guide
8. `QUICK_REFERENCE.md` - Common commands

**ARCHIVE to `docs/archive/`:**
- All MODE_* files (issue tracking from multiple AIs)
- All COMMISSIONING_* files except one consolidated version
- All STATUS/VERIFICATION/FINALIZATION files (outdated)
- All deployment troubleshooting (consolidate into one)
- Action summaries (historical, not current)

**DELETE (temporary/generated):**
- `commissioning_*.json` files (old reports)
- `commissioning_summary.txt` (old)

### Phase 2: Tools/Scripts Cleanup

**KEEP (Essential):**
```
tools/
  diagnose_pi.sh          # NEW - comprehensive diagnostic
  commission.ps1          # Main commissioning script
  deploy_controllers.ps1  # Deployment script
  README.md               # Tools documentation
  
scripts/
  (evaluate each for current use)
```

**ARCHIVE to `tools/archive/`:**
- All `deploy-*.ps1` variants (multiple versions)
- All `verify-*.ps1` variants (consolidate)
- Old commissioning scripts (outdated)
- Duplicate deployment scripts
- Test scripts no longer used

**CONSOLIDATE:**
- Multiple deployment scripts → ONE master deploy script
- Multiple verify scripts → ONE verify script
- Multiple commissioning helpers → ONE set

### Phase 3: Backend Code Review

**Check for:**
1. Duplicate endpoints (same functionality, different paths)
2. Unused imports
3. Dead code (functions never called)
4. Conflicting mode implementations
5. Multiple ways to do same thing

**Files to audit:**
- `app/main.py` (2000+ lines - likely has duplicates)
- `app/system_mode.py` vs `app/controller_modes.py` (dual systems)
- `app/sensors_mode.py` (third mode system?)
- All controller files (pH, EC, circulation, lights)

### Phase 4: Frontend Code Review

**Check for:**
1. Duplicate mode management code
2. Multiple polling mechanisms for same data
3. Unused functions
4. Conflicting button handlers
5. Dead event listeners

**Files to audit:**
- `app/static/js/relays_v2.js` (mode management)
- `app/static/js/sensors.js` (mode buttons)
- `app/static/js/circulation.js` (hold buttons)
- `app/static/js/ph.js` (hold buttons)
- `app/static/js/ec.js` (hold buttons)

### Phase 5: Unified Mode System

**Current mess:**
- System mode (auto/manual/maintenance)
- Controller mode (auto/hold) with legacy mapping
- Sensor mode (auto/manual/maintenance)
- Frontend: some use mode buttons, some use hold buttons

**Target state:**
- ONE mode concept everywhere
- ONE set of API endpoints
- ONE frontend implementation
- Clear documentation of what it means

## Execution Order

1. **FIRST:** Fix immediate system not responding issue
2. **THEN:** Archive old documentation
3. **THEN:** Consolidate tools/scripts
4. **THEN:** Backend code cleanup
5. **THEN:** Frontend code cleanup
6. **FINALLY:** Unified mode system refactor

## Success Criteria

- ✅ Can find current documentation easily
- ✅ Only ONE way to do each task
- ✅ No conflicting implementations
- ✅ Clear separation: dev machine vs Pi vs HMI
- ✅ System actually works reliably

## Estimated Time

- Documentation cleanup: 30 minutes
- Tools cleanup: 1 hour
- Backend cleanup: 2 hours
- Frontend cleanup: 1 hour  
- Mode system unification: 3 hours
- Testing: 2 hours

**Total: ~10 hours of focused work**

## After Cleanup

**Repository structure:**
```
RDWC-v4/
  README.md
  START_HERE.md
  SYSTEM_ARCHITECTURE.md
  HMI_SETUP_GUIDE.md
  EMERGENCY_DIAGNOSTIC.md
  CHANGELOG.md
  CONTRIBUTING.md
  QUICK_REFERENCE.md
  
  app/
    (clean backend code)
    
  docs/
    archive/
      (all old docs with dates)
    
  tools/
    diagnose_pi.sh
    commission.ps1
    deploy.ps1
    verify.ps1
    README.md
    archive/
      (old tools)
      
  tests/
    (test files)
```

Clean, organized, ONE way to do things.
