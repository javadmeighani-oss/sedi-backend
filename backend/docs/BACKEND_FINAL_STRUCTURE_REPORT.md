# گزارش کامل ساختار نهایی بک‌اند Sedi

**نسخه:** ۲.۰.۱  
**تاریخ گزارش:** ۲۰۲۵-۰۲-۰۷  
**Entrypoint پروداکشن:** `backend.app.main:app`

---

## ۱) نمای کلی

بک‌اند یک API مبتنی بر **FastAPI** است با دیتابیس **PostgreSQL**، زمان‌بند (**APScheduler**) برای اعلان‌ها، و موتور تصمیم‌گیری برای رویدادهای سلامتی. تمام کد اصلی در پکیج **`backend.app`** قرار دارد؛ در ریشهٔ ریپو یک **shim** در `app/main.py` برای سازگاری با `uvicorn app.main:app` وجود دارد.

---

## ۲) ساختار دایرکتوری (نهایی)

```
backend/
├── .github/workflows/
│   ├── deploy-backend.yml      # دیپلوی به سرور روی push به main
│   └── build-frontend.yml     # بیلد فرانت
├── app/                        # کد اصلی بک‌اند (canonical)
│   ├── main.py                 # اپ FastAPI، روت‌ها، CORS، scheduler
│   ├── database.py             # engine, SessionLocal, get_db, Base
│   ├── models.py               # مدل‌های SQLAlchemy
│   ├── deps.py                 # وابستگی‌های مشترک
│   ├── core/
│   │   ├── scheduler.py        # زمان‌بند اعلان‌ها، تحویل، دارو، دستگاه
│   │   ├── security.py         # JWT، توکن
│   │   ├── passkey_utils.py    # هش/تأیید passkey
│   │   ├── device_auth.py     # احراز هویت دستگاه
│   │   ├── ai_text_engine.py   # تولید متن با GPT
│   │   ├── gpt_engine.py
│   │   └── conversation/       # چت، حافظه، مراحل، پرامپت‌ها
│   │       ├── brain.py
│   │       ├── memory.py
│   │       ├── context.py
│   │       ├── stages.py
│   │       ├── prompts.py
│   │       ├── name_database.py
│   │       ├── question_database.py
│   │       └── sedi_knowledge_base.py
│   ├── decision_engine/        # ارزیابی رویداد، قوانین، اقدامات
│   │   ├── __init__.py
│   │   ├── models.py          # EventDto, CreateHealthAlertAction, ...
│   │   ├── rules.py
│   │   └── service.py         # evaluate_event, decide_from_event
│   ├── routers/               # API endpoints
│   │   ├── __init__.py
│   │   ├── auth.py            # /auth
│   │   ├── auth_login.py   # LEGACY — disabled; Stage 25 OTP only
│   │   ├── interact.py        # /interact (چت، معرفی، onboarding)
│   │   ├── health.py          # /health
│   │   ├── lifestyle.py       # /lifestyle
│   │   ├── notifications.py   # /notifications
│   │   ├── ai_core.py         # /ai_core
│   │   ├── conditions.py      # /conditions
│   │   ├── device.py          # /device (ingest رویداد دستگاه)
│   │   ├── devices.py         # /devices (ثبت دستگاه)
│   │   ├── decision.py        # decision engine API
│   │   ├── data.py
│   │   ├── medical.py
│   │   ├── memory.py
│   │   ├── sms_gateway.py
│   │   ├── device_data.py
│   │   └── system.py          # GET /health (Freeze B1 – production monitoring)
│   ├── schemas/               # Pydantic (درخواست/پاسخ)
│   │   ├── __init__.py
│   │   ├── common.py          # APIResponse, ErrorInfo
│   │   ├── chat.py
│   │   ├── device.py
│   │   ├── devices.py
│   │   ├── health.py
│   │   ├── lifestyle.py
│   │   ├── medical.py
│   │   ├── memory.py
│   │   ├── notification.py
│   │   ├── onboarding.py
│   │   ├── interaction.py
│   │   └── user.py
│   └── services/
│       ├── notification_engine.py   # DecisionEngine, NotificationBuilder
│       ├── device_ingestion.py     # ingest_event، محدودیت نرخ
│       ├── medical.py              # MedicalService
│       ├── rag.py                  # RAGService
│       ├── memory/
│       │   ├── memory_repository.py
│       │   ├── memory_context.py
│       │   └── memory_contract.py
│       ├── notification_runtime/   # متن اعلان، fallback، زبان، AI
│       │   ├── fallback_generator.py
│       │   ├── ai_enhancer.py
│       │   └── language_resolver.py
│       ├── notifications/
│       │   └── delivery_service.py # تحویل اعلان (outbox)
│       └── vitals/
│           ├── vital_registry.py   # اعتبارسنجی، dedupe، نگاشت به memory
│           ├── dedupe.py
│           └── rule_alerts.py      # compute_alert_actions
├── deployment/
│   ├── sedi-backend.service   # قالب systemd (backend.app.main:app)
│   ├── deploy.sh
│   ├── migrations/            # اسکریپت‌های SQL و apply
│   └── ... (مستندات و اسکریپت‌های راه‌اندازی)
├── docs/                      # مستندات (شامل این گزارش)
├── tests/
│   ├── acceptance/
│   │   └── test_release_d.py  # تست acceptance رلیز D
│   ├── test_decision_engine.py
│   ├── test_device_ingestion_c1.py
│   ├── test_devices_c2.py
│   ├── test_notification_*.py
│   ├── test_vital_registry_c3.py
│   └── ...
├── requirements.txt
├── Procfile
└── README.md
```

