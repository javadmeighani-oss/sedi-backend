# BACKEND FREEZE (Stage: Post-Release D / Stage 3)

- **تاریخ:** <FILL_DATE>
- **ریپو:** javadmeighani-oss/sedi-backend
- **برنچ:** main
- **کامیت:** `e7b008f` (یا <FILL_COMMIT_SHA> برای قفل رسمی)

---

## ۱) معیارهای فریز (چک‌لیست انجام‌شده)

- [ ] systemd با entrypoint برابر است با: `backend.app.main:app`
- [ ] سرویس فعال است: `systemctl status sedi-backend` → active (running)
- [ ] `GET /docs` با کد ۲۰۰ پاسخ می‌دهد
- [ ] `POST /notifications/deliver_pending` با کد ۲۰۰ پاسخ می‌دهد
- [ ] جدول `notifications` در دیتابیس وجود دارد
- [ ] `deliver_pending` فیلدهای `is_sent=true` و `sent_at` را به‌درستی ست می‌کند
- [ ] مایگریشن‌های Release D (ستون `sent_at` + ایندکس‌ها) اعمال شده‌اند
- [ ] CI: workflow دیپلوی سبز است
- [ ] CI: تست‌های acceptance سبز هستند

---

## ۲) راهنمای عملیاتی (دستورات سرور)

**وضعیت سرویس:**
```bash
sudo systemctl status sedi-backend.service --no-pager -l
```

**آخرین لاگ‌ها:**
```bash
sudo journalctl -u sedi-backend.service -n 80 --no-pager
```

**ری‌استارت:**
```bash
sudo systemctl daemon-reload
sudo systemctl restart sedi-backend.service
```

**تست /docs:**
```bash
curl -sS -i http://127.0.0.1:8000/docs | head -n 20
```

**تست تحویل اعلان:**
```bash
curl -sS -i -X POST "http://127.0.0.1:8000/notifications/deliver_pending" | head -n 60
```

**بررسی دیتابیس (تعداد اعلان‌ها):**
```bash
sudo -u postgres psql -d sedi_db -c "SELECT count(*) FROM notifications;"
```

**بررسی وجود جدول و ستون sent_at:**
```bash
sudo -u postgres psql -d sedi_db -c "\d notifications"
```

---

## ۳) سیاست تغییرات (مهم)

- **برنچ main فریز است.** تغییرات فقط در موارد زیر مجاز است:
  - **هاتفیک/باگ‌فیک** برای: (الف) کرش یا از دست رفتن داده در پروداکشن، (ب) رفع آسیب‌پذیری امنیتی، (ج) رفع بلاکِر فرانت‌اند.
- **تا پایان تست میدانی ممنوع است:**
  - رفکتور، تغییر اسکیما (مگر بحرانی)، تغییرات گسترده در scheduler یا لایهٔ AI، و افزودن فیچر جدید به بک‌اند.

---

## ۴) حداقل امنیت قبل از ۱۰۰ کاربر

- [ ] چرخش کلید OpenAI (کلید واقعی، نه تست)
- [ ] تنظیم `DEVICE_INGEST_TOKEN` واقعی (غیر از مقدار تست)
- [ ] (اختیاری) محدود کردن دسترسی به `/docs` در پروداکشن
- [ ] (اختیاری) محدود کردن CORS به دامنهٔ فرانت (به‌جای `*`)

---

## ۵) تعریف «بک‌اند انجام‌شده»

بک‌اند برای تست میدانی ۱۰۰ کاربر «انجام‌شده» در نظر گرفته می‌شود؛ تمرکز به فرانت‌اند و یادگیری از تست میدانی منتقل می‌شود. تغییرات بک‌اند فقط در صورتی اعمال می‌شوند که تست میدانی را باز کنند (مطابق سیاست تغییرات بالا).
