# Sedi Backend Restart Script for PowerShell
# Run this script to restart the backend service on the cloud server

Write-Host "🚀 Connecting to Sedi Backend Server..." -ForegroundColor Cyan

# SSH connection and commands
$commands = @"
cd /var/www/sedi/backend
echo '📥 Pulling latest changes...'
git pull
echo ''
echo '🔄 Restarting service...'
systemctl restart sedi-backend
sleep 3
echo ''
echo '✅ Service status:'
systemctl status sedi-backend --no-pager | head -15
echo ''
echo '📋 Recent logs (last 20 lines):'
journalctl -u sedi-backend -n 20 --no-pager | tail -20
echo ''
echo '🧪 Testing API endpoint...'
curl -s http://localhost:8000/ | python3 -m json.tool || echo 'API test failed'
"@

# Execute commands via SSH
ssh root@91.107.168.130 $commands

Write-Host "`n✅ Backend restart completed!" -ForegroundColor Green