**نکته:** در ریپوی Demo یک پوشهٔ تو در تو `backend/backend/` هم وجود دارد (کپی قدیمی). کد اصلی و قالب پروداکشن همان **`backend/app`** و **`backend/deployment`** است.

---

## ۳) Entrypoint و نحوهٔ اجرا

| محیط | دستور / تنظیم |
|------|-----------------|
| **پروداکشن (systemd)** | `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000` با `WorkingDirectory=/var/www/sedi/backend` و `PYTHONPATH=/var/www/sedi` |
| **توسعه (مستقیم)** | از ریشهٔ ریپو: `PYTHONPATH=<repo_root> uvicorn backend.app.main:app --reload` |
| **سازگاری (شیم)** | `app/main.py` در ریشه فقط `app` را از `backend.app.main` re-export می‌کند؛ با `uvicorn app.main:app` همان اپ بالا می‌آید (با PYTHONPATH ریشه). |

در تمام قالب‌های deployment و مستندات فقط **`backend.app.main:app`** استفاده شده است؛ **`--app-dir`** و **`app.main:app`** حذف شده‌اند.

---

## ۴) لایه‌های اپلیکیشن

### ۴.۱ روت‌ها (API)

- **`/auth`** — احراز هویت (passkey و غیره)
- **`/auth/login`** — درخواست/تأیید PIN
- **`/interact`** — معرفی کاربر، چت، onboarding
- **`/health`** — دادهٔ سلامتی (افزودن، تحلیل)
- **`/lifestyle`** — دادهٔ سبک زندگی
- **`/notifications`** — ایجاد/لیست اعلان، feedback، `deliver_pending`
- **`/ai_core`** — تحلیل سلامت با AI
- **`/conditions`** — شرایط پزشکی و UserCondition
- **`/device`** — ingest رویداد دستگاه (با احراز هویت دستگاه)
- **`/devices`** — ثبت و مدیریت دستگاه
- **`/decision`** — API موتور تصمیم‌گیری
- **`/data`**, **`/medical`**, **`/memory`**, **`/device_data`**, **`/sms_gateway`** — endpoints مرتبط

### ۴.۲ سرویس‌ها و موتورها

- **notification_engine:** تصمیم برای ساخت اعلان، ساخت payload، زمان‌بندی.
- **device_ingestion:** دریافت رویداد دستگاه، اعتبارسنجی، dedupe، تصمیم‌گیری، اعلان.
- **decision_engine:** ارزیابی رویداد (مثلاً ضربان غیرعادی)، قوانین، تولید اقدامات (اعلان و غیره).
- **vitals (vital_registry, rule_alerts):** اعتبارسنجی ویتال، dedupe، نگاشت به حافظه، قوانین هشدار.
- **notifications/delivery_service:** تحویل اعلان‌های ارسال‌نشده (outbox).
- **memory:** MemoryRepository، MemoryContext، قرارداد دامنه/کلید.
- **conversation (core):** چت، حافظه مکالمه، مراحل، پرامپت‌ها، دانش Sedi.

### ۴.۳ زمان‌بند (scheduler)

- چک سلامت دوره‌ای، اعلان صبح، پینگ عدم فعالیت، تحویل اعلان‌های pending، دستگاه قطع، یادآوری دارو.

---

