# گزارش کامل Backend - Sedi Intelligent Health Assistant

**نسخه:** 2.0.1  
**Framework:** FastAPI (Python)  
**Database:** PostgreSQL  
**تاریخ گزارش:** 2024-12-26

---

## 📋 فهرست مطالب

1. [ساختار کلی پروژه](#ساختار-کلی-پروژه)
2. [فایل‌های اصلی](#فایل‌های-اصلی)
3. [ماژول‌های Core](#ماژول‌های-core)
4. [API Routers](#api-routers)
5. [Database Models](#database-models)
6. [Schemas (Pydantic)](#schemas-pydantic)
7. [Dependencies](#dependencies)
8. [Deployment & Scripts](#deployment--scripts)

---

## 📁 ساختار کلی پروژه

```
backend/
├── app/                    # کد اصلی اپلیکیشن
│   ├── core/              # منطق اصلی و هوشمند
│   ├── routers/           # API endpoints
│   ├── main.py            # نقطه ورود FastAPI
│   ├── database.py        # تنظیمات دیتابیس
│   ├── models.py          # مدل‌های SQLAlchemy
│   ├── schemas.py         # مدل‌های Pydantic
│   └── deps.py            # Dependencies
├── deployment/            # فایل‌های deployment
├── docs/                  # مستندات
├── scripts/               # اسکریپت‌های مدیریتی
├── requirements.txt       # Python dependencies
└── Procfile              # Heroku deployment
```

---

## 📄 فایل‌های اصلی

### 1. `app/main.py` - نقطه ورود اپلیکیشن

**وظیفه:**
- ایجاد و پیکربندی FastAPI application
- تنظیم CORS middleware
- اتصال routers به application
- راه‌اندازی scheduler برای notifications خودکار
- ایجاد جداول دیتابیس

**ویژگی‌ها:**
- Title: "Sedi Intelligent Health Assistant"
- Version: 2.0.1
- CORS: فعال برای همه origins (قابل تنظیم برای production)
- Languages: en, fa, ar

**Routers متصل شده:**
- `/auth` - Authentication
- `/interact` - Chat & Interaction
- `/health` - Health Data
- `/lifestyle` - Lifestyle Data
- `/notifications` - Notifications
- `/ai_core` - AI Core Functions

---

### 2. `app/database.py` - تنظیمات دیتابیس

**وظیفه:**
- اتصال به PostgreSQL
- ایجاد database engine
- ایجاد session factory
- مدیریت connection pool

**ویژگی‌ها:**
- Database: PostgreSQL (via psycopg2)
- Connection Pool: 5 connections, max overflow 10
- Pool Pre-ping: فعال برای بررسی اتصال
- Environment Variable: `DATABASE_URL`

**Functions:**
- `get_db()`: Dependency برای FastAPI routes

---

### 3. `app/models.py` - مدل‌های دیتابیس (SQLAlchemy)

**وظیفه:**
- تعریف جداول دیتابیس
- تعریف روابط بین جداول
- تعریف constraints و indexes

**Models:**

#### `User`
- `id`: Primary Key
- `name`: نام کاربر (unique)
- `secret_key`: رمز شخصی
- `preferred_language`: زبان انتخابی (default: "en")
- `created_at`: زمان ثبت‌نام

#### `Memory`
- `id`: Primary Key
- `user_id`: Foreign Key به User
- `user_message`: پیام کاربر
- `sedi_response`: پاسخ صدی
- `language`: زبان مکالمه
- `created_at`: زمان ایجاد

#### `HealthData`
- `id`: Primary Key
- `user_id`: Foreign Key به User
- `heart_rate`: ضربان قلب
- `temperature`: دما
- `spo2`: سطح اکسیژن خون
- `created_at`: زمان ثبت

#### `Notification`
- `id`: Primary Key
- `user_id`: Foreign Key به User
- `type`: نوع notification (info, alert, reminder, check_in, achievement)
- `priority`: اولویت (low, normal, high, urgent)
- `title`: عنوان (اختیاری)
- `message`: متن notification
- `actions`: JSON string از actions array
- `metadata_json`: JSON string از metadata object
- `is_read`: وضعیت خوانده شدن
- `created_at`: زمان ایجاد

---

### 4. `app/schemas.py` - مدل‌های Pydantic

**وظیفه:**
- تعریف ساختار داده‌های ورودی و خروجی API
- Validation داده‌ها
- تبدیل ORM objects به JSON

**Schemas:**

#### Base Schemas
- `ErrorInfo`: ساختار خطا
- `APIResponse`: پاسخ استاندارد API

#### User Schemas
- `UserCreate`: ایجاد کاربر جدید
- `UserResponse`: پاسخ اطلاعات کاربر

#### Health Data Schemas
- `HealthDataCreate`: ایجاد داده سلامت
- `HealthDataResponse`: پاسخ داده سلامت

#### Lifestyle Data Schemas
- `LifestyleDataCreate`: ایجاد داده سبک زندگی
- `LifestyleDataResponse`: پاسخ داده سبک زندگی

#### Notification Schemas (Contract-Compliant)
- `Action`: ساختار action در notification
- `NotificationMetadata`: metadata notification
- `NotificationCreate`: ایجاد notification
- `NotificationResponse`: پاسخ notification (مطابق contract)
- `NotificationFeedback`: feedback از کاربر

#### Memory Schemas
- `MemoryCreate`: ایجاد memory
- `MemoryResponse`: پاسخ memory

#### Interaction Schemas
- `InteractionResponse`: پاسخ chat/interaction

---

### 5. `app/deps.py` - Dependencies

**وظیفه:**
- تعریف dependencies مشترک برای routes
- در حال حاضر فقط `get_db` را export می‌کند

---

## 🧠 ماژول‌های Core

### 1. `app/core/conversation/` - Conversation Brain

**مسئولیت:** مدیریت هوشمند مکالمات و تصمیم‌گیری

#### `brain.py` - Conversation Brain (Commander)
**وظیفه:**
- نقطه ورود برای تمام تعاملات چت
- تعیین stage فعلی مکالمه
- هماهنگی بین memory، context، و prompts
- تولید پاسخ هوشمند

**Flow:**
1. دریافت user_id و user_message
2. دریافت stage فعلی
3. ساخت context
4. تولید پاسخ با استفاده از prompts
5. ذخیره در memory
6. بررسی transition stage
7. بازگشت پاسخ + metadata

#### `stages.py` - Conversation Stages
**وظیفه:**
- تعریف مراحل مختلف مکالمه
- مدیریت transition بین stages
- تعیین stage بر اساس context

**Stages:**
- Initial greeting
- Getting to know user
- Regular conversation
- Health check
- etc.

#### `context.py` - Conversation Context
**وظیفه:**
- ساخت context از memory
- استخراج اطلاعات کاربر
- آماده‌سازی context برای prompts

#### `memory.py` - Conversation Memory
**وظیفه:**
- ذخیره و بازیابی memory
- مدیریت تاریخچه مکالمات
- استخراج اطلاعات مهم از مکالمات

#### `prompts.py` - Conversation Prompts
**وظیفه:**
- نگهداری prompts برای GPT
- تولید prompts بر اساس stage و context
- پشتیبانی از چندزبانه (en, fa, ar)

---

### 2. `app/core/gpt_engine.py` - GPT Integration

**وظیفه:**
- اتصال به OpenAI API
- ارسال prompts به GPT
- دریافت و پردازش پاسخ‌ها
- مدیریت errors و retries

---

### 3. `app/core/ai_text_engine.py` - AI Text Generation

**وظیفه:**
- تولید متن برای notifications
- تولید متن برای responses
- مدیریت tone و personality
- پشتیبانی از چندزبانه

**Functions:**
- `generate_notification_text()`: تولید متن notification
- `NOTIF_TYPE_MORNING`: نوع notification صبحگاهی
- `NOTIF_TYPE_HEALTH_CHECK`: نوع notification بررسی سلامت
- `NOTIF_TYPE_INACTIVE`: نوع notification برای کاربران غیرفعال

---

### 4. `app/core/scheduler.py` - Background Scheduler

**وظیفه:**
- اجرای وظایف زمان‌بندی شده
- ارسال notifications خودکار
- بررسی کاربران غیرفعال
- ارسال health check reminders

**Jobs:**
- `check_inactive_users()`: بررسی کاربران غیرفعال (هر 2 ساعت)
- `send_morning_greetings()`: ارسال سلام صبحگاهی (ساعت 8 صبح)
- `send_health_reminders()`: ارسال یادآوری بررسی سلامت

**تنظیمات:**
- Timezone: Asia/Tehran
- Check Interval: 2 hours
- Inactive Threshold: 3 hours
- Morning Hour: 8 AM

---

### 5. `app/core/security.py` - Security & Authentication

**وظیفه:**
- بررسی امنیت
- تشخیص رفتار مشکوک
- مدیریت authentication
- Hash کردن passwords

---

### 6. `app/core/passkey_utils.py` - Passkey Utilities

**وظیفه:**
- مدیریت passkeys
- تولید و verify passkeys
- امنیت authentication

---

## 🛣️ API Routers

### 1. `app/routers/interact.py` - Chat & Interaction

**Base Path:** `/interact`

**Endpoints:**

#### `POST /interact/introduce`
- ثبت‌نام کاربر جدید
- Upgrade anonymous user به registered user
- دریافت greeting از Conversation Brain

**Parameters:**
- `name`: نام کاربر
- `secret_key`: رمز شخصی
- `lang`: زبان (en, fa, ar)
- `user_id`: (اختیاری) برای upgrade anonymous user

#### `POST /interact/chat`
- ارسال پیام و دریافت پاسخ
- پشتیبانی از anonymous users
- مدیریت security checks

**Parameters:**
- `message`: متن پیام
- `lang`: زبان
- `name`: (اختیاری) نام کاربر
- `secret_key`: (اختیاری) رمز شخصی

**Response:**
- `message`: پاسخ صدی
- `language`: زبان پاسخ
- `user_id`: شناسه کاربر (برای anonymous users)
- `timestamp`: زمان پاسخ
- `requires_security_check`: نیاز به بررسی امنیتی

#### `GET /interact/greeting`
- دریافت greeting برای کاربر
- پشتیبانی از returning users

#### `GET /interact/history`
- دریافت تاریخچه مکالمات
- Pagination support

---

### 2. `app/routers/notifications.py` - Notifications

**Base Path:** `/notifications`

**Contract-Compliant:** مطابق با Notification Contract v1.0.0

**Endpoints:**

#### `GET /notifications` یا `GET /notifications/`
- دریافت لیست notifications
- Pagination support
- Filter by user_id

**Parameters:**
- `user_id`: شناسه کاربر
- `limit`: تعداد نتایج (default: 20, max: 100)
- `offset`: offset برای pagination (default: 0)

**Response:**
```json
{
  "ok": true,
  "data": {
    "notifications": [...],
    "total": 0,
    "unread_count": 0
  }
}
```

#### `POST /notifications/create`
- ایجاد notification جدید
- Contract-compliant structure

#### `POST /notifications/feedback`
- دریافت feedback از کاربر
- ثبت reaction و action_id

**Contract Section 5:**
- `notification_id`: شناسه notification
- `action_id`: (اختیاری) شناسه action
- `reaction`: نوع reaction (seen, interact, dismiss, like, dislike)
- `feedback_text`: (اختیاری) متن feedback
- `timestamp`: زمان feedback

---

### 3. `app/routers/auth.py` - Authentication

**Base Path:** `/auth`

**Endpoints:**
- `POST /auth/set-passkey`: تنظیم passkey
- `POST /auth/verify-passkey`: بررسی passkey

---

### 4. `app/routers/auth_login.py` - Login & Token *(LEGACY — DISABLED)*

Stage 25 OTP is the only supported auth; this router is not mounted. Do not re-enable.

**Base Path:** `/auth` (extended)

**Endpoints:**
- `POST /auth/request-pin`: درخواست PIN
- `POST /auth/verify-pin`: بررسی PIN
- `POST /auth/refresh-token`: تازه‌سازی token
- `GET /auth/verify-token`: بررسی token

---

### 5. `app/routers/health.py` - Health Data

**Base Path:** `/health`

**Endpoints:**
- `POST /health/add`: افزودن داده سلامت

---

### 6. `app/routers/lifestyle.py` - Lifestyle Data

**Base Path:** `/lifestyle`

**Endpoints:**
- مدیریت داده‌های سبک زندگی

---

### 7. `app/routers/memory.py` - Memory Management

**Base Path:** `/memory`

**Endpoints:**
- `POST /memory/save`: ذخیره memory
- `GET /memory/latest`: دریافت آخرین memory

---

### 8. `app/routers/medical.py` - Medical Records

**Base Path:** `/medical`

**Endpoints:**
- `POST /medical/share`: اشتراک‌گذاری اطلاعات پزشکی
- `GET /medical/records`: دریافت سوابق پزشکی
- `POST /medical/doctor-note`: افزودن یادداشت پزشک

---

### 9. `app/routers/device.py` - Device Management

**Base Path:** `/device`

**Endpoints:**
- `GET /device/pending-commands`: دریافت دستورات در انتظار
- `POST /device/heartbeat`: ارسال heartbeat
- `POST /device/acknowledge`: تأیید دریافت دستور

---

### 10. `app/routers/device_data.py` - Device Data

**Base Path:** `/device`

**Endpoints:**
- `POST /device/data/upload`: آپلود داده از device

---

### 11. `app/routers/data.py` - General Data

**Base Path:** `/data`

**Endpoints:**
- `POST /data/upload`: آپلود داده عمومی

---

### 12. `app/routers/sms_gateway.py` - SMS Gateway

**Base Path:** `/sms`

**Endpoints:**
- `POST /sms/send`: ارسال SMS
- `GET /sms/logs`: دریافت لاگ‌های SMS

---

### 13. `app/routers/ai_core.py` - AI Core Functions

**Base Path:** `/ai_core`

**Endpoints:**
- `POST /ai_core/analyze`: تحلیل داده‌ها با AI

---

## 📦 Dependencies

### Python Packages (`requirements.txt`)

```
fastapi              # Web framework
uvicorn              # ASGI server
pydantic             # Data validation
python-dotenv        # Environment variables
openai               # OpenAI API client
requests             # HTTP requests
passlib              # Password hashing
bcrypt               # Password encryption
python-jose          # JWT tokens
apscheduler          # Background scheduler
sqlalchemy           # ORM
pytz                 # Timezone handling
psycopg2-binary      # PostgreSQL adapter
```

---

## 🚀 Deployment & Scripts

### Deployment Files (`deployment/`)

**Scripts:**
- `deploy.sh`: اسکریپت deployment اصلی
- `postgresql-setup.sh`: تنظیم PostgreSQL
- `VERIFY_DEPLOYMENT.sh`: بررسی deployment
- `RESTART_BACKEND.ps1`: Restart backend (PowerShell)

**Documentation:**
- `FINAL_DEPLOYMENT_CHECKLIST.md`: چک‌لیست deployment
- `POSTGRESQL_MIGRATION.md`: راهنمای migration
- `manual-deploy.md`: راهنمای deployment دستی

**Service Files:**
- `sedi-backend.service`: systemd service file

### Scripts (`scripts/`)

- `restart-backend.ps1`: اسکریپت restart برای Windows
- `RESTART_INSTRUCTIONS.md`: راهنمای restart
- `README.md`: راهنمای scripts

---

## 📚 Documentation (`docs/`)

**Architecture:**
- `conversation_brain_architecture.md`: معماری Conversation Brain
- `notification_contract.md`: Notification Contract (v1.0.0)

**Deployment:**
- `GITHUB_ACTIONS_SETUP.md`: راهنمای GitHub Actions
- `DEPLOYMENT_STATUS.md`: وضعیت deployment
- `CI_CD_SOLUTIONS.md`: راهکارهای CI/CD

**Change Reports:**
- `CONVERSATION_BRAIN_CHANGE_REPORT.md`
- `CONVERSATION_TUNING_V1_CHANGE_REPORT.md`

---

## 🔧 Configuration

### Environment Variables

- `DATABASE_URL`: آدرس PostgreSQL
- `OPENAI_API_KEY`: کلید API OpenAI
- (سایر متغیرهای محیطی)

### Server Configuration

- **Port:** 8000
- **Host:** 0.0.0.0 (برای production)
- **CORS:** فعال (قابل تنظیم)

---

## 📊 آمار پروژه

- **Total Routers:** 13
- **Total Endpoints:** ~30+
- **Database Models:** 4 (User, Memory, HealthData, Notification)
- **Core Modules:** 6
- **Conversation Brain Components:** 5
- **Supported Languages:** 3 (en, fa, ar)

---

## ✅ ویژگی‌های کلیدی

1. **Conversation Brain:** سیستم هوشمند مدیریت مکالمات
2. **Multi-language Support:** پشتیبانی از انگلیسی، فارسی، عربی
3. **Notification System:** سیستم notification مطابق contract
4. **Background Scheduler:** ارسال notifications خودکار
5. **Security:** تشخیص رفتار مشکوک و security checks
6. **Anonymous Users:** پشتیبانی از کاربران ناشناس
7. **Memory Management:** مدیریت حافظه مکالمات
8. **Health Data:** مدیریت داده‌های سلامت
9. **Device Integration:** اتصال با device‌ها
10. **RESTful API:** API استاندارد و مستند

---

## 🎯 معماری

### Pattern: Clean Architecture

- **Routers:** Thin API layer (فقط دریافت و ارسال)
- **Core:** Business logic (منطق اصلی)
- **Models:** Data layer (دیتابیس)
- **Schemas:** Validation layer (اعتبارسنجی)

### Separation of Concerns

- هر فایل یک مسئولیت مشخص دارد
- Routers فقط API handling
- Core فقط business logic
- Models فقط data structure

---

**آخرین به‌روزرسانی:** 2024-12-26  
**نسخه Backend:** 2.0.1  
**وضعیت:** ✅ Production Ready

