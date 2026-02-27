# فعال‌سازی ارسال SMS کاوا نیگار

## مراحل

### ۱. روی سرور: اضافه کردن API Key به فایل .env

```bash
ssh root@91.107.168.130
nano /var/www/sedi/backend/.env
```

این خط را اضافه یا ویرایش کنید (کلید را از پنل کاوا نیگار جایگزین کنید):

```
KAVENEGAR_API_KEY=your-actual-api-key
```

اگر `SMS_DISABLED=true` وجود دارد، آن را حذف یا به `false` تغییر دهید.

### ۲. ریستارت سرویس

```bash
systemctl restart sedi-backend
```

### ۳. بررسی لاگ

```bash
journalctl -u sedi-backend -f -n 50
```

با درخواست OTP، اگر ارسال موفق باشد، خطای `SMS send failed` نباید ظاهر شود.

---

**توجه:** API Key را هرگز در ریپوزیتوری یا کد قرار ندهید. فقط در فایل `.env` روی سرور که در .gitignore است.
