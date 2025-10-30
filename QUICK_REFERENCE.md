# RDWC v4 - Quick Reference Card

## 🌐 Web Dashboard
**URL:** http://192.168.88.49:8080

**If buttons don't work:**
1. Hard refresh: `Ctrl + Shift + R` (Windows) or `Cmd + Shift + R` (Mac)
2. Check browser console for errors (F12)

---

## 🚨 Emergency Commands

### Force All Relays OFF
```bash
curl -X POST http://192.168.88.49:8080/relay/emergency_off
```

### Restart Service
```bash
ssh pi@192.168.88.49 "sudo systemctl restart rdwc.service"
```

### Check Service Status
```bash
ssh pi@192.168.88.49 "sudo systemctl status rdwc.service"
```

---

## 🔧 Relay Control (Manual)

### Toggle Relay ON
```bash
curl 'http://192.168.88.49:8080/relay/set?name=lights&on=1'
```

### Toggle Relay OFF
```bash
curl 'http://192.168.88.49:8080/relay/set?name=lights&on=0'
```

### Valid Relay Names:
- `lights`
- `main_pump`
- `chiller_pump`
- `chiller_power`
- `dosing_grow`
- `dosing_micro`
- `dosing_bloom`
- `dosing_ph_up`

---

## 📊 Monitoring Commands

### Check All Relay States
```bash
curl -s http://192.168.88.49:8080/relay/status
```

### Check Debug Info (antiflap, cooldowns, change counts)
```bash
curl -s http://192.168.88.49:8080/relay/debug
```

### Check Recent Toggle Attempts (last 50)
```bash
curl -s http://192.168.88.49:8080/debug/relay_requests
```

### Check System Health
```bash
curl -s http://192.168.88.49:8080/health
```

---

## ⚙️ Cooldown Times

| Relay | Min ON Time | Min OFF Time | Purpose |
|-------|-------------|--------------|---------|
| chiller_power | 5 minutes | 5 minutes | Prevent compressor damage |
| chiller_pump | 2 minutes | 2 minutes | Prevent pump short-cycling |
| main_pump | 1 minute | 30 seconds | Protect pump motor |
| lights | 30 seconds | 10 seconds | Reduce stress on ballast |
| dosing_* | None | None | Instant response needed |

---

## 🛡️ Safety Features

### Anti-Flap Protection
- Triggers after **15 changes in 5 minutes**
- Blocks non-forced changes for **2 minutes**
- Cleared automatically or via emergency endpoint

### Lights Whitelist
Only approved operations can control lights:
- ✅ Manual override (`override`)
- ✅ Scheduler (`schedule_on`, `schedule_off`)
- ✅ Emergency shutdown (`emergency`)
- ❌ Unapproved automation (blocked + logged)

---

## 📝 Deployment

```bash
# Local machine
git add .
git commit -m "your changes"
git push

# Deploy to Pi
ssh pi@192.168.88.49 "cd ~/RDWC-v4 && git pull && sudo systemctl restart rdwc.service"

# Wait for startup (8 seconds)
sleep 8

# Verify
curl http://192.168.88.49:8080/health
```

---

## 🐛 Troubleshooting

### Problem: Relays won't toggle
**Check:** Cooldown or antiflap protection active
```bash
curl -s http://192.168.88.49:8080/relay/debug
```

### Problem: UI buttons don't respond
**Solution:** Hard refresh browser (`Ctrl+Shift+R`)

### Problem: Dosing pumps stuck ON
**Solution:** Emergency off
```bash
curl -X POST http://192.168.88.49:8080/relay/emergency_off
```

### Problem: Service keeps restarting
**Check:** Logs for errors
```bash
ssh pi@192.168.88.49 "sudo journalctl -u rdwc.service -n 50 --no-pager"
```

---

## 📍 Important Files

| File | Purpose |
|------|---------|
| `app/main.py` | API endpoints |
| `app/relays_core.py` | Relay control logic |
| `app/debug.py` | Debug router |
| `app/static/index.html` | Web dashboard |
| `/etc/systemd/system/rdwc.service` | Service configuration |
| `PRODUCTION_STATUS.md` | Full documentation |

---

## ✅ System Status
**Last Verified:** October 30, 2025  
**Status:** ✅ OPERATIONAL  
**Uptime:** Stable (no crashes)  
**All 8 Relays:** Working  
**Web UI:** Operational
