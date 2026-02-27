# گزارش نهایی — اصلاحات OTP و ارسال SMS

**تاریخ:** ۲۷ فوریه ۲۰۲۶  

---

## خلاصه اجرایی

مشکلات ارسال و تأیید کد OTP برطرف شد. اپ اکنون در دو حالت کار می‌کند:
1. **حالت تست:** بدون SMS واقعی — کد در اپ (SnackBar) نمایش داده می‌شود
2. **حالت تولید:** با تنظیم Kavenegar — SMS به موبایل کاربر ارسال می‌شود

---

## تغییرات انجام‌شده

### ۱. فرانت‌اند (Frontend)

| فایل | تغییر |
|------|-------|
| `frontend/lib/features/auth_otp/presentation/pages/otp_login_page.dart` | رفع overflow کیبورد، ScrollView، نرمال‌سازی شماره تلفن ایرانی (09... → +98...)، پیام‌های خطای فارسی |
| `frontend/lib/core/auth/auth_otp_service.dart` | افزایش timeout به ۳۰ ثانیه، نمایش dev_code در SnackBar |
| `frontend/android/app/build.gradle` | minSdk از ۲۱ به ۲۳ برای سازگاری با record_android |
| `frontend/pubspec.yaml` | bump version 1.0.0+3 |

### ۲. بک‌اند (Backend)

| فایل | تغییر |
|------|-------|
| `backend/app/services/auth_otp_service.py` | برگرداندن `dev_code` وقتی SMS ارسال نشود، rate limit قابل تنظیم (پیش‌فرض ۵ در ۱۰ دقیقه) |
| `backend/app/routers/auth_otp.py` | افزودن `dev_code` به پاسخ request_otp در حالت توسعه |
| `backend/docs/STAGE25_OTP_AUTH_RUNBOOK.md` | مستندسازی راه‌اندازی Kavenegar (API key، خط ارسال) |

### ۳. CI و Build

| فایل | تغییر |
|------|-------|
| `.github/workflows/frontend_android_debug.yml` | استفاده از google-services.json.ci با ساختار صحیح |

### ۴. مستندات و پیکربندی

| فایل | تغییر |
|------|-------|
| `backend/.env.example` | نمونه متغیرهای محیطی شامل KAVENEGAR_API_KEY |
| `deployment/KAVENEGAR_SETUP.md` | راهنمای فعال‌سازی SMS با کاوا نیگار |

---

## فعال‌سازی ارسال واقعی SMS

برای ارسال SMS به موبایل کاربران:

1. SSH به سرور: `ssh root@91.107.168.130`
2. ویرایش: `nano /var/www/sedi/backend/.env`
3. اضافه کردن: `KAVENEGAR_API_KEY=your-api-key`
4. حذف `SMS_DISABLED=true` در صورت وجود
5. ریستارت: `systemctl restart sedi-backend`

مستندات کامل: `deployment/KAVENEGAR_SETUP.md`

---

## کامیت‌های پوش‌شده در GitHub

```
9342578 fix(auth): return dev_code when SMS not sent - OTP works without Kavenegar
2ec651f fix(auth): OTP UX - layout overflow, timeout, rate limit, phone norm, error messages
154493e fix(android): set minSdk 23 for record_android compatibility
f06cf24 chore(frontend): bump version 1.0.0+3 - trigger CI build
8265acd fix(ci): use google-services.json.ci stub
```

---

## وضعیت نهایی

| بخش | وضعیت |
|-----|-------|
| رفع overflow صفحه OTP | تکمیل |
| افزایش timeout درخواست | ۳۰ ثانیه |
| پیام‌های خطای فارسی | تکمیل |
| نرمال‌سازی شماره تلفن (۰۹...) | تکمیل |
| نمایش کد در حالت تست (dev_code) | تکمیل |
| پشتیبانی از Kavenegar برای SMS واقعی | تکمیل |
| مستندسازی و .env.example | تکمیل |
| بیلد CI Android | تکمیل |
| Push به GitHub | تکمیل |

---

## مراحل باقی‌مانده (دستی)

تنظیم `KAVENEGAR_API_KEY` در فایل `.env` روی سرور و ریستارت سرویس — این کار باید توسط شما روی سرور انجام شود (کلید API در ریپو commit نمی‌شود به‌دلیل امنیت).
