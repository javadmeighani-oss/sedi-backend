# راهنمای بررسی لاگ‌های Backend

## 📍 محل لاگ‌ها

لاگ‌های backend در دو حالت ممکن است باشند:

### حالت 1: اجرا با systemd service (Production)

اگر backend به صورت service اجرا می‌شود، لاگ‌ها در **systemd journal** ذخیره می‌شوند.

#### دستورات بررسی لاگ:

```bash
# نمایش تمام لاگ‌های service
sudo journalctl -u sedi-backend

# نمایش لاگ‌های آخرین 100 خط
sudo journalctl -u sedi-backend -n 100

# نمایش لاگ‌های از 10 دقیقه پیش تا الان
sudo journalctl -u sedi-backend --since "10 minutes ago"

# نمایش لاگ‌های از یک زمان خاص
sudo journalctl -u sedi-backend --since "2025-01-15 10:00:00"

# نمایش لاگ‌های real-time (follow mode)
sudo journalctl -u sedi-backend -f

# فیلتر لاگ‌های onboarding
sudo journalctl -u sedi-backend | grep -i "ONBOARDING"

# فیلتر لاگ‌های خطا
sudo journalctl -u sedi-backend | grep -i "error\|failed\|❌"

# نمایش لاگ‌های با رنگ (اگر terminal پشتیبانی می‌کند)
sudo journalctl -u sedi-backend --no-pager | grep --color=always -i "ONBOARDING\|ERROR\|SUCCESS"
```

#### اگر SSH به سرور ندارید:

اگر backend روی سرور remote است و SSH ندارید:
1. از پنل مدیریت سرور (cPanel, Plesk, etc.) استفاده کنید
2. یا از VNC/RDP به سرور متصل شوید
3. یا با مدیر سرور تماس بگیرید

---

### حالت 2: اجرا مستقیم با uvicorn (Development)

اگر backend را به صورت مستقیم اجرا می‌کنید:

```bash
# در terminal/console که uvicorn را اجرا کرده‌اید
# لاگ‌ها مستقیماً در همان terminal نمایش داده می‌شوند
```

#### دستور اجرا:

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

در این حالت، تمام لاگ‌ها (شامل `[ONBOARDING]` logs) در همان terminal نمایش داده می‌شوند.

---

### حالت 3: اجرا با nohup (Background)

اگر backend را با `nohup` اجرا کرده‌اید:

```bash
# لاگ‌ها در فایل backend.log ذخیره می‌شوند
tail -f backend.log

# یا نمایش آخرین 100 خط
tail -n 100 backend.log

# فیلتر لاگ‌های onboarding
grep -i "ONBOARDING" backend.log

# فیلتر لاگ‌های خطا
grep -i "error\|failed\|❌" backend.log
```

---

## 🔍 چه لاگ‌هایی را بررسی کنیم؟

برای مشکل onboarding، این لاگ‌ها مهم هستند:

### 1. لاگ‌های شروع Onboarding:
```
[ONBOARDING] ========== START ONBOARDING ==========
[ONBOARDING] Password length: X, Language: Y
```

### 2. لاگ‌های بررسی دیتابیس:
```
[ONBOARDING] Check 1: Testing database connection...
[ONBOARDING] ✅ Database connection: OK
[ONBOARDING] Check 2: Verifying users table exists...
[ONBOARDING] ✅ Table 'users' exists
[ONBOARDING] Check 3: Verifying users table structure...
[ONBOARDING] ✅ Users table structure: OK
```

### 3. لاگ‌های ایجاد User:
```
[ONBOARDING] Step 3: Creating user object...
[ONBOARDING] ✅ User object created
[ONBOARDING] Step 4: Adding user to session...
[ONBOARDING] ✅ User added to session
[ONBOARDING] Step 5: Committing transaction...
[ONBOARDING] ✅ Transaction committed
[ONBOARDING] Step 6: Refreshing user to get ID...
[ONBOARDING] ✅ Step 3 SUCCESS: User created - user_id: X
```

### 4. لاگ‌های خطا (اگر خطا رخ دهد):
```
[ONBOARDING] ❌ Step 1 FAILED: Database error creating user: ...
[ONBOARDING] Error type: ...
[ONBOARDING] Traceback: ...
```

---

## 📋 دستورات سریع برای بررسی

### در سرور (با SSH):

```bash
# نمایش لاگ‌های onboarding از 5 دقیقه پیش
sudo journalctl -u sedi-backend --since "5 minutes ago" | grep -i "ONBOARDING"

# نمایش آخرین خطاها
sudo journalctl -u sedi-backend -n 50 | grep -i "error\|failed\|❌"

# نمایش تمام لاگ‌های onboarding امروز
sudo journalctl -u sedi-backend --since today | grep -i "ONBOARDING"
```

### در Development (Local):

```bash
# اگر uvicorn را در terminal اجرا کرده‌اید
# فقط به terminal نگاه کنید - تمام لاگ‌ها آنجا هستند

# اگر با nohup اجرا کرده‌اید
tail -f backend.log | grep -i "ONBOARDING"
```

---

## 🛠️ اگر لاگ‌ها را نمی‌بینید

### 1. بررسی کنید service در حال اجرا است:

```bash
sudo systemctl status sedi-backend
```

### 2. بررسی کنید service لاگ می‌گیرد:

```bash
sudo journalctl -u sedi-backend -n 10
```

### 3. Restart کنید و لاگ‌ها را دنبال کنید:

```bash
sudo systemctl restart sedi-backend
sudo journalctl -u sedi-backend -f
```

---

## 📝 مثال کامل

```bash
# 1. Restart service
sudo systemctl restart sedi-backend

# 2. دنبال کردن لاگ‌ها به صورت real-time
sudo journalctl -u sedi-backend -f

# 3. در یک terminal دیگر، تست onboarding انجام دهید
# 4. در terminal اول، لاگ‌های [ONBOARDING] را مشاهده کنید
```

---

## 💡 نکات مهم

1. **لاگ‌های systemd** ممکن است بعد از restart پاک شوند (بسته به تنظیمات)
2. **برای debugging بهتر**، لاگ‌ها را به صورت real-time دنبال کنید (`-f` flag)
3. **اگر لاگ‌ها خیلی زیاد هستند**، از `grep` برای فیلتر کردن استفاده کنید
4. **تمام لاگ‌های `[ONBOARDING]`** با پیشوند مشخص شروع می‌شوند و راحت پیدا می‌شوند

---

## 🔗 فایل‌های مرتبط

- Service file: `backend/deployment/sedi-backend.service`
- Main app: `backend/app/main.py`
- Onboarding endpoint: `backend/app/routers/interact.py`

