# گزارش آخرین تغییرات و ساختار فرانت‌اند و بک‌اند Sedi

**تاریخ گزارش:** ۱۴۰۳/۱۱/۲۲ (۲۰۲۵-۰۲-۱۱)  
**نسخه بک‌اند:** ۲.۰.۱  
**نسخه فرانت‌اند:** ۱.۰.۰+۲  
**ریپو:** Demo (Sedi Intelligent Health Assistant)

---

## بخش ۱ — آخرین تغییرات (خلاصه کامیت‌ها و وضعیت فعلی)

### ۱.۱ تغییرات اخیر فرانت‌اند

| مرحله / کامیت | توضیح |
|---------------|--------|
| **Stage 20 (Freeze ready)** | قفل برند، intro تأییدشده، آیکون اپ |
| **Stages 20.1A, 20.3, 20.4, 20.5** | آیکون اپ، onboarding فقط با username، رفع ۴۲۲ چت، قفل نام برند |
| **فرانت جدید** | صفحات ویتال‌ها، دستگاه‌ها، سبک زندگی، نوار ورودی، ممیزی UI |
| **ساختار فعلی** | فیچرهای health، devices، lifestyle، notification (inbox، sync)، ویجت‌های چت و انتخاب زبان |

### ۱.۲ تغییرات اخیر بک‌اند

| موضوع | توضیح |
|--------|--------|
| **Entrypoint** | استفاده از `backend.app.main:app` در systemd و CI؛ شیم `app.main` در ریشه برای سازگاری |
| **Importها** | همهٔ ماژول‌های داخل `backend/app` از `backend.app.*` استفاده می‌کنند (PYTHONPATH=ریشهٔ ریپو) |
| **Release D** | ستون `sent_at` و ایندکس‌ها برای notifications؛ تحویل اعلان (deliver_pending)؛ تست acceptance |
| **PyJWT** | نسخه ثابت `PyJWT==2.11.0` در requirements |
| **راوتِر device** | `/device` شامل: pending-commands، heartbeat، ingest (با احراز دستگاه)، و endpoints مرتبط |

### ۱.۳ وضعیت فریز و دیپلوی

- **بک‌اند:** در مرحله Post-Release D (Stage 3)؛ تغییرات فقط برای باگ‌فیک و هات‌فیک مجاز است.
- **فرانت‌اند:** آماده Freeze با برند قفل‌شده و آیکون اپ.
- **CI/CD:** دیپلوی بک‌اند با push به `main`؛ بیلد فرانت (Android)؛ تست acceptance با Postgres موقت.

---

## بخش ۲ — ساختار بک‌اند

### ۲.۱ نمای کلی

- **فریمورک:** FastAPI  
- **دیتابیس:** PostgreSQL (SQLAlchemy)  
- **زمان‌بند:** APScheduler (درون‌پردازه)  
- **Entrypoint پروداکشن:** `backend.app.main:app`  
- **پورت پیش‌فرض:** ۸۰۰۰  

کد اصلی در پکیج **`backend/app`** است.

### ۲.۲ ساختار دایرکتوری بک‌اند

```
backend/
├── app/
│   ├── main.py              # اپ FastAPI، روت‌ها، CORS، scheduler
│   ├── database.py          # engine, SessionLocal, get_db, Base
│   ├── models.py            # مدل‌های SQLAlchemy
│   ├── deps.py              # وابستگی‌های مشترک
│   ├── core/
│   │   ├── scheduler.py     # زمان‌بند اعلان‌ها، تحویل، دارو، دستگاه
│   │   ├── security.py      # JWT، توکن
│   │   ├── passkey_utils.py
│   │   ├── device_auth.py   # احراز هویت دستگاه
│   │   ├── ai_text_engine.py
│   │   ├── gpt_engine.py
│   │   └── conversation/    # چت، حافظه، مراحل، پرامپت‌ها
│   │       ├── brain.py, memory.py, context.py, stages.py, prompts.py
│   │       ├── name_database.py, question_database.py, sedi_knowledge_base.py
│   ├── decision_engine/      # ارزیابی رویداد، قوانین، اقدامات
│   │   ├── models.py, rules.py, service.py
│   ├── routers/
│   │   ├── auth.py          # /auth
│   │   ├── auth_login.py    # /auth/login
│   │   ├── interact.py     # /interact (چت، onboarding)
│   │   ├── health.py        # /health
│   │   ├── lifestyle.py     # /lifestyle
│   │   ├── notifications.py # /notifications
│   │   ├── ai_core.py       # /ai_core
│   │   ├── conditions.py    # /conditions
│   │   ├── device.py        # /device (ingest، pending-commands، heartbeat)
│   │   ├── devices.py       # /devices (ثبت دستگاه)
│   │   ├── decision.py      # موتور تصمیم‌گیری
│   │   ├── data.py, medical.py, memory.py, device_data.py, sms_gateway.py
│   ├── schemas/             # Pydantic (درخواست/پاسخ)
│   │   ├── common.py, chat.py, device.py, devices.py, health.py
│   │   ├── lifestyle.py, medical.py, memory.py, notification.py
│   │   ├── onboarding.py, interaction.py, user.py
│   └── services/
│       ├── notification_engine.py
│       ├── device_ingestion.py
│       ├── medical.py, rag.py
│       ├── memory/          # memory_repository, memory_context, memory_contract
│       ├── notification_runtime/  # fallback_generator, ai_enhancer, language_resolver
│       ├── notifications/   # delivery_service
│       └── vitals/          # vital_registry, dedupe, rule_alerts
├── docs/                    # مستندات (از جمله BACKEND_FINAL_STRUCTURE_REPORT)
├── deployment/              # systemd، migrations، اسکریپت‌ها
├── tests/                   # acceptance و واحد/یکپارچه
├── requirements.txt
└── README.md
```

