# گزارش آخرین تغییرات بک‌اند (Stage 3 و مرتبط)

**تاریخ:** ۲۰۲۵-۰۲-۰۷  
**هدف:** یکپارچه‌سازی entrypoint پروداکشن، حذف ارجاع به `app.main:app` در deployment، و تثبیت وابستگی PyJWT.

---

## ۱) خلاصه تغییرات

| بخش | توضیح |
|-----|--------|
| **Stage 3.1** | تبدیل `app/main.py` به compatibility shim؛ re-export از `backend.app.main:app` |
| **Stage 3.2** | حذف استفاده از `app.main:app` در تمام قالب‌ها و مستندات deployment |
| **Stage 3.3** | تثبیت PyJWT در requirements پروداکشن (`PyJWT==2.11.0`) |
| **Systemd** | قالب واحد systemd با `backend.app.main:app` و بدون `--app-dir` |

---

## ۲) فایل‌های تغییر یافته

### ۲.۱ اپلیکیشن (شیم و پکیج)
- **`app/main.py`** — فقط shim: `from backend.app.main import app`
- **`app/__init__.py`** — کامنت کوتاه برای canonical backend

### ۲.۲ وابستگی
- **`backend/requirements.txt`** — پین نسخه: `PyJWT==2.11.0`

### ۲.۳ قالب systemd
- **`backend/backend/deployment/sedi-backend.service`** — ExecStart: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000` (بدون `--app-dir`)
- سایر قالب‌های `.service` در `deployment/` و `backend/deployment/` از قبل با همین فرمت بودند.

### ۲.۴ مستندات و اسکریپت‌های deployment
در همهٔ موارد `uvicorn app.main:app` به `uvicorn backend.app.main:app` تغییر داده شد:

- **README.md**, **backend/README.md**
- **Procfile**, **backend/Procfile**, **backend/backend/Procfile**
- **scripts/restart-backend.ps1**, **scripts/RESTART_INSTRUCTIONS.md**
- **backend/scripts/restart-backend.ps1**, **backend/scripts/RESTART_INSTRUCTIONS.md**
- **backend/backend/scripts/restart-backend.ps1**, **backend/backend/scripts/RESTART_INSTRUCTIONS.md**
- **deployment/manual-deploy.md**, **deployment/POSTGRESQL_MIGRATION.md**
- **backend/deployment/manual-deploy.md**, **backend/deployment/POSTGRESQL_MIGRATION.md**
- **backend/backend/deployment/manual-deploy.md**, **backend/backend/deployment/POSTGRESQL_MIGRATION.md**
- **HOW_TO_CHECK_LOGS.md**, **backend/HOW_TO_CHECK_LOGS.md**, **backend/backend/HOW_TO_CHECK_LOGS.md**
- **PROJECT_DOCUMENTATION.md**, **backend/PROJECT_DOCUMENTATION.md**
- گزارش‌های اتصال و راهنما: **BACKEND_*_REPORT.md**, **BACKEND_*_INSTRUCTIONS.md**, **CONNECTION_*.md** (در روت و در **backend/**)

---

## ۳) نتیجه

- **Entrypoint پروداکشن:** فقط `backend.app.main:app` در قالب‌های systemd و docs.
- **شیم:** `uvicorn app.main:app` همان اپ `backend.app.main:app` را اجرا می‌کند (با PYTHONPATH مناسب).
- **جستجو:** `grep -R "uvicorn app.main:app"` در ریپو = ۰ نتیجه.
- **PyJWT:** پس از `pip install -r backend/requirements.txt`، `import jwt` و نسخهٔ ۲.۱۱.۰ در دسترس است.

---

## ۴) دیپلوی

با push به `main`، workflowهای زیر اجرا می‌شوند:

1. **Deploy Sedi Backend to Cloud Server** — همگام‌سازی با سرور، نصب requirements، ری‌استارت سرویس.
2. **Backend acceptance tests** — تست‌های acceptance با `backend.app.main:app` و PYTHONPATH ریشهٔ ریپو.

پس از push، در GitHub → Actions وضعیت هر دو را بررسی کنید.
