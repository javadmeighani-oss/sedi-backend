# Sedi - Intelligent Health Assistant

پروژه Sedi یک دستیار هوشمند سلامت است که از معماری Monorepo استفاده می‌کند.

## 📁 ساختار پروژه

```
Demo/
├── backend/          # Backend API (Python/FastAPI)
│   ├── app/          # کد اصلی اپلیکیشن
│   ├── scripts/      # اسکریپت‌های مدیریتی (restart, deploy, etc.)
│   ├── deployment/   # فایل‌های deployment و CI/CD
│   ├── docs/         # مستندات backend
│   └── requirements.txt
│
├── frontend/          # Frontend Application (Flutter)
│   ├── lib/          # کد اصلی Flutter
│   ├── assets/       # فایل‌های استاتیک
│   ├── docs/         # مستندات frontend
│   └── pubspec.yaml
│
└── README.md          # این فایل
```

## 🎯 اصول طراحی

### جداسازی وظایف (Separation of Concerns)

هر پوشه و فایل باید **وظیفه مشخصی** داشته باشد:

- **`backend/`**: تمام کدها و اسکریپت‌های مربوط به backend
- **`frontend/`**: تمام کدها و اسکریپت‌های مربوط به frontend
- **هیچ تداخلی بین پوشه‌ها نباید وجود داشته باشد**

### قوانین مهم:

1. ✅ **فایل‌های backend فقط در `backend/`**
2. ✅ **فایل‌های frontend فقط در `frontend/`**
3. ✅ **مستندات مشترک در `backend/docs/` (منبع اصلی)**
4. ✅ **اسکریپت‌های مدیریتی در `backend/scripts/`**

## 🚀 راه‌اندازی

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
flutter pub get
flutter run
```

## 📝 مستندات

- **Backend Docs**: `backend/docs/`
- **Frontend Docs**: `frontend/docs/`
- **Notification Contract**: `backend/docs/notification_contract.md` (منبع اصلی)

## 🔧 اسکریپت‌های مدیریتی

### Restart Backend

```powershell
cd backend/scripts
.\restart-backend.ps1
```

یا مستقیماً:
```powershell
.\backend\scripts\restart-backend.ps1
```

## 📋 ساختار دقیق‌تر

### Backend Structure

```
backend/
├── app/
│   ├── core/              # منطق اصلی (AI, security, scheduler)
│   ├── routers/           # API endpoints
│   ├── models.py          # Database models
│   ├── schemas.py         # Pydantic schemas
│   └── main.py            # FastAPI application
├── scripts/               # اسکریپت‌های مدیریتی
│   ├── restart-backend.ps1
│   └── RESTART_INSTRUCTIONS.md
├── deployment/            # فایل‌های deployment
└── docs/                  # مستندات
```

### Frontend Structure

```
frontend/
├── lib/
│   ├── core/              # Core functionality (auth, network, theme)
│   ├── data/              # Data models and repositories
│   ├── features/          # Feature modules (chat, notification, etc.)
│   └── main.dart
├── assets/                # Static assets
└── docs/                  # Frontend documentation
```

## ⚠️ نکات مهم

1. **هیچ فایل backend در frontend نباشد**
2. **هیچ فایل frontend در backend نباشد**
3. **مستندات مشترک در backend/docs/ نگهداری شود**
4. **اسکریپت‌های مدیریتی در backend/scripts/ باشند**

## 🔗 ارتباط Backend و Frontend

ارتباط بین backend و frontend از طریق:
- **REST API** (تعریف شده در `backend/app/routers/`)
- **Notification Contract** (تعریف شده در `backend/docs/notification_contract.md`)

---

**نسخه:** 2.0.1  
**آخرین به‌روزرسانی:** 2024

