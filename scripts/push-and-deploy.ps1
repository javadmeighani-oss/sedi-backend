# Push and deploy script - avoids index.lock issues by guiding user and using git from repo root.
# Run from repo root: .\scripts\push-and-deploy.ps1
# Or: cd "D:\Rimiya Design Studio\Sedi\software\Demo"; .\scripts\push-and-deploy.ps1

$ErrorActionPreference = "Stop"
$repoRoot = if ($PSScriptRoot) { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path } else { Get-Location }
$lockPath = Join-Path $repoRoot ".git\index.lock"

Write-Host "Repo root: $repoRoot" -ForegroundColor Cyan
Set-Location $repoRoot

# 1. Try to remove stale lock (may need admin or close other git processes)
if (Test-Path $lockPath) {
    Write-Host "Removing .git/index.lock ..." -ForegroundColor Yellow
    try {
        Remove-Item -Force $lockPath -ErrorAction Stop
        Write-Host "Lock removed." -ForegroundColor Green
    } catch {
        Write-Host "Could not remove index.lock. Close Cursor, VS Code, and any terminals using this repo, then run again." -ForegroundColor Red
        Write-Host $_.Exception.Message
        exit 1
    }
}

# 2. Status
Write-Host "`nGit status:" -ForegroundColor Cyan
git status --short 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Git status failed. Fix git state and try again." -ForegroundColor Red
    exit 1
}

# 3. Add backend and workflow (minimal set for backend deploy)
Write-Host "`nStaging backend, .github, app, requirements.txt, deployment..." -ForegroundColor Cyan
git add backend/ 2>&1
git add .github/ 2>&1
git add app/ 2>&1
git add requirements.txt 2>&1
git add deployment/ 2>&1

$status = git status --porcelain
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "Nothing to commit (no changes staged). Exiting." -ForegroundColor Yellow
    exit 0
}

# 4. Commit
$msg = "Backend and deploy: workflow paths, server backend subfolder support"
Write-Host "`nCommitting: $msg" -ForegroundColor Cyan
git commit -m $msg 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Commit failed (maybe nothing to commit or merge conflict)." -ForegroundColor Red
    exit 1
}

# 5. Push
Write-Host "`nPushing to origin main..." -ForegroundColor Cyan
git push origin main 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push failed. Check: SSH key, GitHub status, and remote (git remote -v)." -ForegroundColor Red
    exit 1
}

Write-Host "`nDone. Deploy workflow should run on GitHub Actions." -ForegroundColor Green
