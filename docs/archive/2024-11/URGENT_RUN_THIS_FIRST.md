# ⚠️ URGENT - RUN THIS FIRST ⚠️
**Your system is not responding. Follow these steps IMMEDIATELY.**

## Quick Diagnostic (Run from Windows)

```powershell
# Test if Pi backend is even running
Invoke-RestMethod -Uri "http://192.168.88.49:8080/health" -TimeoutSec 5

# Check E-stop status
Invoke-RestMethod -Uri "http://192.168.88.49:8080/api/estop"

# Check relay status  
Invoke-RestMethod -Uri "http://192.168.88.49:8080/api/relays/status"
```

## If those fail, SSH to Pi and run:

```bash
ssh pi@192.168.88.49

# Once on Pi:
cd ~/RDWC-v4

# 1. Check service status
sudo systemctl status rdwc

# 2. If not running, check why
sudo journalctl -u rdwc -n 50

# 3. Check what branch/commit
git status
git log --oneline -1

# 4. Restart service
sudo systemctl restart rdwc
sudo systemctl status rdwc

# 5. Test locally
curl http://localhost:8080/health
```

## Most Likely Causes:

### 1. Service Not Running
```bash
sudo systemctl start rdwc
```

### 2. E-Stop Engaged
```bash
curl -X POST http://localhost:8080/api/relays/estop/toggle
```

### 3. Changes Not Deployed
```bash
git checkout restore-main-files
git pull origin restore-main-files
sudo systemctl restart rdwc
```

## After You Fix It, Report Back:

Tell me which fix worked, then I'll do the complete cleanup you asked for.
