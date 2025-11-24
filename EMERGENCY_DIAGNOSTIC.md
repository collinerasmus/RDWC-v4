# EMERGENCY FIXES APPLIED - 2025-11-24

## What Was Broken

The system had **4 competing mode management systems**:
1. `controller_modes.py` - Used by pH/EC, expecting "auto"/"hold"
2. `system_mode.py` - Used by relays, using "auto"/"manual"/"maintenance"  
3. `unified_mode.py` - Intended single source, but NOT CONNECTED
4. `sensors_mode.py` - Separate sensor mode (unnecessary)

**Result**: UI mode buttons changed `system_mode`, but pH/EC checked `controller_modes` → mode changes never propagated!

## What Was Fixed

### 1. Unified Mode System
- **KEPT**: `app/unified_mode.py` as THE ONLY mode system
- **ARCHIVED** (not deleted yet): Other mode files will be removed after testing
- **Standardized**: All controllers now use ONE mode source

### 2. Updated All Imports
- `app/main.py`: All mode imports now use `unified_mode`
- `app/ph_control.py`: Changed from `controller_modes` to `unified_mode`
- `app/ec_control.py`: Changed from `controller_modes` to `unified_mode`

### 3. Fixed Function Calls
- Changed `get_mode("ph")` → `get_controller_mode("ph")` in pH controller
- Changed `get_mode("ec")` → `get_controller_mode("ec")` in EC controller

### 4. Backward Compatibility
- `get_controller_mode()` maps "manual"/"maintenance" → "hold" for legacy code
- `set_controller_mode()` maps "hold" → "manual" for legacy callers
- All old endpoints still work, they just route through unified system

## Mode Mapping

| UI/API Mode | Internal Mode | pH/EC Sees | Behavior |
|-------------|---------------|------------|----------|
| AUTO | auto | auto | ✅ Automation runs |
| MANUAL | manual | hold | ⏸️ Automation paused |
| MAINTENANCE | maintenance | hold | ⏸️ Automation paused + safety bypass |

## Testing Required

1. **Mode Change Propagation**:
   - Click "MANUAL" in header → All "Resume" buttons should appear
   - Click "AUTO" in header → All "Hold" buttons should appear
   - Click individual "Hold" → Only that controller pauses

2. **Relay Buttons**: 
   - System tab GPIO buttons should work in any mode
   - Protected relays (lights/chiller) need whitelisted reasons

3. **Browser Stability**:
   - Connection state should not cycle (Initializing → Live → Ready → Live)
   - Camera feed should be stable
   - Hard refresh (Ctrl+Shift+R) should load new code

## Files Modified

```
app/unified_mode.py          ✅ Enhanced with all compatibility functions
app/main.py                  ✅ All imports updated to unified_mode
app/ph_control.py            ✅ Import and function calls updated
app/ec_control.py            ✅ Import and function calls updated
```

## Files to Remove (After Testing)

```
app/controller_modes.py      ❌ OBSOLETE - remove after verification
app/system_mode.py           ❌ OBSOLETE - remove after verification
app/sensors_mode.py          ❌ OBSOLETE - remove after verification
```

## Deployment Steps

1. **On Windows Dev Machine** (YOU):
   ```
   git status  # Review changes
   git add app/unified_mode.py app/main.py app/ph_control.py app/ec_control.py
   git commit -m "fix: unify mode system - single source of truth"
   ```

2. **On Raspberry Pi**:
   ```bash
   cd /home/pi/rdwc-v4
   git pull
   sudo systemctl restart rdwc-api
   sudo systemctl restart rdwc-sensors
   ```

3. **Verify on HMI** (192.168.88.33):
   - Hard refresh browser (Ctrl+Shift+F5)
   - Click MANUAL button in header
   - Check ALL tabs show "Resume" buttons
   - Click AUTO button
   - Check ALL tabs show "Hold" buttons
   - Test relay buttons in System tab

## If Something Breaks

**Rollback**:
```bash
cd /home/pi/rdwc-v4
git log --oneline -n 5   # Find commit before changes
git reset --hard <commit-hash>
sudo systemctl restart rdwc-api
sudo systemctl restart rdwc-sensors
```

## Next Issues to Address

1. **Browser Connection Cycling**: Multiple polling systems running
2. **Relay Button Handlers**: System tab buttons not wired up
3. **Cache Busting**: JS files need version query parameters
4. **Documentation Cleanup**: Too many outdated/conflicting docs

## Status

✅ CORE FIX COMPLETE - Mode system is now unified
⏳ TESTING REQUIRED - Deploy and verify on actual Pi
📋 FOLLOW-UP WORK - Browser stability, relay buttons, cache

---

**CRITICAL**: Do NOT delete the old mode files until you've confirmed the system works on the Pi!
