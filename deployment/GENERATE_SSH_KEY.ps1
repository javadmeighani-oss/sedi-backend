# Generate SSH Key for GitHub Actions - PowerShell Script

Write-Host "🔑 Generating SSH Key for GitHub Actions..." -ForegroundColor Cyan

# Navigate to backend directory
$backendPath = "D:\Rimiya Design Studio\Sedi\software\Demo\backend"
Set-Location $backendPath

# Check if key already exists
if (Test-Path ".github_actions_key") {
    Write-Host "⚠️  SSH key already exists!" -ForegroundColor Yellow
    $overwrite = Read-Host "Do you want to overwrite? (y/n)"
    if ($overwrite -ne "y") {
        Write-Host "Cancelled." -ForegroundColor Red
        exit
    }
    Remove-Item ".github_actions_key" -Force -ErrorAction SilentlyContinue
    Remove-Item ".github_actions_key.pub" -Force -ErrorAction SilentlyContinue
}

# Generate SSH key using OpenSSH (Windows 10+)
Write-Host "📝 Generating new SSH key..." -ForegroundColor Green
ssh-keygen -t ed25519 -C "github-actions-sedi-backend" -f ".github_actions_key" -N '""'

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ SSH key generated successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host "📋 PUBLIC KEY (Copy this for Step 2):" -ForegroundColor Yellow
    Write-Host "=" * 60 -ForegroundColor Cyan
    Get-Content ".github_actions_key.pub"
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host ""
    Write-Host "📝 Next steps:" -ForegroundColor Green
    Write-Host "1. Copy the PUBLIC KEY above" -ForegroundColor White
    Write-Host "2. Add it to server: ~/.ssh/authorized_keys" -ForegroundColor White
    Write-Host "3. Get PRIVATE KEY for GitHub Secrets:" -ForegroundColor White
    Write-Host "   Get-Content .github_actions_key" -ForegroundColor Gray
} else {
    Write-Host "❌ Failed to generate SSH key!" -ForegroundColor Red
    Write-Host "Make sure OpenSSH is installed on Windows." -ForegroundColor Yellow
}

