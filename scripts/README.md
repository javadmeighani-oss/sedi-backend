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

## نکات مهم

- تمام اسکریپت‌های backend باید در این پوشه باشند
- اسکریپت‌های deployment در `../deployment/` قرار دارند
- این اسکریپت‌ها فقط برای backend هستند و نباید در frontend استفاده شوند

