# گزارش آخرین وضعیت ساختار فرانت‌اند و بک‌اند — Sedi

**تاریخ:** بهمن ۱۴۰۳  
**ورژن بک‌اند:** 2.0.1  
**ورژن اپ فرانت:** 1.0.0+2  

---

## ۱. فرانت‌اند (Flutter)

### ۱.۱ مسیر و پلتفرم‌ها
- **مسیر:** `frontend/` (در مخزن Demo)
- **پلتفرم‌ها:** Android، iOS، Web، Linux، macOS، Windows
- **SDK:** Flutter `>=3.0.0 <4.0.0`

### ۱.۲ وابستگی‌های اصلی (`pubspec.yaml`)
| بسته | کاربرد |
|------|--------|
| `firebase_core`, `firebase_messaging` | FCM و پوش |
| `flutter_local_notifications` | نمایش نوتیف در foreground |
| `shared_preferences` | پروفایل کاربر، توکن FCM |
| `provider` | state |
| `http` | API |
| `intl` | چندزبانگی |

### ۱.۳ ساختار `lib/`
```
lib/
├── main.dart                 # نقطه ورود، Firebase init، FCM setup، ثبت توکن
├── app.dart                  # MaterialApp، تم، home: IntroPage
├── core/
│   ├── auth/                 # auth_helper, auth_service
│   ├── config/               # app_config (baseUrl و...)
│   ├── navigation/           # app_navigator, navigatorKey
│   ├── network/              # api_client, api_error, api_response
│   ├── notifications/        # fcm_setup, local_notifications_service
│   ├── theme/                # app_theme
│   └── utils/                # user_profile_manager, brand_name, messages, ...
├── data/
│   ├── dto/                  # درخواست/پاسخ API (health, lifestyle, devices, ...)
│   ├── models/               # user_profile, notification, chat_message
│   └── repositories/         # chat, health, lifestyle, notification, devices
├── features/
│   ├── intro/                # IntroPage (ورود/مسیردهی)
│   ├── onboarding/           # OnboardingPage (ثبت نام + ذخیره پروفایل + ثبت توکن FCM)
│   ├── user_verification/     # UserVerificationPage (تکمیل پروفایل + ثبت توکن FCM)
│   ├── chat/                 # ChatPage, ChatController, chat_service
│   ├── health/               # vitals_page, vitals_controller, vitals_cache
│   ├── lifestyle/            # lifestyle_page, lifestyle_controller
│   ├── devices/              # devices_page, devices_controller
│   └── notification/         # notifications_inbox_page, notification_sync, notification_service
├── services/
│   └── push/
│       └── push_service.dart # saveTokenToPreferences, getTokenFromPreferences,
│                             # registerFcmTokenToBackend, tryRegisterStoredTokenAfterLogin
└── utils/                    # time_utils
```

### ۱.۴ جریان FCM و پوش
- **شروع اپ:** `Firebase.initializeApp()` → `_setupFcm()` → درخواست اجازه، `LocalNotificationsService.init`، `_registerTokenOnStart()` و گوش دادن به `onTokenRefresh`.
- **ثبت توکن:** در `_registerTokenOnStart()`: `getToken()` → لاگ ماسک‌شده → `saveTokenToPreferences(token)` → `registerFcmTokenToBackend(token)`. اگر `userId` نباشد، توکن فقط در prefs ذخیره می‌شود.
- **بعد از لاگین/onboarding:** در `OnboardingPage` و `UserVerificationPage` بعد از `UserProfileManager.saveProfile(profile)` فراخوانی `tryRegisterStoredTokenAfterLogin()` تا توکن ذخیره‌شده با backend ثبت شود.
- **Foreground:** `FirebaseMessaging.onMessage` → `LocalNotificationsService.showRemoteNotification`.
- **باز شدن از نوتیف:** `onMessageOpenedApp` / `getInitialMessage` → `_navigateToChatFromMessage` و ارسال feedback با `NotificationRepository.sendFeedback`.