### ۲.۳ روت‌های API (ثبت‌شده در main.py)

| پیشوند | تگ | فایل روتِر |
|--------|-----|------------|
| `/auth` | Authentication | auth.py |
| `/interact` | Interaction | interact.py |
| `/health` | Health Data | health.py |
| `/lifestyle` | Lifestyle Data | lifestyle.py |
| `/notifications` | Notifications | notifications.py |
| `/ai_core` | AI Core | ai_core.py |
| `/conditions` | Medical Conditions | conditions.py |
| `/device` | Device | device.py |
| `/devices` | Devices | devices.py |
| (decision) | — | decision.py |

### ۲.۴ مدل‌های دیتابیس (خلاصه)

| مدل | جدول | توضیح کوتاه |
|-----|------|--------------|
| User | users | نام، secret_key، زبان |
| Memory | memory | پیام/پاسخ چت |
| HealthData | health_data | ضربان، دما، SpO2 |
| Notification | notifications | type، body، priority، is_sent، sent_at، dedupe_key |
| MedicalCondition | medical_conditions | کد، نام، دسته |
| Medication | medications | داروها |
| UserCondition | user_conditions | ارتباط کاربر–شرایط |
| UserMedication | user_medications | یادآوری دارو |
| DailyMemorySummary | daily_memory_summaries | خلاصه روزانه |
| UserMemoryFact | user_memory_facts | حقایق حافظه (domain, key, value_json) |
| DeviceEvent | device_events | رویداد دستگاه |
| Device | devices | device_id، token_hash، last_seen_at |

### ۲.۵ وابستگی‌های اصلی (requirements.txt)

- fastapi, uvicorn, pydantic, python-dotenv  
- openai, requests  
- passlib, bcrypt, python-jose, **PyJWT==2.11.0**  
- apscheduler, sqlalchemy, pytz, psycopg2-binary  

---

## بخش ۳ — ساختار فرانت‌اند

### ۳.۱ نمای کلی

- **فریمورک:** Flutter (SDK >=3.0.0 <4.0.0)  
- **نسخه:** ۱.۰.۰+۲  
- **مسیر در ریپو:** `frontend/` (و در صورت وجود `backend/frontend`)  
- **نقطه ورود:** IntroPage → Onboarding → UserVerification → Chat و فیچرهای سلامت/دستگاه/سبک زندگی/اعلان  

### ۳.۲ ساختار دایرکتوری فرانت‌اند (lib)

