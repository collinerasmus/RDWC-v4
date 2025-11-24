# HMI Laptop Setup Guide
**Date:** 2025-11-24
**Purpose:** Dedicated touchscreen HMI for RDWC-v4 system

## Why This Approach

**Benefits:**
- Single point of control - no confusion about which browser/machine
- Always connected to the system
- Touchscreen for easy operation during commissioning
- ChromeOS is perfect - lightweight, secure, browser-based
- Separates development (Windows machine) from operation (HMI)

## Network Setup

### Option 1: DHCP Reservation (RECOMMENDED)
1. Find laptop MAC address: Settings → Network → Advanced
2. Log into your router admin
3. Create DHCP reservation for laptop MAC → assign specific IP (e.g., 192.168.1.50)
4. Laptop still gets DNS/gateway automatically
5. IP stays consistent across reboots

### Option 2: Static IP
If DHCP reservation not available:
1. ChromeOS: Settings → Network → [Your Network] → Network
2. IP Configuration: Manual
3. Set: IP, Subnet, Gateway, DNS
4. Example:
   - IP: 192.168.1.50
   - Subnet: 255.255.255.0
   - Gateway: 192.168.1.1 (your router)
   - DNS: 192.168.1.1 or 8.8.8.8

## Pi IP Address

Find your Raspberry Pi IP:
\\\ash
# On Pi via SSH
hostname -I

# Or from Windows
ping raspberrypi.local
\\\

Make note of it: _________________

## Browser Setup

1. **Open Chrome browser** on ChromeOS laptop

2. **Navigate to:** \http://[pi-ip]:8080\
   - Example: \http://192.168.1.100:8080\
   - Or if mDNS works: \http://raspberrypi.local:8080\

3. **Bookmark it:**
   - Press Ctrl+D
   - Name: "RDWC System"
   - Save to bookmarks bar

4. **Make it easy to access:**
   - Pin Chrome to taskbar/shelf
   - Set bookmark to open on startup (Chrome Settings → On startup → Open specific pages)

5. **Optional - Kiosk mode:**
   - For dedicated HMI feel
   - Press F11 for fullscreen
   - Or create Chrome app shortcut

## Testing Connection

1. Open \http://[pi-ip]:8080\ on HMI laptop
2. Should see RDWC dashboard
3. Click through tabs: Overview, Sensors, pH, EC, etc.
4. Test mode switching: Manual → Auto

**If connection fails:**
- Ping Pi from laptop: Open Terminal, \ping [pi-ip]\
- Check Pi is running: SSH from Windows, \sudo systemctl status rdwc\
- Check firewall on Pi: \sudo ufw status\

## Usage Guidelines

### On HMI Laptop (ChromeOS):
✅ **Use for:** 
- Daily monitoring
- Commissioning
- Calibration
- Mode changes
- Viewing sensor data
- Operating the system

### On Windows Development Machine:
✅ **Use for:**
- Code changes
- Git commits  
- Testing new features
- Deployment to Pi
- Development work

❌ **DON'T use Windows for daily operation** - that's what the HMI is for!

## Touchscreen Tips

ChromeOS touchscreen works great with the UI:
- Tap buttons to toggle relays
- Swipe to scroll sensor history
- Pinch to zoom graphs (if implemented)
- Long-press for tooltips (if browser supports)

## Troubleshooting

### Can't reach Pi from laptop:
1. Check both on same network/VLAN
2. Ping test: \ping [pi-ip]\
3. Check Pi service: \ssh pi@[pi-ip]\ then \sudo systemctl status rdwc\

### UI loads but looks broken:
1. Hard refresh: Ctrl+Shift+R
2. Clear cache: Chrome Settings → Privacy → Clear browsing data
3. Check browser console (Ctrl+Shift+J) for errors

### Mode buttons don't work:
1. Check backend is running: \sudo systemctl status rdwc\
2. Check backend logs: \sudo journalctl -u rdwc -n 50\
3. Verify network connection is stable

### Touchscreen not working:
1. ChromeOS Settings → Device → Touchscreen → Enable
2. Calibrate if needed
3. Check for OS updates

## Security Notes

- HMI connects to Pi on local network only
- No internet access required for operation
- Pi should have firewall (ufw) limiting access to port 8080
- Consider VPN if accessing remotely

## Maintenance

- Keep ChromeOS updated
- Bookmark updates if Pi IP changes
- Clear browser cache monthly
- Monitor for slow performance

## Next Steps After Setup

1. Test mode switching works on HMI
2. Go through commissioning on HMI
3. Bookmark commonly used tabs
4. Get comfortable with touchscreen interface
5. Use Windows only for development

---
**This creates a clean separation: HMI for operation, Windows for development.**
