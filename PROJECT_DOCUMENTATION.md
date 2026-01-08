# 📚 مستندات کامل پروژه Sedi

**نسخه:** 2.0.1  
**تاریخ به‌روزرسانی:** 2024-12-26  
**وضعیت:** ✅ Production Ready

---

## 📋 فهرست مطالب

1. [ساختار کلی پروژه](#ساختار-کلی-پروژه)
2. [ساختار Backend](#ساختار-backend)
3. [ساختار Frontend](#ساختار-frontend)
4. [API Contracts](#api-contracts)
5. [کارهای انجام شده](#کارهای-انجام-شده)
6. [تغییرات اخیر](#تغییرات-اخیر)
7. [راه‌اندازی و Deployment](#راه‌اندازی-و-deployment)

---

## 📁 ساختار کلی پروژه

```
Demo/
├── backend/              # Backend API (Python/FastAPI)
│   ├── app/             # کد اصلی اپلیکیشن
│   ├── deployment/       # فایل‌های deployment و CI/CD
│   ├── docs/            # مستندات backend
│   ├── scripts/         # اسکریپت‌های مدیریتی
│   └── requirements.txt
│
├── frontend/            # Frontend Application (Flutter)
│   ├── lib/             # کد اصلی Flutter
│   ├── assets/          # فایل‌های استاتیک
│   ├── android/         # Android configuration
│   ├── ios/             # iOS configuration
│   └── pubspec.yaml
│
└── README.md            # راهنمای کلی پروژه
```

---

## 🔧 ساختار Backend

### 📂 ساختار پوشه‌ها

```
backend/
├── app/
│   ├── core/                    # منطق اصلی و هوشمند
│   │   ├── conversation/        # Conversation Brain
│   │   │   ├── brain.py         # Central decision engine
│   │   │   ├── prompts.py       # GPT prompts and text generation
│   │   │   ├── memory.py        # Memory management
│   │   │   ├── stages.py        # Conversation stages
│   │   │   └── sedi_knowledge_base.py  # Sedi knowledge
│   │   ├── ai_text_engine.py    # AI text processing
│   │   ├── gpt_engine.py        # GPT integration
│   │   ├── scheduler.py         # Task scheduler
│   │   └── security.py          # Security checks
│   │
│   ├── routers/                  # API endpoints
│   │   ├── interact.py          # Chat & Onboarding endpoints
│   │   ├── notifications.py     # Notification endpoints
│   │   ├── health.py            # Health data endpoints
│   │   ├── lifestyle.py         # Lifestyle data endpoints
│   │   ├── memory.py            # Memory endpoints
│   │   └── ...                  # سایر endpoints
│   │
│   ├── schemas/                  # Pydantic schemas (Package structure)
│   │   ├── __init__.py          # Schema exports
│   │   ├── common.py            # Common schemas (APIResponse, ErrorInfo)
│   │   ├── onboarding.py        # OnboardingRequest
│   │   ├── chat.py              # ChatRequest, InteractionResponse
│   │   ├── user.py              # User schemas
│   │   ├── health.py            # Health data schemas
│   │   ├── lifestyle.py         # Lifestyle schemas
│   │   ├── notification.py     # Notification schemas
│   │   ├── memory.py            # Memory schemas
│   │   └── interaction.py       # Interaction schemas
│   │
│   ├── models.py                # SQLAlchemy database models
│   ├── database.py              # Database configuration
│   ├── main.py                  # FastAPI application entry point
│   └── deps.py                  # Dependencies
│
├── deployment/                   # Deployment files
│   ├── deploy.sh                # Deployment script
│   ├── postgresql-setup.sh      # PostgreSQL setup
│   └── ...                      # سایر فایل‌های deployment
│
├── docs/                         # مستندات
│   ├── notification_contract.md  # Notification API contract
│   ├── conversation_brain_architecture.md
│   └── ...
│
├── scripts/                      # اسکریپت‌های مدیریتی
│   └── restart-backend.ps1
│
├── remove_name_unique_constraint.py  # Migration script
├── fix_schema.py                 # Schema fix script
├── requirements.txt              # Python dependencies
└── Procfile                      # Heroku deployment
```

### 🗄️ Database Models

#### User Model
```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True, unique=False)  # NOT unique - multiple users allowed
    secret_key = Column(String, nullable=False, unique=False)  # Placeholder (ignored)
    preferred_language = Column(String, default="en", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

**تغییرات اخیر:**
- ✅ `name` دیگر unique نیست - چند کاربر با نام یکسان مجاز است
- ✅ `secret_key` به placeholder تبدیل شده (password حذف شده)

#### Memory Model
```python
class Memory(Base):
    __tablename__ = "memory"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_message = Column(String, nullable=False)
    sedi_response = Column(String, nullable=True)
    language = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 🔌 API Endpoints

#### Onboarding
- **POST** `/interact/onboarding`
  - **Request:** `{"name": string}`
  - **Response:** `{"user_id": number, "message": string, "language": string}`
  - **Status:** ✅ Username-only (password removed)

#### Chat
- **POST** `/interact/chat`
  - **Request:** `{"user_id": number, "message": string}`
  - **Response:** `{"message": string, "language": string, "user_id": number, "detected_name": string?}`

#### Notifications
- **GET** `/notifications?user_id={id}`
- **POST** `/notifications/feedback`

---

## 📱 ساختار Frontend

### 📂 ساختار پوشه‌ها

```
frontend/
├── lib/
│   ├── core/                    # Core functionality
│   │   ├── auth/               # Authentication (deprecated - password removed)
│   │   ├── config/             # App configuration
│   │   │   └── app_config.dart # API base URL, local mode
│   │   ├── network/             # Network utilities
│   │   ├── theme/               # App theme
│   │   │   └── app_theme.dart  # Colors, styles
│   │   └── utils/               # Utility functions
│   │       ├── user_profile_manager.dart
│   │       └── user_preferences.dart
│   │
│   ├── data/                    # Data layer
│   │   ├── models/              # Data models
│   │   │   └── user_profile.dart
│   │   └── repositories/        # Data repositories
│   │
│   ├── features/                # Feature modules
│   │   ├── chat/                # Chat feature
│   │   │   ├── chat_service.dart        # API communication
│   │   │   ├── state/
│   │   │   │   └── chat_controller.dart # State management
│   │   │   └── presentation/
│   │   │       ├── pages/
│   │   │       │   └── chat_page.dart
│   │   │       └── widgets/
│   │   │           ├── input_bar.dart
│   │   │           └── sedi_header.dart
│   │   │
│   │   ├── onboarding/         # Onboarding feature
│   │   │   └── presentation/
│   │   │       └── pages/
│   │   │           └── onboarding_page.dart
│   │   │
│   │   ├── notification/       # Notification feature
│   │   └── user_verification/   # User verification (legacy)
│   │
│   ├── app.dart                 # App widget
│   └── main.dart                # Entry point
│
├── assets/                      # Static assets
│   └── images/                  # Images, logos
│
├── android/                     # Android configuration
├── ios/                         # iOS configuration
└── pubspec.yaml                 # Flutter dependencies
```

### 🎨 UI Components

#### Onboarding Page
- **Location:** `lib/features/onboarding/presentation/pages/onboarding_page.dart`
- **Features:**
  - ✅ Username input only (password removed)
  - ✅ Form validation (name required, non-empty)
  - ✅ Auto-navigation to chat on success
  - ✅ Error handling with backend messages

#### Chat Page
- **Location:** `lib/features/chat/presentation/pages/chat_page.dart`
- **Features:**
  - ✅ Message display
  - ✅ Input bar with voice recording
  - ✅ State machine (idle, sending, waiting, error)
  - ✅ Loading indicators
  - ✅ Error handling

#### Chat Service
- **Location:** `lib/features/chat/chat_service.dart`
- **Methods:**
  - `setupOnboarding({required String name})` - Username-only onboarding
  - `sendMessage(String message, {int? userId})` - Send chat message

---

## 📋 API Contracts

### Onboarding API

#### Request
```json
POST /interact/onboarding
Content-Type: application/json

{
  "name": "javad"
}
```

#### Success Response (HTTP 200)
```json
{
  "user_id": 123,
  "message": "Hello! I'm Sedi, your health care assistant. Welcome!",
  "language": "en"
}
```

#### Error Response (HTTP 400)
```json
{
  "detail": "Name is required and cannot be empty"
}
```

### Chat API

#### Request
```json
POST /interact/chat
Content-Type: application/json

{
  "user_id": 123,
  "message": "Hello Sedi"
}
```

#### Success Response (HTTP 200)
```json
{
  "message": "Hello! How can I help you today?",
  "language": "en",
  "user_id": 123,
  "detected_name": null,
  "timestamp": "2024-12-26T10:00:00Z"
}
```

---

## ✅ کارهای انجام شده

### 🔐 Authentication & Onboarding

1. **حذف کامل Password از Onboarding**
   - ✅ Backend: حذف `password` از `OnboardingRequest` schema
   - ✅ Backend: حذف validation و logic مربوط به password
   - ✅ Frontend: حذف password input field از UI
   - ✅ Frontend: به‌روزرسانی `setupOnboarding` برای فقط `name`
   - ✅ Database: حذف UNIQUE constraint از `users.name`
   - ✅ Migration: ایجاد script برای حذف constraint

2. **Username-Only Onboarding**
   - ✅ چند کاربر با نام یکسان مجاز است
   - ✅ Onboarding همیشه موفق می‌شود (اگر name ارائه شده باشد)
   - ✅ هیچ authentication logic وجود ندارد

### 🗄️ Database

1. **Schema Updates**
   - ✅ `users.name` دیگر unique نیست
   - ✅ `users.secret_key` به placeholder تبدیل شده
   - ✅ Migration script برای حذف constraint

2. **Error Handling**
   - ✅ بهبود error handling برای constraint errors
   - ✅ عدم افشای جزئیات database به client

### 🎨 Frontend Improvements

1. **Onboarding Flow**
   - ✅ حذف password input
   - ✅ Validation فقط برای name
   - ✅ Auto-navigation به chat بعد از موفقیت
   - ✅ Error handling با پیام‌های backend

2. **Chat Flow**
   - ✅ State machine صریح (idle, sending, waiting, error)
   - ✅ Disable input هنگام ارسال
   - ✅ Loading indicators
   - ✅ JSON response parsing
   - ✅ Error handling بهبود یافته

3. **Error Handling**
   - ✅ حذف پیام‌های خطای ساختگی
   - ✅ نمایش پیام‌های backend به صورت verbatim
   - ✅ Generic errors برای network issues

### 🔧 Backend Improvements

1. **Schema Architecture**
   - ✅ Migrate از `schemas.py` به package structure
   - ✅ ایجاد `schemas/common.py` برای shared schemas
   - ✅ Domain-specific schema files
   - ✅ Explicit exports در `__init__.py`

2. **GPT Integration**
   - ✅ Migration به OpenAI Responses API (برای project keys)
   - ✅ استفاده از `client.responses.create()`
   - ✅ Extract response با `output_text`

3. **Conversation Brain**
   - ✅ حذف dependency به `context` variable
   - ✅ ساخت مستقیم `messages` list
   - ✅ Fail-safe GPT invocation

---

## 🔄 تغییرات اخیر

### آخرین تغییرات (2024-12-26)

#### Backend
1. **حذف Password از Onboarding**
   - Commit: `0cb8513` - "feat: remove password from onboarding - username only"
   - Commit: `2649c0a` - "fix: remove username uniqueness constraint"
   - Commit: `878ac08` - "fix: improve error handling to not leak constraint details"

2. **Schema Migration**
   - Commit: `9dac54d` - "fix: migrate schemas to package structure"
   - حذف `schemas.py` legacy file
   - ایجاد package structure با sub-modules

3. **GPT API Update**
   - Migration به `responses.create()` API
   - Support برای project-based keys (`sk-proj-*`)

#### Frontend
1. **Onboarding Rewrite**
   - Commit: `6704c76` - "feat: remove password from onboarding - username only"
   - حذف password input field
   - به‌روزرسانی validation

2. **Chat Flow Improvements**
   - Commit: `8fd3a86` - "fix: remove hardcoded onboarding error"
   - State machine implementation
   - Error handling improvements

3. **Build Fixes**
   - Commit: `1a3e0cc` - "fix: replace undefined systemLanguage and language references"
   - Commit: `0ad273d` - "fix: correct setupOnboarding calls"

---

## 🚀 راه‌اندازی و Deployment

### Backend Setup

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run migration (if needed)
python remove_name_unique_constraint.py

# Start server
uvicorn app.main:app --reload
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
flutter pub get

# Run app
flutter run
```

### Environment Variables

#### Backend (.env)
```env
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/sedi_db
OPENAI_API_KEY=sk-...
```

#### Frontend (app_config.dart)
```dart
static const String baseUrl = 'http://91.107.168.130:8000';
static const bool useLocalMode = false;
```

---

## 📊 وضعیت پروژه

### ✅ Completed
- [x] Username-only onboarding
- [x] Password removal (backend & frontend)
- [x] Database constraint removal
- [x] Schema package migration
- [x] GPT API migration
- [x] Error handling improvements
- [x] Frontend state machine
- [x] Build fixes

### 🔄 In Progress
- [ ] Production testing
- [ ] Performance optimization

### 📝 Future Improvements
- [ ] User profile enhancements
- [ ] Advanced conversation features
- [ ] Analytics integration

---

## 🔗 لینک‌های مفید

- **Backend API Docs:** http://91.107.168.130:8000/docs
- **GitHub Backend:** https://github.com/javadmeighani-oss/sedi-backend
- **GitHub Frontend:** https://github.com/javadmeighani-oss/sedi-frontend

---

## 📝 یادداشت‌ها

### Architecture Decisions

1. **Username-Only Onboarding**
   - تصمیم: حذف کامل password/authentication
   - دلیل: ساده‌سازی flow و کاهش friction
   - نتیجه: چند کاربر با نام یکسان مجاز است

2. **Schema Package Structure**
   - تصمیم: Migration از single file به package
   - دلیل: بهبود modularity و maintainability
   - نتیجه: Schema files در sub-modules

3. **Error Handling**
   - تصمیم: عدم افشای جزئیات database
   - دلیل: Security و user experience
   - نتیجه: Generic error messages برای client

---

**آخرین به‌روزرسانی:** 2024-12-26  
**نگهدارنده:** Development Team