```
frontend/lib/
├── main.dart                 # نقطه ورود → SediApp
├── app.dart                  # MaterialApp، تم، home: IntroPage
├── core/
│   ├── config/
│   │   └── app_config.dart   # baseUrl، useLocalMode
│   ├── auth/
│   │   ├── auth_helper.dart
│   │   └── auth_service.dart
│   ├── network/
│   │   └── api_client.dart, api_error.dart, api_response.dart
│   ├── theme/
│   │   └── app_theme.dart
│   ├── notifications/
│   │   └── local_notifications_service.dart
│   ├── debug/                # smoke تست‌ها (device_ingest, devices, health, lifestyle)
│   └── utils/
│       ├── language_detector.dart, messages.dart
│       ├── user_preferences.dart, user_profile_manager.dart
│       ├── brand_name.dart, gender_guess.dart
├── data/
│   ├── dto/
│   │   ├── interact_request.dart, interact_response.dart
│   │   ├── device_ingest_request.dart, device_ingest_response.dart
│   │   ├── device_public_info.dart, device_register_request.dart, devices_list_response.dart
│   │   ├── health_data_create.dart, health_data_response.dart
│   │   ├── lifestyle_data_create.dart, lifestyle_context_response.dart
│   ├── models/
│   │   ├── chat_message.dart, user_profile.dart
│   │   ├── notification.dart, notification_feedback.dart
│   ├── repositories/
│   │   ├── chat_repository.dart
│   │   ├── device_repository.dart, devices_repository.dart
│   │   ├── health_repository.dart, lifestyle_repository.dart
├── features/
│   ├── intro/
│   │   └── presentation/pages/intro_page.dart
│   ├── onboarding/
│   │   └── presentation/pages/onboarding_page.dart
│   ├── user_verification/
│   │   └── presentation/pages/user_verification_page.dart
│   ├── chat/
│   │   ├── chat_service.dart
│   │   ├── state/chat_controller.dart
│   │   ├── logic/greeting_templates.dart
│   │   └── presentation/
│   │       ├── pages/chat_page.dart, chat_history_page.dart
│   │       └── widgets/input_bar, message_bubble, sedi_header, sedi_ring_anim, language_selection_dialog
│   ├── health/
│   │   ├── logic/vitals_controller.dart, vitals_cache.dart, vitals_history.dart
│   │   └── presentation/pages/vitals_page.dart, widgets/vital_value_tile.dart
│   ├── devices/
│   │   ├── logic/devices_controller.dart
│   │   └── presentation/pages/devices_page.dart
│   ├── lifestyle/
│   │   ├── logic/lifestyle_controller.dart, lifestyle_validation.dart
│   │   └── presentation/pages/lifestyle_page.dart
│   ├── notification/
│   │   ├── data/models/sedi_notification.dart
│   │   ├── notification_service.dart
│   │   ├── logic/notification_handler, notification_sync, frontend_contract_test, notification_test
│   │   ├── presentation/pages/notifications_inbox_page.dart
│   │   ├── presentation/widgets/notification_card.dart
│   │   └── utils/notification_ui_mapping.dart
└── utils/
    └── time_utils.dart
```

### ۳.۳ وابستگی‌های فرانت (pubspec.yaml)

| پکیج | کاربرد |
|------|--------|
| flutter | SDK |
| cupertino_icons | آیکون‌ها |
| http | درخواست به بک‌اند |
| shared_preferences | ذخیرهٔ محلی |
| provider | مدیریت وضعیت |
| intl | تاریخ/زبان |
| flutter_local_notifications | اعلان‌های محلی |

### ۳.۴ اتصال به بک‌اند

- **آدرس پیش‌فرض:** در `AppConfig.baseUrl` (مثلاً `http://91.107.168.130:8000`).
- **حالت لوکال:** `useLocalMode = true` برای mock بدون بک‌اند؛ برای اتصال واقعی `useLocalMode = false`.

### ۳.۵ پلتفرم‌ها و بیلد

- **پلتفرم‌ها:** android، ios، web، windows، linux، macos.
- **آیکون اپ:** `flutter_launcher_icons` با `assets/images/sedi_app_icon.png`.
- **GitHub Actions:** بیلد Android روی push به main/master/develop و workflow_dispatch.

---

## بخش ۴ — خلاصه و مراجع

### ۴.۱ خلاصه

| لایه | فریمورک / نسخه | Entrypoint / نقطه ورود |
|------|-----------------|-------------------------|
| بک‌اند | FastAPI ۲.۰.۱ | `backend.app.main:app` |
| فرانت‌اند | Flutter ۱.۰.۰+۲ | IntroPage → Onboarding → Chat و فیچرها |

### ۴.۲ اسناد مرتبط در پروژه

| سند | مسیر | توضیح |
|-----|------|--------|
| گزارش ساختار نهایی بک‌اند | `backend/docs/BACKEND_FINAL_STRUCTURE_REPORT.md` | ساختار کامل بک‌اند، روت‌ها، سرویس‌ها، مدل‌ها، CI |
| گزارش ساختار فرانت‌اند | `backend/docs/FRONTEND_STRUCTURE_REPORT.md` | ساختار فرانت و هم‌راستایی با بک‌اند |
| فریز بک‌اند | `backend/docs/BACKEND_FREEZE.md` | سیاست تغییرات، چک‌لیست عملیاتی، امنیت |
| هم‌راستایی فرانت–بک‌اند | `frontend/docs/FRONTEND_BACKEND_ALIGNMENT.md` | APIها، اسکیماها، پیشنهاد ساختار برای توسعه |

### ۴.۳ دستورات مفید

**اجرای بک‌اند (توسعه):**
```bash
# از ریشهٔ ریپو
PYTHONPATH=<repo_root> uvicorn backend.app.main:app --reload
```

**تست acceptance بک‌اند:**
```bash
PYTHONPATH=<repo_root> python -m pytest backend/tests/acceptance/test_release_d.py -v --tb=long
```

**بیلد فرانت (Android):**
```bash
cd frontend && flutter build apk
# یا
flutter build appbundle
```

---

*این گزارش آخرین تغییرات و ساختار فعلی فرانت‌اند و بک‌اند را تا تاریخ بالا خلاصه می‌کند. برای جزئیات بیشتر به اسناد اشاره‌شده در بخش ۴.۲ مراجعه شود.*
