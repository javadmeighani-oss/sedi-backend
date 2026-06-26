# Enable Mediana OTP SMS on Sedi production server (Docker Compose).
# Run:
#   $env:SEDI_SSH_HOST = "root@your-server"
#   $env:SEDI_DEPLOY_PATH = "/opt/sedi"
#   $env:MEDIANA_API_KEY = "your-key"
#   $env:MEDIANA_OTP_PATTERN_CODE = "your-pattern-code"
#   .\deployment\setup_sms_on_server.ps1

$ApiKey = $env:MEDIANA_API_KEY
$PatternCode = $env:MEDIANA_OTP_PATTERN_CODE
$Server = $env:SEDI_SSH_HOST
$DeployPath = if ($env:SEDI_DEPLOY_PATH) { $env:SEDI_DEPLOY_PATH } else { "/opt/sedi" }
$RemoteEnv = "/etc/sedi/sedi-backend.env"
$ImageTag = $env:SEDI_IMAGE_TAG

if (-not $ApiKey) {
    Write-Host "Error: Set MEDIANA_API_KEY first."
    exit 1
}
if (-not $PatternCode) {
    Write-Host "Error: Set MEDIANA_OTP_PATTERN_CODE first."
    exit 1
}
if (-not $Server) {
    Write-Host "Error: Set SEDI_SSH_HOST first (e.g. root@your-server)."
    exit 1
}

$escapedKey = $ApiKey -replace "'", "''"
$escapedPattern = $PatternCode -replace "'", "''"
$tagExport = if ($ImageTag) { "export SEDI_IMAGE_TAG='$ImageTag';" } else { "" }

$script = @"
set -e
sudo test -f $RemoteEnv || sudo touch $RemoteEnv
sudo sed -i '/^SMS_DISABLED=/d' $RemoteEnv
sudo sed -i '/^SMS_PROVIDER=/d' $RemoteEnv
sudo sed -i '/^MEDIANA_API_KEY=/d' $RemoteEnv
sudo sed -i '/^MEDIANA_OTP_PATTERN_CODE=/d' $RemoteEnv
sudo sed -i '/^KAVENEGAR_API_KEY=/d' $RemoteEnv
sudo sed -i '/^KAVENEGAR_SENDER=/d' $RemoteEnv
echo 'SMS_DISABLED=false' | sudo tee -a $RemoteEnv > /dev/null
echo 'SMS_PROVIDER=mediana' | sudo tee -a $RemoteEnv > /dev/null
echo 'MEDIANA_API_KEY=$escapedKey' | sudo tee -a $RemoteEnv > /dev/null
echo 'MEDIANA_OTP_PATTERN_CODE=$escapedPattern' | sudo tee -a $RemoteEnv > /dev/null
cd $DeployPath
$tagExport
docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
echo 'Mediana SMS env updated and sedi-backend recreated.'
"@

Write-Host "Connecting to server and enabling Mediana OTP SMS..."
ssh $Server $script