### ۱.۵ CI/CD فرانت
- **Workflow:** `.github/workflows/build-frontend.yml` (در سطح Demo؛ ممکن است مسیر فرانت در مخزن جدا باشد).
- **خروجی:** ساخت APK اندروید (مثلاً برای نصب یا انتشار).

---

## ۲. بک‌اند (FastAPI + PostgreSQL)

### ۲.۱ مسیر و محیط
- **مسیر:** `backend/` (در مخزن Demo؛ ریموت اصلی: `javadmeighani-oss/sedi-backend`).
- **زبان:** Python، FastAPI، SQLAlchemy، PostgreSQL.
- **ورژن اپ:** 2.0.1

### ۲.۲ وابستگی‌های اصلی (`requirements.txt`)
| بسته | کاربرد |
|------|--------|
| `fastapi`, `uvicorn` | API و سرور |
| `sqlalchemy`, `psycopg2-binary` | دیتابیس |
| `alembic>=1.13.0` | مایگریشن اسکیما (تنها منبع ایجاد/تغییر جدول) |
| `pydantic` | اعتبارسنجی و schema |
| `openai` | GPT |
| `apscheduler` | زمان‌بندی نوتیفیکیشن |
| `google-auth` | FCM |
| `python-jose`, `PyJWT`, `passlib`, `bcrypt` | احراز هویت |

### ۲.۳ ساختار `backend/app/`
```
app/
├── main.py              # FastAPI app، CORS، روت‌ها، start_scheduler — بدون create_all
├── database.py          # engine, Base, SessionLocal, get_db؛ DATABASE_URL از env
├── models.py            # مدل‌های SQLAlchemy (User, Memory, HealthData, Notification, PushDevice, ...)
├── deps.py              # وابستگی‌های مشترک
├── db/                  # فقط __init__.py (ماژول schema_sync حذف شده)
├── routers/
│   ├── auth.py          # احراز هویت
│   ├── interact.py      # چت، onboarding
│   ├── health.py        # سلامت
│   ├── lifestyle.py     # سبک زندگی
│   ├── notifications.py # نوتیف، پوش (register/unregister توکن، feedback، send_now)
│   ├── device.py        # device ingest
│   ├── devices.py       # لیست/ثبت دستگاه
│   ├── ai_core.py       # هسته AI
│   ├── conditions.py    # شرایط پزشکی
│   ├── decision.py      # موتور تصمیم
│   ├── memory.py        # حافظه
│   └── user_knowledge.py # دانش کاربر
├── schemas/             # Pydantic برای request/response
├── core/
│   ├── conversation/    # brain, context, memory, prompts, sedi_knowledge_base
│   ├── scheduler.py     # زمان‌بندی نوتیف
│   ├── gpt_engine.py    # GPT
│   └── ...
├── services/
│   ├── notification_engine.py
│   ├── notification_runtime/  # renderer, rag_provider, quiet_hours, ...
│   ├── notifications/   # delivery_service, fcm_client
│   ├── local_rag/       # RAG و vector
│   ├── lifestyle/       # fact_extractor, summary_service
│   ├── memory/          # memory_context, memory_repository
│   └── vitals/          # vital_registry, rule_alerts
└── decision_engine/     # قوانین و سرویس تصمیم
```

### ۲.۴ دیتابیس و مایگریشن
- **تنها منبع اسکیما:** Alembic. هیچ `Base.metadata.create_all` در `main.py` یا در startup وجود ندارد.
- **پیکربندی Alembic:**
  - `backend/alembic.ini`: `script_location = alembic`، بدون URL ثابت (URL از env در `env.py`).
  - `backend/alembic/env.py`: بارگذاری `DATABASE_URL` از env، استفاده از `Base.metadata` و `engine` از `backend.app.database`؛ در صورت نبود `DATABASE_URL` خطای واضح.
