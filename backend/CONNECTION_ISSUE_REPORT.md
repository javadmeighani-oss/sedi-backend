# گزارش بررسی مشکل اتصال Frontend به Backend

**تاریخ:** 2024-12-30  
**مشکل:** Frontend نمی‌تواند به Backend متصل شود

---

## 🔍 تشخیص مشکل

### وضعیت اتصال:
- **Backend URL:** `http://91.107.168.130:8000`
- **Test Result:** ❌ **TCP connection failed**
- **Status:** Backend در دسترس نیست

### پیام‌های خطا در اپلیکیشن:
1. **انگلیسی:** "I'm sorry, I'm not connected to the server right now. Please check your internet connection and try again. 😔"
2. **فارسی:** "متأسفانه در حال حاضر به سرور متصل نیستم. لطفاً اتصال اینترنت را بررسی کنید و دوباره تلاش کنید. 😔"
3. **عربی:** "عذراً، أنا غير متصل بالخادم حاليًا. يرجى التحقق من اتصال الإنترنت والمحاولة مرة أخرى. 😔"

---

## 📋 بررسی کد Frontend

### تنظیمات اتصال:
**فایل:** `frontend/lib/core/config/app_config.dart`
```dart
static const String baseUrl = "http://91.107.168.130:8000";
static const bool useLocalMode = false; // ✅ اتصال به backend واقعی
```

**وضعیت:** ✅ تنظیمات درست است

### منطق اتصال:
**فایل:** `frontend/lib/features/chat/chat_service.dart`

**Greeting Request:**
- Endpoint: `/interact/chat`
- Method: POST
- Parameters: `message=__GREETING__`, `lang=...`
- Timeout: 10 seconds

**Chat Message:**
- Endpoint: `/interact/chat`
- Method: POST
- Parameters: `message=...`, `lang=...`, `user_id=...` (optional)
- Timeout: 10 seconds

**وضعیت:** ✅ منطق اتصال درست است

### مدیریت خطا:
**فایل:** `frontend/lib/features/chat/state/chat_controller.dart`

خطاها به درستی مدیریت می‌شوند:
- `BACKEND_UNAVAILABLE` → نمایش پیام خطای مناسب
- Exception در `getGreeting()` → نمایش پیام خطا
- Exception در `sendMessage()` → نمایش پیام خطا

**وضعیت:** ✅ مدیریت خطا درست است

---

## 🔧 علل احتمالی مشکل

### 1. Backend در حال اجرا نیست
**احتمال:** ⚠️ **بالا**

**بررسی:**
- Backend باید روی سرور `91.107.168.130:8000` در حال اجرا باشد
- Service باید active باشد

**راه حل:**
```bash
# روی سرور بررسی کنید:
sudo systemctl status sedi-backend
# یا
ps aux | grep uvicorn
```

### 2. Firewall یا Network Issue
**احتمال:** ⚠️ **متوسط**

**بررسی:**
- Port 8000 باید باز باشد
- Firewall باید اجازه اتصال بدهد

**راه حل:**
```bash
# بررسی firewall:
sudo ufw status
# یا
sudo firewall-cmd --list-ports

# باز کردن port:
sudo ufw allow 8000/tcp
```

### 3. Backend Crash یا Error
**احتمال:** ⚠️ **متوسط**

**بررسی:**
- Logs backend را بررسی کنید
- ممکن است backend crash کرده باشد

**راه حل:**
```bash
# بررسی logs:
sudo journalctl -u sedi-backend -n 50
# یا
tail -f /var/log/sedi-backend.log
```

### 4. IP Address تغییر کرده
**احتمال:** ⚠️ **پایین**

**بررسی:**
- IP سرور ممکن است تغییر کرده باشد
- باید IP جدید را در `app_config.dart` به‌روزرسانی کنید

---

## ✅ راه‌حل‌های پیشنهادی

### راه‌حل 1: بررسی و Restart Backend

```bash
# روی سرور:
cd /path/to/backend
sudo systemctl restart sedi-backend
sudo systemctl status sedi-backend
```

### راه‌حل 2: بررسی Network Connectivity

```bash
# از local machine:
ping 91.107.168.130
telnet 91.107.168.130 8000
# یا
curl http://91.107.168.130:8000/
```

### راه‌حل 3: بررسی Logs

```bash
# بررسی logs برای خطاها:
sudo journalctl -u sedi-backend --since "10 minutes ago"
```

### راه‌حل 4: Manual Start Backend (برای تست)

```bash
# روی سرور:
cd /path/to/backend
source venv/bin/activate  # اگر virtualenv دارید
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 📊 وضعیت فعلی

| Component | Status | Details |
|-----------|--------|---------|
| Frontend Config | ✅ OK | Base URL درست تنظیم شده |
| Frontend Logic | ✅ OK | Error handling درست است |
| Backend URL | ❌ **NOT REACHABLE** | TCP connection failed |
| Network Test | ❌ **FAILED** | Cannot connect to 91.107.168.130:8000 |

---

## 🎯 اقدامات فوری

### برای DevOps:
1. ✅ بررسی کنید که backend service در حال اجرا است
2. ✅ بررسی logs برای خطاها
3. ✅ بررسی firewall و network rules
4. ✅ Restart backend service اگر لازم است

### برای Developer:
1. ✅ Frontend code درست است - نیازی به تغییر نیست
2. ✅ Error messages به درستی نمایش داده می‌شوند
3. ⏳ منتظر بمانید تا backend در دسترس قرار گیرد

---

## 📝 خلاصه

**مشکل:** Backend در دسترس نیست (`91.107.168.130:8000`)

**علت احتمالی:** 
- Backend service متوقف شده
- Network/Firewall issue
- Backend crash

**راه حل:**
- بررسی و restart backend service
- بررسی network connectivity
- بررسی logs برای خطاها

**Frontend:** ✅ کد درست است - نیازی به تغییر نیست

---

**گزارش ایجاد شده:** 2024-12-30

