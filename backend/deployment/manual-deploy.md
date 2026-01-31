# دستورالعمل استقرار دستی Sedi Backend

## اطلاعات سرور
- **IP:** 91.107.168.130
- **OS:** Ubuntu 22.04
- **مسیر پروژه:** /var/www/sedi/backend
- **دستور اجرا:** uvicorn app.main:app --host 0.0.0.0 --port 8000

---

## مرحله 1: تنظیم SSH Key (در PowerShell محلی)

```powershell
# بررسی وجود کلید SSH
Test-Path ~\.ssh\id_ed25519

# اگر وجود ندارد، ایجاد کنید:
ssh-keygen -t ed25519 -C "sedi-backend" -f ~\.ssh\id_ed25519

# نمایش کلید عمومی
Get-Content ~\.ssh\id_ed25519.pub
```

---

## مرحله 2: کپی کلید به سرور

```powershell
# اتصال به سرور و کپی کلید
ssh-copy-id -i ~\.ssh\id_ed25519.pub ubuntu@91.107.168.130

# یا به صورت دستی:
ssh ubuntu@91.107.168.130
# سپس در سرور:
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
# محتویات id_ed25519.pub را paste کنید
chmod 600 ~/.ssh/authorized_keys
```

---

## مرحله 3: کپی فایل Service به سرور

```powershell
# از PowerShell در پوشه پروژه:
scp deployment\sedi-backend.service ubuntu@91.107.168.130:/tmp/sedi-backend.service
```

---

## مرحله 4: تنظیم Service در سرور

```powershell
# اتصال به سرور
ssh ubuntu@91.107.168.130
```

**دستورات در سرور:**

```bash
# انتقال فایل service
sudo mv /tmp/sedi-backend.service /etc/systemd/system/sedi-backend.service

# بررسی مسیر virtual environment
ls -la /var/www/sedi/backend/.venv/bin/uvicorn

# اگر مسیر متفاوت است، ویرایش کنید:
sudo nano /etc/systemd/system/sedi-backend.service
# مسیرها را اصلاح کنید

# بارگذاری مجدد systemd
sudo systemctl daemon-reload

# فعال‌سازی
sudo systemctl enable sedi-backend

# شروع سرویس
sudo systemctl start sedi-backend

# بررسی وضعیت
sudo systemctl status sedi-backend
```

---

## مرحله 5: بررسی و تست

```bash
# بررسی وضعیت
sudo systemctl status sedi-backend

# مشاهده لاگ‌ها
sudo journalctl -u sedi-backend -f

# تست دسترسی
curl http://localhost:8000/
curl http://91.107.168.130:8000/
```

---

## مرحله 6: به‌روزرسانی (Git Pull)

```bash
cd /var/www/sedi/backend
git pull
sudo systemctl restart sedi-backend
sudo systemctl status sedi-backend
```

---

## دستورات مفید

```bash
# راه‌اندازی مجدد
sudo systemctl restart sedi-backend

# توقف
sudo systemctl stop sedi-backend

# شروع
sudo systemctl start sedi-backend

# مشاهده لاگ
sudo journalctl -u sedi-backend -n 50
sudo journalctl -u sedi-backend -f

# بررسی خطاها
sudo journalctl -u sedi-backend -p err
```

