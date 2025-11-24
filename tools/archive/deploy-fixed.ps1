# ===================== tools/deploy.ps1 =====================
param(
  [string]$PiHost = "192.168.88.49",
  [string]$PiUser = "pi",
  [string]$GitRepo = "https://github.com/collinerasmus/RDWC-v4.git",
  [int]$Port = 22
)

$ErrorActionPreference = "Stop"

function Invoke-SSH {
  param([string]$Cmd)
  & ssh -p $Port "$PiUser@$PiHost" $Cmd
}

function Copy-FromPi {
  param([string]$Remote, [string]$Local = ".")
  & scp -P $Port "${PiUser}@${PiHost}:$Remote" $Local
}

Write-Host "=== RDWC-v4: Start deploy to $PiUser@$PiHost ==="

# 0) Ensure OpenSSH exists
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { 
  throw "OpenSSH client not found on this PC." 
}

# 1) Stop any rdwc services if present and back up any RDWC folders
Write-Host "— Stopping any rdwc*.service and backing up RDWC folders (if any)…"
$cmd1 = 'set -e; cd ~; for s in $(systemctl list-unit-files | awk '\''/^rdwc.*\.service/ {print $1}'\''); do sudo systemctl stop "$s" || true; done; STAMP=$(date +%Y%m%d_%H%M%S); RDWC_DIRS=$(ls -d RDWC* rdwc* 2>/dev/null || true); if [ -n "$RDWC_DIRS" ]; then tar -czf "RDWC-backup_${STAMP}.tar.gz" $RDWC_DIRS; echo "BACKUP=RDWC-backup_${STAMP}.tar.gz"; else echo "BACKUP="; fi'
Invoke-SSH $cmd1

# 2) Pull backup tarball to this PC if it exists
Write-Host "— Pulling backup tarball (if created)…"
try {
  Copy-FromPi "~/RDWC-backup_*.tar.gz" "."
} catch {
  Write-Host "No RDWC backup tarball to copy (that's fine)."
}

# 3) Remove old projects and unit files; prep OS + I2C; reboot
Write-Host "— Cleaning old RDWC trees, removing unit files, installing deps, enabling I2C…"
$cmd3 = 'set -e; cd ~; rm -rf ~/RDWC-v3 ~/RDWC-v2 ~/RDWC-v1 ~/RDWC ~/rdwc ~/RDWC.v3 || true; for f in /etc/systemd/system/rdwc*.service; do [ -e "$f" ] && sudo rm "$f"; done; sudo systemctl daemon-reload; sudo apt-get update -y; sudo apt-get install -y i2c-tools python3-venv python3-pip; sudo raspi-config nonint do_i2c 0; sudo reboot'
Invoke-SSH $cmd3

# 4) Wait for Pi to come back online (SSH)
Write-Host "— Waiting for Pi to reboot and SSH to become ready…"
Start-Sleep -Seconds 8
$maxTries = 60
for ($i=1; $i -le $maxTries; $i++) {
  try {
    Invoke-SSH "echo OK" | Out-Null
    Write-Host "SSH is back."
    break
  } catch {
    Start-Sleep -Seconds 2
    if ($i -eq $maxTries) { 
      throw "Pi did not come back on SSH in time." 
    }
  }
}

# 5) Verify I2C addresses
Write-Host "— Verifying I2C devices (expect 0x63, 0x64, 0x66)…"
Invoke-SSH "i2cdetect -y 1"

# 6) Fresh clone + venv + requirements + .env + systemd
Write-Host "— Deploying RDWC-v4 fresh…"
$cmd6 = "set -e; cd ~; rm -rf RDWC-v4; git clone $GitRepo; cd RDWC-v4; python3 -m venv .venv; source .venv/bin/activate; pip install --upgrade pip; pip install -r requirements.txt; cp .env.example .env; sed -i 's/^ENV=.*/ENV=prod/' .env; sed -i 's/^HOST=.*/HOST=0.0.0.0/' .env; sed -i 's/^PORT=.*/PORT=8080/' .env; sudo cp systemd/rdwc.service /etc/systemd/system/rdwc.service; sudo systemctl daemon-reload; sudo systemctl enable rdwc.service; sudo systemctl start rdwc.service; sudo systemctl status rdwc.service --no-pager -l"
Invoke-SSH $cmd6

# 7) Hit the status endpoint from the Pi (curl), then from this PC
Write-Host "— Testing API on the Pi…"
$cmd7 = 'curl -s http://localhost:8080/status || true'
Invoke-SSH $cmd7

Write-Host "=== RDWC-v4: Deploy complete. Open http://$PiHost:8080/status in your browser. ==="
# =================== end tools/deploy.ps1 ===================