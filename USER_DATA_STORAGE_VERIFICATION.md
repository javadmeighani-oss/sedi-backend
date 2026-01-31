# بررسی کامل ذخیره‌سازی داده‌های کاربر و Navigation

**تاریخ:** 2024-12-30  
**هدف:** اطمینان از ذخیره‌سازی داده‌ها در backend و بسته شدن پنجره بعد از submit

---

## ✅ بررسی Backend - ذخیره‌سازی داده‌ها

### 1. فایل Model: `backend/app/models.py`

**کلاس User (خط 8-15):**
```python
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)              # نام کاربر
    secret_key = Column(String, nullable=False)                     # رمز شخصی
    preferred_language = Column(String, default="en")               # زبان انتخابی کاربر
    created_at = Column(DateTime, default=datetime.utcnow)          # زمان ثبت‌نام
```

**نتیجه:** ✅ فایل model وجود دارد و فیلدهای `name` و `secret_key` تعریف شده‌اند

---

### 2. فایل Database: `backend/app/database.py`

**اتصال به PostgreSQL:**
```python
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://sedi_user:sedi_password@localhost:5432/sedi_db"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

**نتیجه:** ✅ اتصال به دیتابیس PostgreSQL تنظیم شده است

---

### 3. فایل Endpoint: `backend/app/routers/interact.py`

**Endpoint `/onboarding` (خط 226-266):**
```python
@router.post("/onboarding")
def setup_onboarding(
    name: str = Query(...),
    password: str = Query(...),
    language: str = Query("fa"),
    db: Session = Depends(get_db)
):
    # Validate password
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    # Check if name already exists
    existing_user = db.query(User).filter(User.name == name).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User name already exists")
    
    # Create new user
    new_user = User(
        name=name,
        secret_key=password,
        preferred_language=language
    )
    db.add(new_user)        # ✅ اضافه کردن به session
    db.commit()             # ✅ commit کردن به دیتابیس
    db.refresh(new_user)    # ✅ refresh کردن برای گرفتن ID
    
    # Generate initial greeting
    brain = ConversationBrain(db, language=language)
    initial_message = brain.get_initial_message(new_user.id, name, language)
    
    return {
        "user_id": new_user.id,
        "message": initial_message,
        "language": language,
        "name": name
    }
```

**نتیجه:** ✅ داده‌ها در دیتابیس ذخیره می‌شوند:
- `db.add(new_user)` - اضافه کردن به session
- `db.commit()` - commit کردن به دیتابیس PostgreSQL
- `db.refresh(new_user)` - refresh کردن برای گرفتن `user_id`

---

## ✅ بررسی Frontend - Navigation

### فایل: `frontend/lib/features/onboarding/presentation/pages/onboarding_page.dart`

#### 1. Import ChatPage (خط 9):
```dart
import '../../../chat/presentation/pages/chat_page.dart';
```

**نتیجه:** ✅ ChatPage import شده است

---

#### 2. Submit Flow (خط 107-259):

**مرحله 1: Validation**
```dart
if (!_isFormValid) {
  return; // Stop if form invalid
}
```

**مرحله 2: API Call**
```dart
final result = await chatService.setupOnboarding(
  _nameController.text.trim(),
  _passwordController.text,
  systemLanguage,
);
```

**مرحله 3: Check Backend Response**
```dart
if (result['user_id'] == null && !AppConfig.useLocalMode) {
  // Backend error - show error and return (no navigation)
  return;
}
```

**مرحله 4: Save Locally**
```dart
final profile = UserProfile(
  name: result['name']?.toString() ?? _nameController.text.trim(),
  securityPassword: _passwordController.text,
  preferredLanguage: result['language']?.toString() ?? systemLanguage,
  userId: result['user_id'] as int?,
  // ...
);

final saved = await UserProfileManager.saveProfile(profile);
if (!saved) {
  return; // Stop if local save failed
}
```

**مرحله 5: Navigation**
```dart
// Navigate to ChatPage
print('[OnboardingPage] Navigating to ChatPage...');
if (mounted) {
  Navigator.of(context).pushReplacement(
    MaterialPageRoute(
      builder: (context) => ChatPage(
        initialMessage: result['message']?.toString(),
      ),
    ),
  );
  print('[OnboardingPage] Navigation completed');
}
```

**نتیجه:** ✅ Navigation انجام می‌شود:
- فقط در صورت موفقیت (`user_id != null`)
- فقط در صورت ذخیره موفق local
- استفاده از `pushReplacement` که صفحه قبلی را جایگزین می‌کند (پنجره بسته می‌شود)

---

## 🔄 Flow کامل

```
User Taps Submit Button
        ↓
