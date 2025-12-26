# ============================================
# Sedi Backend Restart Script
# ============================================
# این اسکریپت برای restart کردن backend استفاده می‌شود
# Location: backend/scripts/restart-backend.ps1
# ============================================

# تنظیمات - لطفاً این مقادیر را با اطلاعات سرور خود تنظیم کنید
$SERVER_IP = "91.107.168.130"
$SERVER_USER = "root"  # نام کاربری SSH شما
$BACKEND_PATH = "/root/sedi-backend"  # مسیر backend روی سرور

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Sedi Backend Restart" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server: $SERVER_IP" -ForegroundColor Yellow
Write-Host "User: $SERVER_USER" -ForegroundColor Yellow
Write-Host "Backend Path: $BACKEND_PATH" -ForegroundColor Yellow
Write-Host ""

# ============================================
# دستورات آماده برای اجرا
# ============================================

Write-Host "Choose restart method:" -ForegroundColor Green
Write-Host "1. Quick restart (systemctl) - Recommended if service exists" -ForegroundColor White
Write-Host "2. Full restart with git pull" -ForegroundColor White
Write-Host "3. Background restart (nohup)" -ForegroundColor White
Write-Host "4. Test connection only" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Enter your choice (1-4)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "Executing: Quick restart with systemctl..." -ForegroundColor Yellow
        $cmd = "ssh $SERVER_USER@$SERVER_IP 'sudo systemctl restart sedi-backend'"
        Write-Host "Command: $cmd" -ForegroundColor Gray
        Write-Host ""
        Invoke-Expression $cmd
        Write-Host ""
        Write-Host "Restart completed!" -ForegroundColor Green
    }
    "2" {
        Write-Host ""
        Write-Host "Executing: Full restart with git pull..." -ForegroundColor Yellow
        $cmd = "ssh $SERVER_USER@$SERVER_IP 'cd $BACKEND_PATH && git pull origin main && pkill -f uvicorn && sleep 2 && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &'"
        Write-Host "Command: $cmd" -ForegroundColor Gray
        Write-Host ""
        Invoke-Expression $cmd
        Write-Host ""
        Write-Host "Restart completed!" -ForegroundColor Green
    }
    "3" {
        Write-Host ""
        Write-Host "Executing: Background restart..." -ForegroundColor Yellow
        $cmd = "ssh $SERVER_USER@$SERVER_IP 'cd $BACKEND_PATH && git pull origin main && pkill -f uvicorn && nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &'"
        Write-Host "Command: $cmd" -ForegroundColor Gray
        Write-Host ""
        Invoke-Expression $cmd
        Write-Host ""
        Write-Host "Restart completed!" -ForegroundColor Green
    }
    "4" {
        Write-Host ""
        Write-Host "Testing backend connection..." -ForegroundColor Yellow
        try {
            $response = Invoke-WebRequest -Uri "http://$SERVER_IP:8000/" -TimeoutSec 10
            Write-Host "Status Code: $($response.StatusCode)" -ForegroundColor Green
            Write-Host "Response:" -ForegroundColor Green
            Write-Host $response.Content -ForegroundColor White
        }
        catch {
            Write-Host "Error: Backend is not accessible!" -ForegroundColor Red
            Write-Host $_.Exception.Message -ForegroundColor Red
        }
    }
    default {
        Write-Host "Invalid choice!" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Done!" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

