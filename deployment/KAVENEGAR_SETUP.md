# فعال‌سازی ارسال SMS کاوا نیگار

## روش ۱: اسکریپت خودکار (پیشنهادی)

```powershell
$env:KAVENEGAR_API_KEY="your-api-key-from-kavenegar-panel"
.\deployment\setup_sms_on_server.ps1
```

نیاز به اتصال SSH به سرور دارد. در صورت استفاده از کلید SSH، احراز هویت خودکار انجام می‌شود.

## روش ۲: دستی

### ۱. اتصال به سرور

```bash
ssh root@91.107.168.130
nano /var/www/sedi/backend/.env
```

### ۲. اضافه کردن خطوط

```
KAVENEGAR_API_KEY=your-actual-api-key
SMS_DISABLED=false
```

اگر `SMS_DISABLED=true` وجود دارد، حذف یا به `false` تغییر دهید.

### ۳. ریستارت

```bash
systemctl restart sedi-backend
```

### ۴. بررسی لاگ

```bash
journalctl -u sedi-backend -f -n 50
```

---

**توجه:** API Key را هرگز در ریپوزیتوری commit نکنید.
