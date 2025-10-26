param([string]$PiHost="192.168.88.49",[string]$PiUser="pi",[int]$Port=22,[int]$Baud=100000)
function SSH($c){ ssh -p $Port "$PiUser@$PiHost" $c }
Write-Host "Adding $PiUser to i2c group and setting i2c baudrate=$Baud ..."
SSH @"
set -e
sudo adduser $PiUser i2c || true
sudo grep -q 'i2c_arm=on' /boot/config.txt || echo 'dtparam=i2c_arm=on' | sudo tee -a /boot/config.txt
sudo sed -i 's/^dtparam=i2c_arm_baudrate=.*/dtparam=i2c_arm_baudrate=$Baud/' /etc/rc.local 2>/dev/null || true
sudo grep -q 'i2c_arm_baudrate' /boot/config.txt && sudo sed -i 's/dtparam=i2c_arm_baudrate=.*/dtparam=i2c_arm_baudrate=$Baud/' /boot/config.txt || echo 'dtparam=i2c_arm_baudrate=$Baud' | sudo tee -a /boot/config.txt
"@
Write-Host "I2C sanity applied. Rebooting ..."
SSH "sudo reboot"