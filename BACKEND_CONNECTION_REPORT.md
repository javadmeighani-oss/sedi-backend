# گزارش بررسی اتصال Backend و Frontend

**تاریخ:** 2024-12-30  
**وضعیت:** ❌ **Backend در دسترس نیست**

---

## مشکل شناسایی شده

از اسکرین‌شات موبایل:
- ❌ پیام خطا: "I'm sorry, I'm not connected to the server right now. Please check your internet connection and try again. 😔"
- ❌ Frontend نمی‌تواند به Backend متصل شود

---

## تست‌های انجام شده

### 1. تست TCP Connection
```powershell
Test-NetConnection -ComputerName 91.107.168.130 -Port 8000
```

**نتیجه:**
- ✅ Ping موفق: 132ms (سرور online است)
- ❌ TCP Connection به Port 8000: **FAILED**
- ❌ Port 8000 باز نیست یا service در حال اجرا نیست

### 2. تست HTTP Request
```powershell
Invoke-WebRequest -Uri "http://91.107.168.130:8000/docs"
```

**نتیجه:**
- ❌ Status Code: **503 Server Unavailable**
- ❌ Service در دسترس نیست

---

## تحلیل مشکل

### علت اصلی:
**Backend service در حال اجرا نیست یا در دسترس نیست.**

### دلایل احتمالی:

1. **Service متوقف شده:**
   - FastAPI service ممکن است crash کرده باشد
   - Systemd service ممکن است متوقف شده باشد

2. **Port بسته است:**
   - Firewall ممکن است port 8000 را بسته باشد
   - Service ممکن است روی port دیگری اجرا شود

3. **مشکل در Deployment:**
   - Service ممکن است restart نشده باشد
   - ممکن است نیاز به restart داشته باشد

---

## تنظیمات Frontend

### URL Backend:
```dart
// frontend/lib/core/config/app_config.dart
static const String baseUrl = "http://91.107.168.130:8000";
```

✅ **تنظیمات Frontend درست است**

### Error Handling:
- ✅ Retry mechanism (3 attempts)
- ✅ Timeout: 15 seconds
- ✅ Error messages به زبان‌های مختلف
- ✅ Connection error detection

✅ **Error handling Frontend کامل است**

---

## راه‌حل‌های پیشنهادی

### 1. بررسی وضعیت Backend Service (اولویت اول)

**SSH به سرور:**
```bash
ssh root@91.107.168.130
```

**بررسی service:**
```bash
# بررسی systemd service
systemctl status sedi-backend
# یا
systemctl status uvicorn

# بررسی process
ps aux | grep uvicorn
ps aux | grep python

# بررسی port
netstat -tulpn | grep 8000
# یا
ss -tulpn | grep 8000
```

### 2. Restart Backend Service

```bash
# Restart service
systemctl restart sedi-backend
# یا
systemctl restart uvicorn

# بررسی logs
journalctl -u sedi-backend -f
# یا
tail -f /var/log/sedi-backend.log
```

### 3. بررسی Firewall

```bash
# بررسی firewall rules
ufw status
# یا
iptables -L -n | grep 8000

# اگر port بسته است، باز کنید
ufw allow 8000/tcp
```

### 4. بررسی Nginx (اگر استفاده می‌شود)

```bash
# بررسی nginx status
systemctl status nginx

# بررسی nginx config
cat /etc/nginx/sites-available/sedi-backend

# Restart nginx
systemctl restart nginx
```

### 5. اجرای دستی Backend (برای تست)

```bash
cd /path/to/backend
source venv/bin/activate
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

---

## تست بعد از Fix

### 1. تست از Windows:
```powershell
# تست TCP
Test-NetConnection -ComputerName 91.107.168.130 -Port 8000

# تست HTTP
Invoke-WebRequest -Uri "http://91.107.168.130:8000/docs"
```

### 2. تست از موبایل:
- باز کردن app
- بررسی اینکه greeting نمایش داده می‌شود
- ارسال یک پیام تست

---

## خلاصه

| مورد | وضعیت | توضیح |
|------|-------|-------|
| **Frontend Config** | ✅ | URL درست است |
| **Frontend Error Handling** | ✅ | کامل است |
| **Backend Service** | ❌ | در حال اجرا نیست |
| **Port 8000** | ❌ | بسته است یا service نیست |
| **Server Ping** | ✅ | سرور online است |

---

## اقدامات لازم

1. ✅ **بررسی وضعیت Backend Service** (اولویت اول)
2. ✅ **Restart Service** اگر متوقف شده
3. ✅ **بررسی Logs** برای پیدا کردن مشکل
4. ✅ **تست اتصال** بعد از restart
5. ✅ **بررسی Firewall** اگر مشکل ادامه داشت

---

**وضعیت:** نیاز به بررسی و restart Backend Service روی سرور

