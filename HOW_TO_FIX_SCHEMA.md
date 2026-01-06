# How to Fix Schema Mismatch

اگر خطای "Required field is missing" دریافت می‌کنید، احتمالاً مشکل از **schema mismatch** است.

## تشخیص مشکل

ابتدا schema را بررسی کنید:

```bash
cd backend
python check_schema.py
```

اگر schema mismatch وجود دارد، این script آن را نشان می‌دهد.

## راه حل

### گزینه 1: Fix Schema Script (پیشنهادی)

این script جدول users را drop و recreate می‌کند:

```bash
cd backend
python fix_schema.py
```

**⚠️ هشدار:** این script **همه users موجود را حذف می‌کند!**

### گزینه 2: Manual Fix (اگر نمی‌خواهید users حذف شوند)

اگر نمی‌خواهید users حذف شوند، می‌توانید schema را manually fix کنید:

```sql
-- در PostgreSQL
ALTER TABLE users 
  ALTER COLUMN preferred_language SET NOT NULL,
  ALTER COLUMN preferred_language SET DEFAULT 'en',
  ALTER COLUMN created_at SET NOT NULL;
```

### گزینه 3: Migration (برای Production)

برای production، بهتر است از migration استفاده کنید:

```bash
# اگر Alembic دارید
alembic revision --autogenerate -m "fix users table schema"
alembic upgrade head
```

## بررسی بعد از Fix

بعد از fix، دوباره schema را بررسی کنید:

```bash
python check_schema.py
```

باید پیام "✅ Schema matches model perfectly!" را ببینید.

## Restart Backend

بعد از fix schema، backend را restart کنید:

```bash
# در سرور
sudo systemctl restart sedi-backend

# یا اگر local است
# Backend را restart کنید
```

## بررسی Logs

بعد از restart، لاگ‌ها را بررسی کنید:

```bash
# در سرور
sudo journalctl -u sedi-backend -f | grep -i "ONBOARDING"
```

باید ببینید که:
- User object با موفقیت ایجاد شده
- همه فیلدها set شده‌اند
- Transaction commit شده
- user_id برگردانده شده

