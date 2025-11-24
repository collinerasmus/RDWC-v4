param([string]$PiHost="192.168.88.49",[string]$PiUser="pi",[string]$Repo="https://github.com/collinerasmus/RDWC-v4.git",[int]$Port=22)
function SSH($c){ ssh -p $Port "$PiUser@$PiHost" $c }

# Commit and push any changes
git add -A
git commit -m "fix: add Atlas fixer + stable USB camera service + diagnostics" --allow-empty
git branch -M main
git remote remove origin 2>$null; git remote add origin $Repo 2>$null
git push -u origin main

# Pull and restart service
SSH @"
set -e
cd ~/RDWC-v4 || git clone $Repo ~/RDWC-v4 && cd ~/RDWC-v4
git fetch --all
git reset --hard origin/main
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
sudo systemctl restart rdwc.service
"@

# Quick checks
Write-Host "`n/status:"
SSH "curl -s http://127.0.0.1:8080/status"
Write-Host "`n/fix_ezo:"
SSH "curl -s -X POST http://127.0.0.1:8080/fix_ezo"
Write-Host "`n/diag:"
SSH "curl -s http://127.0.0.1:8080/diag | head -c 2000"
Write-Host "`nCamera HEAD:"
SSH "curl -s -I http://127.0.0.1:8081/?action=stream | head -n 1"