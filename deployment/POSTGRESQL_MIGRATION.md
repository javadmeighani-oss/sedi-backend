# PostgreSQL Migration Guide - Sedi Backend

## خلاصه

این راهنما برای جایگزینی SQLite با PostgreSQL در Sedi Backend است.

**نکته مهم:** این migration یک **FRESH START** است. داده‌های SQLite موجود migrate نمی‌شوند.

---

## مراحل Migration

### مرحله 1: نصب PostgreSQL (سرور)

دو روش دارید:

#### روش 1: استفاده از اسکریپت خودکار

```bash
# کپی اسکریپت به سرور
scp deployment/postgresql-setup.sh root@91.107.168.130:/tmp/

# اجرای اسکریپت
ssh root@91.107.168.130
chmod +x /tmp/postgresql-setup.sh
/tmp/postgresql-setup.sh
```

#### روش 2: نصب دستی

راهنمای کامل در فایل `deployment/postgresql-setup-manual.md` موجود است.

---

### مرحله 2: به‌روزرسانی Dependencies (سرور)

```bash
cd /var/www/sedi/backend
source .venv/bin/activate
pip install psycopg2-binary
# یا
pip install -r requirements.txt
```

---

### مرحله 3: به‌روزرسانی کد (محلی)

کدها قبلاً به‌روزرسانی شده‌اند:
- ✅ `app/database.py` - استفاده از PostgreSQL
- ✅ `requirements.txt` - اضافه شدن `psycopg2-binary`

**Commit و Push:**

```bash
git add app/database.py requirements.txt deployment/
git commit -m "Migrate from SQLite to PostgreSQL"
git push
```

---

### مرحله 4: به‌روزرسانی در سرور

```bash
# در سرور
cd /var/www/sedi/backend
git pull

# نصب dependencies
source .venv/bin/activate
pip install -r requirements.txt
```

---

### مرحله 5: تنظیم Environment Variable (سرور)

```bash
# ویرایش .env
nano /var/www/sedi/backend/.env
```

اضافه کردن:

```env
DATABASE_URL=postgresql+psycopg2://sedi_user:your_password@localhost:5432/sedi_db
```

---

### مرحله 6: به‌روزرسانی Systemd Service (سرور)

```bash
# کپی فایل service جدید
cat > /etc/systemd/system/sedi-backend.service << 'EOF'
[Unit]
Description=Sedi FastAPI Backend Service
After=network-online.target postgresql.service
Wants=network-online.target
Requires=postgresql.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/var/www/sedi/backend
Environment="PATH=/var/www/sedi/backend/.venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/var/www/sedi/backend/.env
ExecStart=/var/www/sedi/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# بارگذاری مجدد systemd
systemctl daemon-reload
```

---

### مرحله 7: راه‌اندازی مجدد و بررسی

```bash
# راه‌اندازی مجدد
systemctl restart sedi-backend

# بررسی وضعیت
systemctl status sedi-backend --no-pager

# بررسی لاگ‌ها
journalctl -u sedi-backend -n 30 --no-pager

# تست API
curl http://localhost:8000/
```

---

## بررسی Migration

### بررسی جداول در PostgreSQL

```bash
sudo -u postgres psql -d sedi_db -c "\dt"
```

باید جداول زیر را ببینید:
- `users`
- `memory`
- `notifications`

### بررسی اتصال

```bash
# تست اتصال
sudo -u postgres psql -d sedi_db -c "SELECT version();"
```

---

## Rollback (در صورت نیاز)

اگر نیاز به بازگشت به SQLite دارید:

```bash
# 1. بازگردانی database.py
git checkout HEAD~1 app/database.py

# 2. حذف DATABASE_URL از .env
nano /var/www/sedi/backend/.env
# حذف خط DATABASE_URL

# 3. راه‌اندازی مجدد
systemctl restart sedi-backend
```

---

## تغییرات انجام شده

### فایل‌های تغییر یافته:
- `app/database.py` - جایگزینی SQLite با PostgreSQL
- `requirements.txt` - اضافه شدن `psycopg2-binary`
- `deployment/sedi-backend.service` - وابستگی به PostgreSQL

### فایل‌های جدید:
- `deployment/postgresql-setup.sh` - اسکریپت نصب خودکار
- `deployment/postgresql-setup-manual.md` - راهنمای نصب دستی
- `deployment/POSTGRESQL_MIGRATION.md` - این فایل

---

## نکات مهم

1. **داده‌های SQLite migrate نمی‌شوند** - این یک fresh start است
2. **پسورد PostgreSQL را ایمن نگه دارید**
3. **فایل `.env` را محافظت کنید**: `chmod 600 .env`
4. **پشتیبان‌گیری منظم**: `sudo -u postgres pg_dump sedi_db > backup.sql`

---

## پشتیبانی

در صورت بروز مشکل:
1. بررسی لاگ‌ها: `journalctl -u sedi-backend -f`
2. بررسی وضعیت PostgreSQL: `systemctl status postgresql`
3. بررسی اتصال: `sudo -u postgres psql -d sedi_db`

