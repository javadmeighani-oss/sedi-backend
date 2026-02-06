# Verify SSH Key Format for GitHub Actions
# Run this before adding to GitHub Secrets

Write-Host "🔍 Verifying SSH Key Format..." -ForegroundColor Cyan
Write-Host ""

$keyPath = ".github_actions_key"

if (-not (Test-Path $keyPath)) {
    Write-Host "❌ SSH key not found: $keyPath" -ForegroundColor Red
    Write-Host "Generate it first using: ssh-keygen -t ed25519 -C 'github-actions-sedi' -f '.github_actions_key' -N ''" -ForegroundColor Yellow
    exit 1
}

Write-Host "📋 Checking key format..." -ForegroundColor Green
Write-Host ""

# Read key content
$keyContent = Get-Content $keyPath -Raw

# Check 1: Has BEGIN header
if ($keyContent -match "-----BEGIN OPENSSH PRIVATE KEY-----") {
    Write-Host "✅ Has BEGIN header" -ForegroundColor Green
} else {
    Write-Host "❌ Missing BEGIN header" -ForegroundColor Red
    Write-Host "   Key should start with: -----BEGIN OPENSSH PRIVATE KEY-----" -ForegroundColor Yellow
}

# Check 2: Has END header
if ($keyContent -match "-----END OPENSSH PRIVATE KEY-----") {
    Write-Host "✅ Has END header" -ForegroundColor Green
} else {
    Write-Host "❌ Missing END header" -ForegroundColor Red
    Write-Host "   Key should end with: -----END OPENSSH PRIVATE KEY-----" -ForegroundColor Yellow
}

# Check 3: Not encrypted (no passphrase)
if ($keyContent -match "Proc-Type: 4,ENCRYPTED") {
    Write-Host "❌ Key is ENCRYPTED (has passphrase)" -ForegroundColor Red
    Write-Host "   Regenerate key with: ssh-keygen -t ed25519 -f '.github_actions_key' -N ''" -ForegroundColor Yellow
} else {
    Write-Host "✅ Key is NOT encrypted (no passphrase)" -ForegroundColor Green
}

# Check 4: Line endings
$hasCRLF = $keyContent -match "`r`n"
if ($hasCRLF) {
    Write-Host "⚠️  Key has CRLF line endings (Windows format)" -ForegroundColor Yellow
    Write-Host "   GitHub Secrets should use LF. Converting..." -ForegroundColor Yellow
    $keyContent = $keyContent -replace "`r`n", "`n"
    $keyContent | Set-Content -Path $keyPath -NoNewline -Encoding UTF8
    Write-Host "✅ Converted to LF" -ForegroundColor Green
} else {
    Write-Host "✅ Key has LF line endings (correct)" -ForegroundColor Green
}

# Check 5: No extra spaces
$trimmed = $keyContent.Trim()
if ($keyContent -ne $trimmed) {
    Write-Host "⚠️  Key has leading/trailing spaces" -ForegroundColor Yellow
    Write-Host "   Removing..." -ForegroundColor Yellow
    $trimmed | Set-Content -Path $keyPath -NoNewline -Encoding UTF8
    Write-Host "✅ Spaces removed" -ForegroundColor Green
} else {
    Write-Host "✅ No extra spaces" -ForegroundColor Green
}

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host "📋 PRIVATE KEY (Copy this to GitHub Secrets):" -ForegroundColor Yellow
Write-Host ("=" * 60) -ForegroundColor Cyan
Get-Content $keyPath -Raw
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

Write-Host "📝 Next steps:" -ForegroundColor Green
Write-Host "1. Copy the PRIVATE KEY above (entire content)" -ForegroundColor White
Write-Host "2. Go to: https://github.com/javadmeighani-oss/sedi-backend/settings/secrets/actions" -ForegroundColor White
Write-Host "3. Update SSH_PRIVATE_KEY secret with the copied content" -ForegroundColor White
Write-Host "4. Make sure to include -----BEGIN... and -----END... lines" -ForegroundColor White