## ۵) مدل‌های دیتابیس (SQLAlchemy)

| مدل | جدول | توضیح کوتاه |
|-----|------|--------------|
| User | users | کاربر، نام، secret_key، زبان |
| Memory | memory | پیام/پاسخ چت |
| HealthData | health_data | ضربان قلب، دما، SpO2 |
| Notification | notifications | اعلان با type، body، priority، is_sent، sent_at، dedupe_key |
| MedicalCondition | medical_conditions | شرایط پزشکی (کد، نام، دسته) |
| Medication | medications | داروها |
| UserCondition | user_conditions | ارتباط کاربر–شرایط |
| UserMedication | user_medications | داروهای کاربر برای یادآوری |
| DailyMemorySummary | daily_memory_summaries | خلاصه روزانه |
| UserMemoryFact | user_memory_facts | حقایق حافظه (domain, key, value_json) |
| DeviceEvent | device_events | رویداد دستگاه (event_type، payload، dedupe_key) |
| Device | devices | دستگاه (device_id، token_hash، last_seen_at) |

---

## ۶) وابستگی‌ها (requirements.txt)

```
fastapi
uvicorn
pydantic
python-dotenv
openai
requests
passlib
bcrypt
python-jose
PyJWT==2.11.0
apscheduler
sqlalchemy
pytz
psycopg2-binary
```

---

## ۷) دیپلوی و CI/CD

### ۷.۱ systemd (پروداکشن)

- **فایل:** `backend/deployment/sedi-backend.service` (و کپی در `backend/backend/deployment/`).
- **ExecStart:**  
  `ExecStart=/var/www/sedi/backend/.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`
- **WorkingDirectory:** `/var/www/sedi/backend`
- **PYTHONPATH:** `/var/www/sedi` (ریشهٔ ریپو روی سرور).
- بدون **`--app-dir`**؛ وابسته به PostgreSQL.

### ۷.۲ GitHub Actions

- **Deploy Sedi Backend to Cloud Server**  
  - با push به `main` (و تغییر در `app/**`, `backend/**`, `requirements.txt`, `deployment/**` یا خود workflow).  
  - همگام‌سازی با سرور، نصب وابستگی‌ها از `requirements.txt`، ری‌استارت `sedi-backend.service`.
- **Backend acceptance tests**  
  - با push/PR به `main`.  
  - سرویس Postgres موقت، `PYTHONPATH=workspace` (ریشهٔ ریپو)، اجرای `backend/tests/acceptance/test_release_d.py`.

---

## ۸) تست‌ها

- **Acceptance (Release D):** `backend/tests/acceptance/test_release_d.py` — با اپ واقعی و DB موقت.
- **واحد/یکپارچه:** `test_decision_engine.py`, `test_device_ingestion_c1.py`, `test_devices_c2.py`, `test_notification_*.py`, `test_vital_registry_c3.py`, `test_e2e_abnormal_hr.py` و غیره.

اجرای acceptance از ریشهٔ ریپو:  
`PYTHONPATH=<repo_root> python -m pytest backend/tests/acceptance/test_release_d.py -v --tb=long`

---

## ۹) قواعد مهم کدنویسی

- **Import در `backend.app`:** برای سازگاری با CI و پروداکشن (PYTHONPATH=ریشهٔ ریپو)، ماژول‌های داخل `backend/app` از **`backend.app.*`** استفاده می‌کنند (مثلاً `from backend.app.models import ...`)، نه `from app.*`.
- **Entrypoint واحد:** پروداکشن و docs فقط **`backend.app.main:app`**؛ شیم `app.main:app` فقط برای سازگاری است.
- **دیتابیس:** متغیر محیطی `DATABASE_URL`؛ در CI از Postgres سرویس GitHub Actions استفاده می‌شود.

---

## ۱۰) خلاصه

| مورد | مقدار |
|------|--------|
| فریمورک | FastAPI |
| دیتابیس | PostgreSQL (SQLAlchemy) |
| Entrypoint | `backend.app.main:app` |
| پورت پیش‌فرض | 8000 |
| زمان‌بند | APScheduler (در-process) |
| احراز هویت | JWT، passkey، device token |
| تست acceptance | `backend/tests/acceptance/test_release_d.py` |
| دیپلوی | GitHub Actions → SSH به سرور، systemd `sedi-backend.service` |

این سند ساختار نهایی بک‌اند را تا تاریخ گزارش بالا به‌صورت متمرکز توصیف می‌کند.
