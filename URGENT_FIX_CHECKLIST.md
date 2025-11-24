# URGENT FIX CHECKLIST
**Date:** 2024-11-24  
**Status:** IN PROGRESS

## What We Just Fixed

✅ **1. Unified Mode System** - Created single source of truth for modes  
✅ **2. Updated Main.py** - All mode endpoints use unified_mode  
✅ **3. Fixed Chiller** - Now uses unified_mode system  
✅ **4. Comprehensive Audit** - Found ALL duplicate systems  

## Current Status

**Working:**
- pH Hold button ✓
- EC Hold button ✓
- Circulation Hold button ✓
- Lights Hold button ✓
- Chiller Hold button ✓ (after deploy)

**Still Broken:**
- ❌ System Tab GPIO buttons (emergency backup control)
- ❌ Browser reloading/going offline (29 polling loops)

## Deploy NOW to Test Chiller Fix

```bash
ssh pi@192.168.88.49
cd ~/RDWC-v4
git pull origin restore-main-files
sudo systemctl restart rdwc
sleep 5
curl http://localhost:8080/api/system_mode
curl http://localhost:8080/api/controller/chiller/mode
exit
```

Then test on HMI:
1. Clear browser cache completely
2. Re-open browser to http://192.168.88.49:8080
3. Click "Manual" button
4. Check Chiller tab - Hold button should activate

## Next Critical Fixes (After Testing)

### CRITICAL #1: Fix System Tab GPIO Buttons
**Problem:** GPIO buttons don't work (emergency backup control)  
**Solution:** Update system.js to use correct relay API  
**Time:** 15 minutes

### CRITICAL #2: Fix Browser Chaos
**Problem:** 29 concurrent polling loops causing reload/offline  
**Solution:** Create polling_manager.js for coordinated updates  
**Time:** 1 hour

### CRITICAL #3: Database Access
**Problem:** 17 files opening DB directly, no coordination  
**Solution:** Create db.py module, single access point  
**Time:** 2 hours

## Success Criteria

✅ All Hold buttons work (Manual mode syncs)  
✅ GPIO buttons always work (emergency backup)  
✅ Browser stays stable (no reload loops)  
✅ System stays online (coordinated polling)  

## Files That Will Be Fixed Next

1. `app/static/js/system.js` - GPIO buttons
2. `app/static/js/polling_manager.js` - NEW FILE
3. `app/db.py` - NEW FILE (database access)
4. All JS files - Update to use polling_manager

## Testing Protocol

After each fix:
1. Clear HMI browser cache
2. Test all tabs
3. Watch browser console for errors
4. Monitor for 5 minutes (stability check)

## Communication

**To User:**  
"Deploy the chiller fix now. If chiller Hold button works after deploy + cache clear, we're on track. Then I'll fix the GPIO buttons (15min) and polling chaos (1hr). Your observation that browser reload/offline is from the 29 concurrent polling loops was exactly right."
