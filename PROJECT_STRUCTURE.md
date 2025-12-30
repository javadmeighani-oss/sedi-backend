# ساختار پروژه Sedi

این سند ساختار کامل پروژه را توضیح می‌دهد.

## 📁 ساختار کلی

```
Demo/
├── backend/              # Backend API (Python/FastAPI)
├── frontend/              # Frontend Application (Flutter)
├── README.md              # راهنمای کلی پروژه
├── .gitignore             # Git ignore rules (root level)
└── PROJECT_STRUCTURE.md   # این فایل
```

## 🎯 اصول طراحی

### جداسازی وظایف (Separation of Concerns)

**قانون اصلی:** هر پوشه و فایل باید وظیفه مشخصی داشته باشد و **هیچ تداخلی** بین backend و frontend وجود نداشته باشد.

### قوانین:

1. ✅ **فایل‌های backend فقط در `backend/`**
   - کدهای Python
   - اسکریپت‌های مدیریتی backend
   - مستندات backend
   - فایل‌های deployment backend

2. ✅ **فایل‌های frontend فقط در `frontend/`**
   - کدهای Flutter/Dart
   - اسکریپت‌های اجرای frontend
   - مستندات frontend
   - فایل‌های build frontend

3. ✅ **مستندات مشترک**
   - منبع اصلی: `backend/docs/`
   - نسخه مرجع در frontend: `frontend/docs/` (با لینک به منبع اصلی)

4. ✅ **اسکریپت‌های مدیریتی**
   - Backend scripts: `backend/scripts/`
   - Frontend scripts: `frontend/` (فقط برای frontend)

## 📂 ساختار Backend

```
backend/
├── app/                   # کد اصلی اپلیکیشن
│   ├── core/             # منطق اصلی (AI, security, scheduler)
│   │   ├── conversation/ # Conversation brain
│   │   ├── ai_text_engine.py
│   │   ├── gpt_engine.py
│   │   ├── scheduler.py
│   │   └── security.py
│   ├── routers/          # API endpoints
│   │   ├── auth.py
│   │   ├── interact.py
│   │   ├── notifications.py
│   │   └── ...
│   ├── models.py         # Database models
│   ├── schemas.py        # Pydantic schemas
│   ├── database.py       # Database configuration
│   └── main.py           # FastAPI application
│
├── scripts/              # اسکریپت‌های مدیریتی
│   ├── restart-backend.ps1
│   ├── RESTART_INSTRUCTIONS.md
│   └── README.md
│
├── deployment/           # فایل‌های deployment
│   ├── deploy.sh
│   ├── RESTART_BACKEND.ps1
│   └── ...
│
├── docs/                 # مستندات backend
│   ├── notification_contract.md  # ⭐ منبع اصلی
│   ├── conversation_brain_architecture.md
│   └── ...
│
├── requirements.txt      # Python dependencies
└── README_DEPLOYMENT.md  # راهنمای deployment
```

## 📂 ساختار Frontend

```
frontend/
├── lib/                  # کد اصلی Flutter
│   ├── core/            # Core functionality
│   │   ├── auth/        # Authentication
│   │   ├── config/      # App configuration
│   │   ├── network/     # API client
│   │   └── theme/       # App theme
│   ├── data/            # Data layer
│   │   ├── dto/         # Data transfer objects
│   │   ├── models/      # Data models
│   │   └── repositories/
│   ├── features/        # Feature modules
│   │   ├── chat/        # Chat feature
│   │   ├── notification/ # Notification feature
│   │   └── intro/       # Intro screens
│   ├── utils/           # Utility functions
│   ├── app.dart
│   └── main.dart
│
├── assets/              # Static assets
│   └── images/
│
├── docs/                # مستندات frontend
│   ├── notification_contract.md  # ⚠️ Reference copy
│   ├── lib_structure.txt
│   └── ...
│
├── android/             # Android platform files
├── ios/                  # iOS platform files
├── web/                  # Web platform files
├── windows/              # Windows platform files
├── linux/                # Linux platform files
├── macos/                # macOS platform files
│
├── pubspec.yaml         # Flutter dependencies
├── run.bat              # Frontend run script
└── README.md            # Frontend documentation
```

## 🔗 ارتباط Backend و Frontend

### API Communication
- Backend exposes REST API endpoints
- Frontend consumes API through `lib/core/network/api_client.dart`

### Notification Contract
- **منبع اصلی:** `backend/docs/notification_contract.md`
- **نسخه مرجع:** `frontend/docs/notification_contract.md` (با لینک به منبع اصلی)
- این contract تعریف می‌کند که backend و frontend چگونه با هم ارتباط برقرار می‌کنند

## ✅ Checklist جداسازی

قبل از commit، مطمئن شوید:

- [ ] هیچ فایل backend در `frontend/` نیست
- [ ] هیچ فایل frontend در `backend/` نیست
- [ ] اسکریپت‌های restart backend در `backend/scripts/` هستند
- [ ] مستندات مشترک در `backend/docs/` نگهداری می‌شوند
- [ ] فایل‌های deployment در `backend/deployment/` هستند

## 📝 نکات مهم

1. **Monorepo Structure**: این یک monorepo است که backend و frontend را در یک repository نگهداری می‌کند
2. **Separation of Concerns**: با وجود monorepo، backend و frontend کاملاً جدا هستند
3. **Single Source of Truth**: مستندات مشترک در `backend/docs/` نگهداری می‌شوند
4. **Clear Responsibilities**: هر پوشه وظیفه مشخصی دارد

---

**آخرین به‌روزرسانی:** 2024