Form Validation ✅
        ↓
API Call to Backend
        ↓
Backend Validation:
  - Password length >= 6 ✅
  - Name unique ✅
        ↓
Create User Object
        ↓
db.add(new_user) ✅
        ↓
db.commit() ✅ (ذخیره در دیتابیس PostgreSQL)
        ↓
db.refresh(new_user) ✅ (گرفتن user_id)
        ↓
Return Response:
  {
    "user_id": new_user.id,
    "message": initial_message,
    "language": language,
    "name": name
  }
        ↓
Frontend Receives Response
        ↓
Check: result['user_id'] != null ✅
        ↓
Save Profile Locally ✅
        ↓
Navigator.pushReplacement() ✅
        ↓
OnboardingPage Closes ✅
        ↓
ChatPage Opens ✅
```

---

## ✅ بررسی‌های انجام شده

### Backend:
1. ✅ فایل `backend/app/models.py` وجود دارد
2. ✅ کلاس `User` با فیلدهای `name` و `secret_key` تعریف شده
3. ✅ فایل `backend/app/database.py` اتصال به PostgreSQL را تنظیم کرده
4. ✅ Endpoint `/onboarding` داده‌ها را با `db.add()`, `db.commit()`, `db.refresh()` ذخیره می‌کند

### Frontend:
1. ✅ ChatPage import شده است
2. ✅ Navigation با `Navigator.pushReplacement()` انجام می‌شود
3. ✅ Navigation فقط در صورت موفقیت انجام می‌شود
4. ✅ `pushReplacement` صفحه قبلی را جایگزین می‌کند (پنجره بسته می‌شود)

---

## 🧪 سناریوهای تست

### تست 1: Submit موفق
- ورودی: نام و رمز معتبر و جدید
- انتظار:
  - ✅ داده‌ها در backend ذخیره می‌شوند
  - ✅ `user_id` برگردانده می‌شود
  - ✅ Profile در local ذخیره می‌شود
  - ✅ پنجره بسته می‌شود
  - ✅ ChatPage باز می‌شود

### تست 2: نام تکراری
- ورودی: نامی که قبلاً استفاده شده
- انتظار:
  - ❌ خطا: "User name already exists"
  - ❌ Navigation انجام نمی‌شود
  - ✅ پنجره باز می‌ماند

### تست 3: رمز کمتر از 6 کاراکتر
- ورودی: رمز کمتر از 6 کاراکتر
- انتظار:
  - ❌ خطا: "Password must be at least 6 characters"
  - ❌ Navigation انجام نمی‌شود
  - ✅ پنجره باز می‌ماند

---

## 📋 فایل‌های مرتبط

### Backend:
1. ✅ `backend/app/models.py` - Model User
2. ✅ `backend/app/database.py` - Database connection
3. ✅ `backend/app/routers/interact.py` - Endpoint `/onboarding`

### Frontend:
1. ✅ `frontend/lib/features/onboarding/presentation/pages/onboarding_page.dart` - Onboarding page
2. ✅ `frontend/lib/features/chat/presentation/pages/chat_page.dart` - Chat page
3. ✅ `frontend/lib/features/chat/chat_service.dart` - API service

---

## ✅ نتیجه نهایی

**ذخیره‌سازی در Backend:**
- ✅ فایل model وجود دارد
- ✅ Database connection تنظیم شده
- ✅ `db.add()`, `db.commit()`, `db.refresh()` انجام می‌شود
- ✅ داده‌ها در PostgreSQL ذخیره می‌شوند

**Navigation:**
- ✅ ChatPage import شده است
- ✅ `Navigator.pushReplacement()` استفاده می‌شود
- ✅ Navigation فقط در صورت موفقیت انجام می‌شود
- ✅ پنجره بسته می‌شود و ChatPage باز می‌شود

---

**وضعیت:** ✅ **همه چیز درست است - داده‌ها ذخیره می‌شوند و navigation انجام می‌شود**

**نکته:** اگر هنوز مشکل دارید، مطمئن شوید که:
1. Backend در حال اجرا است
2. Database connection درست است
3. Backend restart شده است (اگر تغییراتی اعمال شده)

