# Deploy Conversation Brain v1 - دستورات Deploy

## تغییرات انجام شده
- Conversation Brain v1 (Phase 3)
- Conversation Tuning v1 (Phase 3.A)
- فایل‌های جدید در `app/core/conversation/`
- تغییرات در `app/routers/interact.py`
- مستندات در `docs/`

## دستورات Deploy روی سرور

### 1. اتصال به سرور
```bash
ssh root@91.107.168.130
```

### 2. رفتن به پوشه backend
```bash
cd /var/www/sedi/backend
```

### 3. Pull تغییرات از Git
```bash
git pull
```

### 4. بررسی تغییرات
```bash
# بررسی فایل‌های جدید
ls -la app/core/conversation/

# بررسی تغییرات در interact.py
git diff HEAD~1 app/routers/interact.py | head -30
```

### 5. نصب Dependencies (در صورت نیاز)
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 6. راه‌اندازی مجدد سرویس
```bash
systemctl restart sedi-backend
```

### 7. بررسی وضعیت سرویس
```bash
systemctl status sedi-backend --no-pager
```

### 8. بررسی لاگ‌ها
```bash
journalctl -u sedi-backend -n 50 --no-pager
```

### 9. تست API
```bash
# تست greeting endpoint
curl "http://localhost:8000/interact/greeting?user_id=1&lang=en" | python3 -m json.tool

# تست chat endpoint
curl -X POST "http://localhost:8000/interact/chat?message=Hello&name=testuser&secret_key=xxx&lang=en" | python3 -m json.tool
```

## نکات مهم

1. **تغییرات Breaking:**
   - `/interact/chat` اکنون نیاز به authentication دارد (name + secret_key)
   - اگر frontend از این endpoint استفاده می‌کند، باید authentication را اضافه کند

2. **Dependencies:**
   - همه dependencies موجود هستند (openai, sqlalchemy, etc.)
   - نیازی به نصب dependency جدید نیست

3. **Database:**
   - هیچ تغییر schema وجود ندارد
   - جداول موجود کافی هستند

4. **Environment Variables:**
   - `OPENAI_API_KEY` باید در `.env` تنظیم شده باشد
   - `DATABASE_URL` باید در `.env` تنظیم شده باشد

## در صورت بروز خطا

### خطای Import
```bash
# بررسی Python path
python3 -c "import app.core.conversation.brain; print('OK')"
```

### خطای GPT API
```bash
# بررسی API key
grep OPENAI_API_KEY /var/www/sedi/backend/.env
```

### خطای Database
```bash
# بررسی connection
PGPASSWORD='Sedi2025!SecurePass' psql -h localhost -U sedi_user -d sedi_db -c "SELECT 1;"
```

## Rollback (در صورت نیاز)

```bash
# بازگشت به commit قبلی
git reset --hard HEAD~1
systemctl restart sedi-backend
```

## تایید نهایی

پس از deploy، این endpoint‌ها باید کار کنند:
- ✅ `GET /interact/greeting?user_id=1&lang=en`
- ✅ `POST /interact/chat?message=Hello&name=testuser&secret_key=xxx&lang=en`
- ✅ `POST /interact/introduce?name=test&secret_key=xxx&lang=en`

