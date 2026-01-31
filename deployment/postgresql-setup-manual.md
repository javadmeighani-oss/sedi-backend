# راهنمای نصب و تنظیم PostgreSQL برای Sedi Backend

## پیش‌نیازها
- دسترسی root به سرور Ubuntu 22.04
- دسترسی به `/var/www/sedi/backend`

---

## مرحله 1: نصب PostgreSQL

```bash
# به‌روزرسانی package list
apt-get update

# نصب PostgreSQL
apt-get install -y postgresql postgresql-contrib

# راه‌اندازی و فعال‌سازی سرویس
systemctl start postgresql
systemctl enable postgresql

# بررسی وضعیت
systemctl status postgresql
```

---

## مرحله 2: ایجاد Database و User

```bash
# ورود به PostgreSQL به عنوان کاربر postgres
sudo -u postgres psql
```

در PostgreSQL shell:

```sql
-- ایجاد کاربر
CREATE USER sedi_user WITH PASSWORD 'your_strong_password_here';

-- ایجاد دیتابیس
CREATE DATABASE sedi_db OWNER sedi_user;

-- اعطای دسترسی‌ها
GRANT ALL PRIVILEGES ON DATABASE sedi_db TO sedi_user;

-- اتصال به دیتابیس
\c sedi_db

-- اعطای دسترسی‌های schema
GRANT ALL ON SCHEMA public TO sedi_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO sedi_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO sedi_user;

-- خروج
\q
```

---

## مرحله 3: تنظیم Environment Variable

```bash
# رفتن به پوشه پروژه
cd /var/www/sedi/backend

# ویرایش فایل .env
nano .env
```

اضافه کردن این خط (پسورد را جایگزین کنید):

```env
DATABASE_URL=postgresql+psycopg2://sedi_user:your_strong_password_here@localhost:5432/sedi_db
```

یا به صورت مستقیم:

```bash
echo "DATABASE_URL=postgresql+psycopg2://sedi_user:your_strong_password_here@localhost:5432/sedi_db" >> /var/www/sedi/backend/.env
```

---

## مرحله 4: نصب Dependencies

```bash
# فعال‌سازی virtual environment
cd /var/www/sedi/backend
source .venv/bin/activate

# نصب psycopg2-binary
pip install psycopg2-binary

# یا نصب همه requirements
pip install -r requirements.txt
```

---

## مرحله 5: راه‌اندازی مجدد سرویس

```bash
# راه‌اندازی مجدد
systemctl restart sedi-backend

# بررسی وضعیت
systemctl status sedi-backend --no-pager

# بررسی لاگ‌ها
journalctl -u sedi-backend -n 30 --no-pager
```

---

## مرحله 6: بررسی و تست

```bash
# تست API
curl http://localhost:8000/

# بررسی اتصال به دیتابیس
sudo -u postgres psql -d sedi_db -c "\dt"
```

---

## دستورات مفید PostgreSQL

```bash
# ورود به PostgreSQL
sudo -u postgres psql

# ورود به دیتابیس خاص
sudo -u postgres psql -d sedi_db

# مشاهده جداول
sudo -u postgres psql -d sedi_db -c "\dt"

# مشاهده کاربران
sudo -u postgres psql -c "\du"

# پشتیبان‌گیری
sudo -u postgres pg_dump sedi_db > sedi_backup.sql

# بازگردانی
sudo -u postgres psql sedi_db < sedi_backup.sql
```

---

## عیب‌یابی

### مشکل: "password authentication failed"
```bash
# بررسی تنظیمات pg_hba.conf
nano /etc/postgresql/*/main/pg_hba.conf

# اطمینان از اینکه این خط وجود دارد:
# local   all             all                                     peer
# host    all             all             127.0.0.1/32            md5

# راه‌اندازی مجدد PostgreSQL
systemctl restart postgresql
```

### مشکل: "could not connect to server"
```bash
# بررسی وضعیت سرویس
systemctl status postgresql

# بررسی پورت
netstat -tlnp | grep 5432
```

---

## امنیت

- پسورد قوی برای `sedi_user` استفاده کنید
- فقط اتصال‌های localhost را مجاز کنید (پیش‌فرض)
- فایل `.env` را محافظت کنید: `chmod 600 .env`

