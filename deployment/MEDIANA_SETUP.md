# فعال‌سازی ارسال OTP با Mediana

Production backend از Docker Compose و env در `/etc/sedi/sedi-backend.env` استفاده می‌کند.

## روش ۱: اسکریپت (SSH)

```powershell
$env:SEDI_SSH_HOST = "root@your-server"
$env:SEDI_DEPLOY_PATH = "/opt/sedi"   # مسیر compose روی سرور
$env:MEDIANA_API_KEY = "your-api-key-from-mediana-panel"
$env:MEDIANA_OTP_PATTERN_CODE = "your-otp-pattern-code"
.\deployment\setup_sms_on_server.ps1
```

کلید API را هرگز در ریپوزیتوری commit نکنید.

## روش ۲: دستی روی سرور

### ۱. ویرایش env

```bash
sudo nano /etc/sedi/sedi-backend.env
```

### ۲. مقادیر OTP/SMS

```
SMS_DISABLED=false
SMS_PROVIDER=mediana
MEDIANA_API_KEY=your-api-key-from-mediana-panel
MEDIANA_OTP_PATTERN_CODE=your-otp-pattern-code
```

### ۳. recreate کانتینر backend

```bash
cd "$SEDI_DEPLOY_PATH"
SEDI_IMAGE_TAG=<commit-sha> docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
```

### ۴. بررسی

```bash
docker logs --tail 50 sedi-backend
curl -s http://127.0.0.1:8000/healthz
```

با `X-ADMIN-TOKEN` معتبر: `GET /ops/config/sms` باید `MEDIANA_API_KEY=set` و `MEDIANA_OTP_PATTERN_CODE=set` نشان دهد (بدون نمایش مقدار secret).

---

**توجه:** Kavenegar دیگر پشتیبانی نمی‌شود. `SMS_PROVIDER` باید `mediana` باشد.
