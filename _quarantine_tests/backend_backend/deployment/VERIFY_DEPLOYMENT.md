# بررسی Deploy Conversation Brain v1

## وضعیت فعلی

✅ **سرویس راه‌اندازی شده**
✅ **تست greeting کار می‌کند**
✅ **تست chat کار می‌کند**
⚠️ **پاسخ‌ها یکسان هستند** (نیاز به بررسی)

## بررسی‌های لازم

### 1. بررسی secret_key کاربر

```bash
# بررسی secret_key کاربر testuser
PGPASSWORD='Sedi2025!SecurePass' psql -h localhost -U sedi_user -d sedi_db -c "SELECT id, name, secret_key FROM users WHERE name='testuser';"
```

### 2. بررسی Memory (ذخیره گفتگوها)

```bash
# بررسی memory entries
PGPASSWORD='Sedi2025!SecurePass' psql -h localhost -U sedi_user -d sedi_db -c "SELECT id, user_id, user_message, sedi_response, created_at FROM memory ORDER BY created_at DESC LIMIT 5;"
```

### 3. تست چند پیام متوالی

```bash
# پیام 1
curl -X POST "http://localhost:8000/interact/chat?message=Hello&name=testuser&secret_key=test123&lang=en"

# پیام 2 (باید متفاوت باشد)
curl -X POST "http://localhost:8000/interact/chat?message=I%20like%20reading&name=testuser&secret_key=test123&lang=en"

# پیام 3
curl -X POST "http://localhost:8000/interact/chat?message=What%20about%20you?&name=testuser&secret_key=test123&lang=en"
```

### 4. بررسی Stage Progression

```bash
# بررسی تعداد memory entries برای user
PGPASSWORD='Sedi2025!SecurePass' psql -h localhost -U sedi_user -d sedi_db -c "SELECT COUNT(*) as memory_count FROM memory WHERE user_id=1;"
```

### 5. بررسی لاگ‌های زنده

```bash
# مشاهده لاگ‌های زنده
journalctl -u sedi-backend -f
```

## مشکلات احتمالی

### مشکل 1: secret_key اشتباه
**علت:** User با secret_key متفاوت ایجاد شده
**راه حل:** 
- بررسی secret_key در دیتابیس
- استفاده از secret_key صحیح در تست

### مشکل 2: Memory ذخیره نمی‌شود
**علت:** خطا در save_conversation
**راه حل:**
- بررسی لاگ‌ها برای خطا
- بررسی database connection

### مشکل 3: GPT پاسخ‌های یکسان می‌دهد
**علت:** Context درست ساخته نمی‌شود
**راه حل:**
- بررسی conversation history
- بررسی system prompts

## دستورات سریع برای بررسی

```bash
# 1. بررسی secret_key
PGPASSWORD='Sedi2025!SecurePass' psql -h localhost -U sedi_user -d sedi_db -c "SELECT id, name, secret_key FROM users WHERE id=1;"

# 2. بررسی memory
PGPASSWORD='Sedi2025!SecurePass' psql -h localhost -U sedi_user -d sedi_db -c "SELECT COUNT(*) FROM memory WHERE user_id=1;"

# 3. تست با secret_key صحیح (بعد از بررسی)
curl -X POST "http://localhost:8000/interact/chat?message=Hello&name=testuser&secret_key=ACTUAL_SECRET_KEY&lang=en" | python3 -m json.tool
```

