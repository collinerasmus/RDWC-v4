param([string]$PiHost="192.168.88.49",[string]$PiUser="pi",[int]$Port=22)
function SSH($c){ ssh -p $Port "$PiUser@$PiHost" $c }
Write-Host "Restarting RDWC and verifying..."
SSH "sudo systemctl restart rdwc.service && sleep 2"
Write-Host "`n/status:"; SSH "curl -s http://127.0.0.1:8080/status"
Write-Host "`n/read_now:"; SSH "curl -s http://127.0.0.1:8080/read_now"
Write-Host "`n/fix_ezo:"; SSH "curl -s http://127.0.0.1:8080/fix_ezo"
Write-Host "`n/cam_status:"; SSH "curl -s http://127.0.0.1:8080/cam_status"