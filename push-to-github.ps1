# Script for pushing to GitHub
# Usage: .\push-to-github.ps1 -RepoUrl "https://github.com/USERNAME/REPO.git"

param(
    [Parameter(Mandatory=$true)]
    [string]$RepoUrl
)

Write-Host "🚀 Starting GitHub push process..." -ForegroundColor Green

# Check if remote exists
$remoteExists = git remote | Select-String -Pattern "origin"
if ($remoteExists) {
    Write-Host "⚠️  Remote 'origin' already exists. Updating..." -ForegroundColor Yellow
    git remote set-url origin $RepoUrl
} else {
    Write-Host "➕ Adding remote 'origin'..." -ForegroundColor Cyan
    git remote add origin $RepoUrl
}

# Verify remote
Write-Host "`n📋 Verifying remote..." -ForegroundColor Cyan
git remote -v

# Rename branch to main if needed
$currentBranch = git branch --show-current
if ($currentBranch -eq "master") {
    Write-Host "`n🔄 Renaming branch from 'master' to 'main'..." -ForegroundColor Cyan
    git branch -M main
    $branchName = "main"
} else {
    $branchName = $currentBranch
}

# Push to GitHub
Write-Host "`n📤 Pushing to GitHub..." -ForegroundColor Cyan
Write-Host "Repository: $RepoUrl" -ForegroundColor Gray
Write-Host "Branch: $branchName" -ForegroundColor Gray
Write-Host ""

try {
    git push -u origin $branchName
    Write-Host "`n✅ Successfully pushed to GitHub!" -ForegroundColor Green
    Write-Host "`n📱 Next steps:" -ForegroundColor Yellow
    Write-Host "1. Go to GitHub repository: $RepoUrl" -ForegroundColor White
    Write-Host "2. Check Actions tab for build status" -ForegroundColor White
    Write-Host "3. Download APK from Actions artifacts after build completes" -ForegroundColor White
} catch {
    Write-Host "`n❌ Error pushing to GitHub:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "`n💡 Make sure:" -ForegroundColor Yellow
    Write-Host "- Repository exists on GitHub" -ForegroundColor White
    Write-Host "- You have push access" -ForegroundColor White
    Write-Host "- You're authenticated (use: git config --global user.name and user.email)" -ForegroundColor White
}