- **باسلاین:** `backend/alembic/versions/001_baseline_v1_schema.py` (revision: `001_baseline_v1`) — ایجاد تمام جداول مدل‌های فعلی؛ downgrade حذف همان جداول.
- **دستورات پرکاربرد:**
  - ایجاد revision: `cd backend && alembic revision --autogenerate -m "توضیح"`
  - اعمال مایگریشن: `cd backend && alembic upgrade head`
  - ریست اسکیما (فقط محیط بدون داده واقعی): `CONFIRM_RESET=YES ./backend/scripts/reset_db_and_migrate.sh`
- **مستندات:** `backend/docs/MIGRATIONS.md` (شامل playbook سرور برای Fresh DB و نکته Safety).

### ۲.۵ APIهای مهم برای فرانت
| مسیر | کاربرد |
|------|--------|
| `/auth/*` | لاگین و توکن |
| `/interact/*` | چت، onboarding |
| `/health/*` | داده سلامت |
| `/lifestyle/*` | سبک زندگی |
| `/notifications/*` | لیست نوتیف، feedback، پوش (register/unregister)، send_now |
| `/device/*` | ingest دستگاه |
| `/devices/*` | ثبت و لیست دستگاه‌ها |
| `/memory/*` | حافظه مکالمه |
| `/user/*` | دانش/پروفایل کاربر |

### ۲.۶ CI/CD بک‌اند
- **Deploy:** `.github/workflows/deploy-backend.yml`
  - تریگر: پوش به `main` با تغییر در `backend/**`, `app/**`, `requirements.txt`, `deployment/**` یا خود workflow.
  - مراحل: checkout، SSH به سرور (مثلاً 91.107.168.130)، همگام‌سازی با `origin/main` در `/var/www/sedi/backend`، نصب وابستگی‌ها، ریستارت `sedi-backend.service`، تست API.
- **تست:** `ci-backend-tests.yml` برای اجرای تست‌های بک‌اند.

---

## ۳. هماهنگی فرانت–بک

- **Base URL:** فرانت از `AppConfig.baseUrl` استفاده می‌کند؛ بک همان دامنه/پورت را سرو می‌کند.
- **پوش:** فرانت توکن FCM را با `NotificationRepository.registerToken(userId, fcmToken, appVersion)` ثبت می‌کند؛ بک در `/notifications/push/register` ذخیره و در ارسال از همان توکن استفاده می‌کند.
- **نوتیفیکیشن:** بک نوتیف را ایجاد و از FCM ارسال می‌کند؛ فرانت feedback (مثل open_chat) را با `sendFeedback` می‌فرستد و از payload برای باز کردن چت استفاده می‌کند.
- **احراز هویت:** بک JWT/توکن صادر می‌کند؛ فرانت در `ApiClient` یا همان لایه شبکه هدر احراز را قرار می‌دهد (طبق `api_client.dart` و روترهای auth).

---

## ۴. خلاصه آخرین تغییرات مهم

| بخش | وضعیت |
|-----|--------|
| فرانت | FCM: ثبت توکن در شروع و بعد از لاگین/onboarding؛ ذخیره در prefs؛ `tryRegisterStoredTokenAfterLogin()` در Onboarding و UserVerification. |
| بک | حذف `schema_sync` و `create_all`؛ اسکیما فقط با Alembic؛ باسلاین v1؛ مایگریشن و playbook و اسکریپت ریست در `MIGRATIONS.md` و `reset_db_and_migrate.sh`. |
| دیتابیس | تمام جداول (users, memory, health_data, notifications, push_devices, notification_feedback, medical_conditions, medications, user_conditions, user_medications, daily_memory_summaries, user_memory_facts, device_events, devices, user_profile_knowledge, user_fact_candidates, user_facts) در یک revision باسلاین تعریف شده‌اند. |

---

## ۵. مخازن و ریموت‌ها (در سطح Demo)

- **origin:** `javadmeighani-oss/sedi-backend` (پوش بک‌اند و فرانت در این مخزن یکپارچه انجام می‌شود).
- **frontend (اختیاری):** `javadmeighani-oss/sedi-frontend` در صورت استفاده از مخزن جدا برای فرانت.

این گزارش با ساختار فعلی پروژه و آخرین تغییرات (تا زمان تهیه گزارش) همخوان است.
