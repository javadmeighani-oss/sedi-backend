# گزارش تشخیص Backend Service

**تاریخ:** 2024-12-30  
**Role:** DevOps Operator (Production Server)  
**Mode:** Execution Only — No Code Change

---

## ⚠️ محدودیت دسترسی

**وضعیت:** دستورات SSH به صورت خودکار اجرا نمی‌شوند  
**دلیل:** نیاز به authentication یا manual intervention

---

## 📋 دستورات لازم برای اجرای دستی

### TASK A — بررسی و Restart Service

#### 1. بررسی وضعیت Service:
```bash
ssh root@91.107.168.130
sudo systemctl status sedi-backend --no-pager
```

#### 2. Restart Service:
```bash
sudo systemctl restart sedi-backend
```

#### 3. انتظار 5 ثانیه:
```bash
sleep 5
```

#### 4. بررسی مجدد:
```bash
sudo systemctl status sedi-backend --no-pager
```

---

### TASK B — بررسی Logs (اگر Service Fail شد)

```bash
sudo journalctl -u sedi-backend -n 50 --no-pager
```

**بررسی کنید:**
- Python traceback errors
- Import errors
- Database connection errors
- Missing environment variables

---

### TASK C — بررسی Dependencies

#### 1. PostgreSQL:
```bash
sudo systemctl status postgresql --no-pager
```

#### 2. Uvicorn:
```bash
ls -la /var/www/sedi/backend/.venv/bin/uvicorn
```

---

### TASK D — Manual Start (برای تشخیص)

```bash
cd /var/www/sedi/backend
source .venv/bin/activate
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

---

## 🔧 دستورات یک خطی (Quick Commands)

### بررسی و Restart:
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

### تست API:
```bash
curl http://91.107.168.130:8000/
```

---

## 📊 وضعیت فعلی

| Component | Status | Action Needed |
|-----------|--------|---------------|
| اینترنت | ✅ متصل | None |
| Network | ✅ OK | None |
| Backend Service | ❌ **503 Unavailable** | **Manual Restart Required** |
| SSH Access | ⚠️ نیاز به manual execution | دستورات آماده است |

---

## ✅ مراحل بعدی

1. ⏳ **اجرای دستی دستورات** در terminal
2. ⏳ **بررسی Service Status** بعد از restart
3. ⏳ **بررسی Logs** اگر خطا وجود دارد
4. ⏳ **تست API** برای تأیید

---

## 📝 گزارش مورد نیاز

بعد از اجرای دستورات، این اطلاعات را گزارش دهید:

1. Service Status (قبل و بعد از restart)
2. Logs (اگر خطا وجود دارد)
3. HTTP Test Result
4. وضعیت نهایی (running/failed)

---

**گزارش ایجاد شده:** 2024-12-30  
**دستورات:** آماده برای اجرای دستی

