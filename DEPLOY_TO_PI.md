# Deploy HMI Rebuild to Raspberry Pi

## Quick Deployment Command

Run this command to deploy the HMI rebuild to your Pi:

```bash
ssh pi@192.168.88.49 "cd ~/rdwc-v4 && git fetch origin && git reset --hard origin/copilot/hmi-rebuild-clean-slate && sudo systemctl restart rdwc && sudo systemctl restart rdwc-sensors"
```

**Note**: Adjust `~/rdwc-v4` if your repository is in a different location.

## What This Does

1. **SSHs to Pi** at 192.168.88.49
2. **Fetches latest code** from GitHub
3. **Force-replaces local code** with branch `copilot/hmi-rebuild-clean-slate` (discards any local changes)
4. **Restarts services**:
   - `rdwc` - Main FastAPI application
   - `rdwc-sensors` - Sensor polling service

## Deployment Verification

After deployment, verify the following:

### 1. Check Services are Running
```bash
ssh pi@192.168.88.49 "sudo systemctl status rdwc rdwc-sensors"
```

### 2. Open HMI in Browser
```
http://192.168.88.49:8080
```

### 3. Verify EC Display
- **KPIs (top of page)**: EC should show correct mS/cm value (e.g., "0.42" not "424")
- **Sensors Graph**: EC line should display correct values
- **EC Tab**: Current EC should show correct mS/cm value
- **EC Chart**: Should have data points (if any doses have occurred)

### 4. Check Browser Console
Open browser DevTools (F12) → Console tab

Look for:
- ✅ No errors
- ✅ Warning messages if µS/cm conversion occurred: `[Sensors] EC value > 20, assuming µS/cm and converting to mS/cm: 424`
- ✅ Confirmation: `[Sensors] Set EC to: 0.42`

### 5. Visual Verification
- ✅ All sections permanently expanded (no collapsible arrows)
- ✅ Dark theme with green/blue accents
- ✅ All 10 tabs present and functional
- ✅ Charts render correctly

## Rollback (If Needed)

If issues occur, rollback to previous working state:

```bash
ssh pi@192.168.88.49 "cd ~/rdwc-v4 && git fetch origin && git reset --hard origin/copilot/clean-ec-page-style && sudo systemctl restart rdwc && sudo systemctl restart rdwc-sensors"
```

**Note**: Replace `copilot/clean-ec-page-style` with whatever branch was working before.

## Changes in This Release

### 1. HMI Cleanup (Primary Goal)
- ✅ Removed all 27 collapsible `<details>` elements
- ✅ All sections permanently visible
- ✅ Extracted 636 lines of inline CSS to `theme_v4.css`
- ✅ Extracted 181 lines of inline JS to `ui_core.js`
- ✅ HTML reduced from 3,105 to 2,277 lines (26.6% reduction)
- ✅ Fixed HTML structure (544/544 div balance)
- ✅ Removed invalid attributes

### 2. EC Unit Fix (Critical Bug Fix)
- ✅ Fixed EC values displaying as µS/cm instead of mS/cm
- ✅ Added safety conversion in 9 locations (complete coverage):
  - sensors.js: KPI display, override panel, recent readings, direct fetch fallback (4 locations)
  - ec.js: status display, delta calculation, calibration display (3 locations)
  - ec_chart.js: current EC annotation (1 location)
  - trends.js: removed incorrect autodetect logic (1 location)
- ✅ All conversions log warnings for debugging

### 3. Code Quality
- ✅ Zero duplicate code
- ✅ Proper separation of concerns (HTML, CSS, JS)
- ✅ Clean validated structure
- ✅ Dark theme maintained

## Testing Checklist

Before approving for production:

- [ ] EC KPIs show correct mS/cm values (0.x range, not 100+ range)
- [ ] Sensor graph displays EC correctly
- [ ] EC chart has data (if doses occurred)
- [ ] All 10 tabs load without errors
- [ ] All sections visible (no collapsibles)
- [ ] No console errors
- [ ] pH/EC controllers work
- [ ] Manual dose buttons work
- [ ] Schedule displays correctly
- [ ] Camera feed works (if enabled)
- [ ] Settings save correctly
- [ ] Calibration workflows complete

## 24-Hour Soak Test

After initial verification:

1. **Monitor for 24 hours**
2. **Check for**:
   - Memory leaks (browser memory usage)
   - Console errors
   - Data accuracy (EC, pH, temperature)
   - Chart updates
   - Controller automation
3. **Log any issues** with timestamps and console output

## Support

If issues arise:
1. Check browser console for errors
2. Check Pi logs: `ssh pi@192.168.88.49 "sudo journalctl -u rdwc -n 100"`
3. Check sensor logs: `ssh pi@192.168.88.49 "sudo journalctl -u rdwc-sensors -n 100"`
4. Report issues with:
   - Screenshots
   - Console output
   - Log excerpts
   - Steps to reproduce

## Commit History

This deployment includes commits:
- `68c0e8c` - Extract inline CSS and create ui_core.js
- `95da07b` - Remove all 27 collapsibles
- `ab49204` - Remove duplicate inline code
- `892f195` - Fix HTML structure
- `0d6039c` - Add validation report
- `3f423b2` - Add deployment readiness report
- `08972ba` - Fix EC unit display issue

Total: 7 commits, 827 lines removed, structure validated, EC bug fixed.
