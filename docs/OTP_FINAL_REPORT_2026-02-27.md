# گزارش نهایی — اصلاحات OTP و ارسال SMS

**تاریخ:** ۲۷ فوریه ۲۰۲۶  
**به‌روزرسانی:** مهاجرت OTP به Mediana (Kavenegar لغو شد)

---

## خلاصه اجرایی

مشکلات ارسال و تأیید کد OTP برطرف شد. اپ اکنون در دو حالت کار می‌کند:
1. **حالت تست:** `SMS_DISABLED=true` — کد در اپ (`dev_code` / SnackBar) نمایش داده می‌شود
2. **حالت تولید:** `SMS_PROVIDER=mediana` — OTP از طریق Mediana ارسال می‌شود

---

## فعال‌سازی ارسال واقعی SMS (Mediana)

روی سرور (`/etc/sedi/sedi-backend.env`):

```
SMS_DISABLED=false
SMS_PROVIDER=mediana
MEDIANA_API_KEY=<from Mediana panel>
MEDIANA_OTP_PATTERN_CODE=<pattern code>
```

سپس recreate کانتینر `sedi-backend`.

مستندات: `deployment/MEDIANA_SETUP.md`

---

## وضعیت نهایی

| بخش | وضعیت |
|-----|-------|
| OTP با Mediana | تکمیل |
| Kavenegar | حذف / پشتیبانی نمی‌شود |
| `dev_code` در حالت تست | تکمیل |
| مستندسازی و `.env.example` | Mediana-only |

---

## مراحل باقی‌مانده (دستی)

تنظیم `MEDIANA_API_KEY` و `MEDIANA_OTP_PATTERN_CODE` روی سرور — کلید API در ریپو commit نمی‌شود.
