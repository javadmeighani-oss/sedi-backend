# Backend Scripts

این پوشه شامل اسکریپت‌های مدیریتی برای backend است.

## فایل‌های موجود

### `restart-backend.ps1`
اسکریپت PowerShell برای restart کردن backend روی سرور.

**استفاده:**
```powershell
.\restart-backend.ps1
```

### `RESTART_INSTRUCTIONS.md`
راهنمای کامل برای restart کردن backend با روش‌های مختلف.

### `prod_notifications_sanity.sh` (Stage 16.6.3)
Production sanity checks for push notifications. Checks env vars, health endpoints, test push.

**Usage:**
```bash
ADMIN_TOKEN=your_token BASE_URL=http://localhost:8000 USER_ID=1 bash backend/scripts/prod_notifications_sanity.sh
```

### `notifications_e2e_smoke.py`
E2E smoke test for notifications (admin endpoints, deliver_pending, feedback).

## نکات مهم

- تمام اسکریپت‌های backend باید در این پوشه باشند
- اسکریپت‌های deployment در `../deployment/` قرار دارند
- این اسکریپت‌ها فقط برای backend هستند و نباید در frontend استفاده شوند

