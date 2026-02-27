# Enable SMS on Sedi server
# Run: .\deployment\setup_sms_on_server.ps1
# Or with custom key: $env:KAVENEGAR_API_KEY="your-key"; .\deployment\setup_sms_on_server.ps1

$KEY = $env:KAVENEGAR_API_KEY
if (-not $KEY) {
    Write-Host "Error: Set KAVENEGAR_API_KEY first. Example: `$env:KAVENEGAR_API_KEY='your-key'; .\deployment\setup_sms_on_server.ps1"
    exit 1
}
$SERVER = "root@91.107.168.130"
$REMOTE_ENV = "/var/www/sedi/backend/.env"

# Update .env and restart
$escapedKey = $KEY -replace "'", "''"
$script = @"
cd /var/www/sedi/backend
test -f .env || touch .env
sed -i '/^KAVENEGAR_API_KEY=/d' .env
sed -i '/^SMS_DISABLED=/d' .env
echo 'KAVENEGAR_API_KEY=$escapedKey' >> .env
echo 'SMS_DISABLED=false' >> .env
systemctl restart sedi-backend
echo 'SMS enabled successfully.'
"@

Write-Host "Connecting to server and enabling SMS..."
ssh $SERVER $script
