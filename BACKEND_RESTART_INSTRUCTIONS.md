# دستورالعمل Restart Backend Service

**تاریخ:** 2024-12-30  
**سرور:** 91.107.168.130  
**Service:** sedi-backend  
**وضعیت فعلی:** HTTP 503 Server Unavailable

---

## 🔍 TASK A — بررسی و Restart Service

### مرحله 1: بررسی وضعیت Service

```bash
ssh root@91.107.168.130
sudo systemctl status sedi-backend --no-pager
```

**خروجی مورد انتظار:**
- اگر `active (running)` → Service در حال اجرا است
- اگر `inactive (dead)` → Service متوقف شده
- اگر `failed` → Service crash کرده

### مرحله 2: Restart Service

```bash
sudo systemctl restart sedi-backend
```

### مرحله 3: انتظار 5 ثانیه

```bash
sleep 5
```

### مرحله 4: بررسی مجدد وضعیت

```bash
sudo systemctl status sedi-backend --no-pager
```

**بررسی کنید:**
- ✅ `Active: active (running)`
- ✅ `Main PID: [number]`
- ✅ No error messages

---

## 🔍 TASK B — بررسی Logs (اگر Service Fail شد)

### اگر Service در حالت `failed` یا `inactive` است:

```bash
sudo journalctl -u sedi-backend -n 50 --no-pager
```

**بررسی کنید:**
- Python traceback errors
- Import errors
- Database connection errors
- Missing dependencies
- Environment variable errors

**مثال خطاهای رایج:**
```
ModuleNotFoundError: No module named '...'
psycopg2.OperationalError: could not connect to server
FileNotFoundError: .env file not found
```

---

## 🔍 TASK C — بررسی Dependencies (Read-Only)

### 1. بررسی PostgreSQL

```bash
sudo systemctl status postgresql --no-pager
```

**باید باشد:**
- ✅ `Active: active (running)`

**اگر متوقف است:**
```bash
sudo systemctl start postgresql
```

### 2. بررسی Uvicorn در Virtual Environment

```bash
ls -la /var/www/sedi/backend/.venv/bin/uvicorn
```

**باید باشد:**
- ✅ File exists
- ✅ Executable permissions

**اگر وجود ندارد:**
```bash
cd /var/www/sedi/backend
source .venv/bin/activate
pip install uvicorn
```

---

## 🔍 TASK D — Manual Start (برای تشخیص)

### اگر systemd restart کار نکرد:

```bash
# 1. Navigate to backend directory
cd /var/www/sedi/backend

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Check environment variables
cat .env

# 4. Start uvicorn manually
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

**بررسی کنید:**
- ✅ Startup messages بدون error
- ✅ "Application startup complete"
- ✅ Listening on `0.0.0.0:8000`

**اگر خطا دیدید:**
- خطا را کپی کنید
- گزارش دهید

---

## 📋 دستورات یک خطی (Quick Commands)

### بررسی وضعیت و Restart:

```bash
ssh root@91.107.168.130 "sudo systemctl status sedi-backend --no-pager && sudo systemctl restart sedi-backend && sleep 5 && sudo systemctl status sedi-backend --no-pager"
```

### بررسی Logs:

```bash
ssh root@91.107.168.130 "sudo journalctl -u sedi-backend -n 50 --no-pager"
```

### بررسی Dependencies:

```bash
ssh root@91.107.168.130 "sudo systemctl status postgresql --no-pager && ls -la /var/www/sedi/backend/.venv/bin/uvicorn"
```

### تست API بعد از Restart:

```bash
curl http://91.107.168.130:8000/
```

---

## ✅ چک‌لیست عیب‌یابی

### بررسی‌های لازم:

- [ ] Service status: `sudo systemctl status sedi-backend`
- [ ] Service restart: `sudo systemctl restart sedi-backend`
- [ ] Service status بعد از restart
- [ ] Logs: `sudo journalctl -u sedi-backend -n 50`
- [ ] PostgreSQL: `sudo systemctl status postgresql`
- [ ] Uvicorn: `ls -la /var/www/sedi/backend/.venv/bin/uvicorn`
- [ ] Manual start (اگر لازم بود)
- [ ] API test: `curl http://91.107.168.130:8000/`

---

## 🎯 علل احتمالی HTTP 503

### 1. Service متوقف شده
**راه حل:** `sudo systemctl restart sedi-backend`

### 2. Service crash کرده
**راه حل:** بررسی logs و رفع خطا

### 3. PostgreSQL متوقف شده
**راه حل:** `sudo systemctl start postgresql`

### 4. Virtual environment مشکل دارد
**راه حل:** بررسی مسیر `.venv/bin/uvicorn`

### 5. Environment variables مشکل دارد
**راه حل:** بررسی فایل `.env`

---

## 📝 گزارش نهایی

بعد از اجرای دستورات، این اطلاعات را گزارش دهید:

1. **Service Status (قبل از restart):**
   ```
   [خروجی systemctl status]
   ```

2. **Service Status (بعد از restart):**
   ```
   [خروجی systemctl status]
   ```

3. **Logs (اگر خطا وجود دارد):**
   ```
   [خروجی journalctl]
   ```

4. **HTTP Test Result:**
   ```
   [Status code و response]
   ```

5. **وضعیت نهایی:**
   - ✅ Service running
   - ❌ Service failed (با دلیل)

---

**دستورالعمل ایجاد شده:** 2024-12-30  
**برای اجرا:** دستورات بالا را در terminal اجرا کنید

