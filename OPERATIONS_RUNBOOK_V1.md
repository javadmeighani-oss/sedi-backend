# Runbook عملیاتی V1 (مارکت)

این Runbook برای عملیات روزانه V1 نوشته شده است: چک سریع سلامت سرویس، مسیر Incident، ری‌استارت امن، بکاپ دیتابیس، و رصد حداقلی بدون دخالت در قراردادهای public.

---

## 1) Endpoints پایش

### مسیرها

- `GET /healthz`
- `GET /health`
- `GET /ops/status` (نیازمند هدر `X-ADMIN-TOKEN`)

### نمونه دستور

```bash
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8000/health
curl -sS -H "X-ADMIN-TOKEN: <ADMIN_TOKEN>" http://127.0.0.1:8000/ops/status | python3 -m json.tool
```

نکته: `ops/status` برای مانیتورینگ حداقلی عملیاتی است و secrets را برنمی‌گرداند.

---

## 2) چک‌های روزانه (Daily Checklist)

هر روز این 4 مورد را سریع چک کنید:

1. سرویس فعال است؟
   ```bash
   sudo systemctl is-active sedi-backend
   ```
2. latency دیتابیس در `ops/status` غیرعادی نیست؟
3. مقدار `notifications_pending` رشد غیرعادی ندارد؟
4. مقدار `device_events_24h` برای مدت طولانی صفر نیست (اگر انتظار دریافت دیتا دارید)؟

---

## 3) Incident Flow (۵ دقیقه اول)

در ۵ دقیقه اول Incident این ترتیب را اجرا کنید:

1. وضعیت سرویس:
   ```bash
   sudo systemctl status sedi-backend --no-pager
   ```
2. لاگ‌های فوری:
   ```bash
   sudo journalctl -u sedi-backend -n 200 --no-pager
   sudo journalctl -u sedi-backend --since "10 minutes ago" --no-pager
   ```
   برای جزئیات بیشتر به `HOW_TO_CHECK_LOGS.md` مراجعه کنید.
3. چک health و ops:
   ```bash
   curl -sS http://127.0.0.1:8000/healthz
   curl -sS http://127.0.0.1:8000/health
   curl -sS -H "X-ADMIN-TOKEN: <ADMIN_TOKEN>" http://127.0.0.1:8000/ops/status | python3 -m json.tool
   ```
4. بررسی env فرآیند (برای تطبیق runtime):
   ```bash
   PID="$(pgrep -f 'uvicorn backend\.app\.main:app' | head -n 1)"
   sudo tr '\0' '\n' < "/proc/${PID}/environ" | egrep '^(DATABASE_URL|DEVICE_AUTH_MODE|APP_TIMEZONE|FCM_DISABLED)='
   ```

---

## 4) Restart امن + Verify

ری‌استارت مرحله‌ای:

```bash
sudo systemctl daemon-reload
sudo systemctl restart sedi-backend
sudo systemctl is-active sedi-backend
```

Verify سریع بعد از ری‌استارت:

```bash
curl -sS http://127.0.0.1:8000/healthz
curl -sS -H "X-ADMIN-TOKEN: <ADMIN_TOKEN>" http://127.0.0.1:8000/ops/status | python3 -m json.tool
```

Verify env فرآیند:

```bash
sudo tr "\0" "\n" < /proc/$(pgrep -f "uvicorn backend\.app\.main:app" | head -n 1)/environ | egrep "^(DEVICE_AUTH_MODE|APP_TIMEZONE|FCM_DISABLED)="
```

---

## 5) بکاپ DB (pg_dump) + Retention

فقط دستورالعمل عملیاتی (بدون تغییر سیستم):

1. ساخت مسیر امن بکاپ:
   ```bash
   sudo mkdir -p /var/backups/sedi
   sudo chown root:root /var/backups/sedi
   sudo chmod 700 /var/backups/sedi
   ```
2. ساخت بکاپ با timestamp:
   ```bash
   TS="$(date +%F_%H-%M-%S)"
   sudo -u postgres pg_dump -Fc -d sedi_db -f "/var/backups/sedi/sedi_db_${TS}.dump"
   ```
3. sanity check:
   ```bash
   sudo -u postgres pg_restore --list "/var/backups/sedi/sedi_db_${TS}.dump" | head
   ```
4. retention پیشنهادی (نگه‌داری 14 بکاپ آخر):
   ```bash
   ls -1t /var/backups/sedi/sedi_db_*.dump | tail -n +15 | xargs -r sudo rm -f
   ```

---

## 6) مانیتورینگ حداقلی (اختیاری، فقط دستورالعمل)

### گزینه A: cron هر 5 دقیقه

```cron
*/5 * * * * curl -sS -H "X-ADMIN-TOKEN: <ADMIN_TOKEN>" http://127.0.0.1:8000/ops/status >> /var/log/sedi_ops_status.log
```

### گزینه B: systemd timer

- یک service/timer ساده طراحی کنید که هر 5 دقیقه `curl /ops/status` را اجرا کند و خروجی را در لاگ بنویسد.
- در این Runbook فایل یا unit جدید ساخته نمی‌شود؛ فقط guideline ارائه شده است.

نکته امنیتی: اگر endpoint روی شبکه public قابل دسترس است، reverse proxy + محدودسازی IP (allowlist) اعمال شود.

---

## 7) فیدبک و رصد حداقلی (Queryهای آماده)

اگر جدول `notification_feedback` یا مشابه دارید، این کوئری‌ها برای snapshot سریع مفید هستند:

```bash
sudo -u postgres psql -d sedi_db -c "select action, count(*) from notification_feedback where created_at >= now() - interval '24 hours' group by action order by count(*) desc;"
sudo -u postgres psql -d sedi_db -c "select count(*) as feedback_24h from notification_feedback where created_at >= now() - interval '24 hours';"
sudo -u postgres psql -d sedi_db -c "select date_trunc('hour', created_at) as h, count(*) from notification_feedback where created_at >= now() - interval '24 hours' group by 1 order by 1;"
```

اگر جدول feedback موجود نیست، رصد generic زیر را اجرا کنید:

```bash
sudo -u postgres psql -d sedi_db -c "select count(*) from notifications where status='failed' and created_at >= now() - interval '24 hours';"
sudo -u postgres psql -d sedi_db -c "select count(*) from notifications where status='pending';"
sudo -u postgres psql -d sedi_db -c "select count(*) from device_events where coalesce(recorded_at, received_at) >= now() - interval '24 hours';"
```

Fallback در اسکیماهای متفاوت:

- اگر `notifications.status` ندارید ولی `is_sent` دارید:
  ```bash
  sudo -u postgres psql -d sedi_db -c "select count(*) from notifications where is_sent=false;"
  ```
- اگر `device_events.recorded_at` خالی/غایب است:
  ```bash
  sudo -u postgres psql -d sedi_db -c "select count(*) from device_events where received_at >= now() - interval '24 hours';"
  ```

---

## 8) لینک‌های مرتبط

- `HOW_TO_CHECK_LOGS.md`
- `BACKEND_RESTART_INSTRUCTIONS.md`
- `README_DEPLOYMENT.md`

