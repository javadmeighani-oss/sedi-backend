# دستورات Restart Backend

## وضعیت فعلی
Backend در حال حاضر در دسترس نیست (503 Server Unavailable) و نیاز به restart دارد.

## روش‌های Restart

### روش 1: SSH با Password
```powershell
ssh root@91.107.168.130 'cd /root/sedi-backend && git pull origin main && pkill -f uvicorn && sleep 2 && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &'
```
**نکته:** بعد از اجرای این دستور، از شما password خواسته می‌شود.

### روش 2: SSH با Key File
```powershell
ssh -i "C:\path\to\your\ssh-key.pem" root@91.107.168.130 'cd /root/sedi-backend && git pull origin main && pkill -f uvicorn && sleep 2 && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &'
```
**نکته:** مسیر SSH key خود را جایگزین کنید.

### روش 3: اگر systemctl service تعریف شده
```powershell
ssh root@91.107.168.130 'sudo systemctl restart sedi-backend'
```

### روش 4: Background Restart (با nohup)
```powershell
ssh root@91.107.168.130 'cd /root/sedi-backend && git pull origin main && pkill -f uvicorn && nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &'
```

## استفاده از اسکریپت

برای استفاده از اسکریپت PowerShell:
```powershell
cd backend/scripts
.\restart-backend.ps1
```

## تست اتصال بعد از Restart

```powershell
# تست ساده
Invoke-WebRequest -Uri "http://91.107.168.130:8000/"

# یا با نمایش محتوا
Invoke-WebRequest -Uri "http://91.107.168.130:8000/" | Select-Object -ExpandProperty Content
```

## اگر SSH در دسترس نیست

اگر نمی‌توانید از طریق SSH متصل شوید، باید:
1. از طریق پنل مدیریت سرور (cPanel, Plesk, etc.) دسترسی پیدا کنید
2. یا از طریق VNC/RDP به سرور متصل شوید
3. یا با مدیر سرور تماس بگیرید

## تنظیمات

اگر مسیر backend یا username متفاوت است، این مقادیر را در `restart-backend.ps1` تغییر دهید:
- `SERVER_USER`: نام کاربری SSH (پیش‌فرض: `root`)
- `BACKEND_PATH`: مسیر backend روی سرور (پیش‌فرض: `/root/sedi-backend`)

