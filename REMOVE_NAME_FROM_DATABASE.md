# حذف فیلد Name از دیتابیس Backend

**تاریخ:** 2024-12-30  
**هدف:** حذف کامل فیلد `name` از دیتابیس backend - name فقط در local storage frontend ذخیره می‌شود

---

## 🔍 تغییرات انجام شده

### 1. حذف Name از Model

**فایل:** `backend/app/models.py`

**قبل:**
```python
id = Column(Integer, primary_key=True, index=True)
name = Column(String, nullable=False)
secret_key = Column(String, nullable=False)
```

**بعد:**
```python
id = Column(Integer, primary_key=True, index=True)
secret_key = Column(String, nullable=False)
```

**نتیجه:** ✅ فیلد `name` از model حذف شد

---

### 2. حذف Name از Endpoint `/onboarding`

**فایل:** `backend/app/routers/interact.py`

**قبل:**
```python
@router.post("/onboarding")
def setup_onboarding(
    name: str = Query(...),
    password: str = Query(...),
    language: str = Query("fa"),
    ...
):
    new_user = User(
        name=name,
        secret_key=password,
        preferred_language=language
    )
    return {
        "user_id": new_user.id,
        "message": initial_message,
        "language": language,
        "name": name
    }
```

**بعد:**
```python
@router.post("/onboarding")
def setup_onboarding(
    password: str = Query(...),
    language: str = Query("fa"),
    ...
):
    new_user = User(
        secret_key=password,
        preferred_language=language
    )
    return {
        "user_id": new_user.id,
        "message": initial_message,
        "language": language
    }
```

**نتیجه:** ✅ `name` از endpoint حذف شد

---

### 3. حذف Name از Endpoint `/introduce`

**فایل:** `backend/app/routers/interact.py`

**قبل:**
```python
@router.post("/introduce")
def introduce_user(
    name: str = Query(...),
    secret_key: str = Query(...),
    ...
):
    existing_user.name = name
    new_user = User(name=name, secret_key=secret_key, ...)
```

**بعد:**
```python
@router.post("/introduce")
def introduce_user(
    secret_key: str = Query(...),
    ...
):
    # No name assignment
    new_user = User(secret_key=secret_key, ...)
```

**نتیجه:** ✅ `name` از endpoint حذف شد

---

### 4. حذف Name از Endpoint `/chat`

**فایل:** `backend/app/routers/interact.py`

**قبل:**
```python
def chat_with_sedi(
    name: Optional[str] = Query(None),
    secret_key: Optional[str] = Query(None),
    ...
):
    user = db.query(User).filter(
        User.name == name,
        User.secret_key == secret_key
    ).first()
    anonymous_name = f"anonymous_{uuid.uuid4().hex[:12]}"
    user = User(name=anonymous_name, ...)
```

**بعد:**
```python
def chat_with_sedi(
    secret_key: Optional[str] = Query(None),
    ...
):
    user = db.query(User).filter(
        User.secret_key == secret_key
    ).first()
    anonymous_secret = "temp_" + uuid.uuid4().hex[:12]
    user = User(secret_key=anonymous_secret, ...)
```

**نتیجه:** ✅ `name` از endpoint حذف شد

---

### 5. حذف Name از Endpoint `/history`

**فایل:** `backend/app/routers/interact.py`

**قبل:**
```python
@router.get("/history")
def get_user_history(
    name: str = Query(...),
    secret_key: str = Query(...),
    ...
):
    user = db.query(User).filter(
        User.name == name,
        User.secret_key == secret_key
    ).first()
```

**بعد:**
```python
@router.get("/history")
def get_user_history(
    secret_key: str = Query(...),
    ...
):
    user = db.query(User).filter(
        User.secret_key == secret_key
    ).first()
```

**نتیجه:** ✅ `name` از endpoint حذف شد

---

### 6. حذف استفاده از user.name در سایر فایل‌ها

**فایل‌های تغییر یافته:**
- ✅ `backend/app/core/conversation/brain.py` - حذف `user.name`
- ✅ `backend/app/core/conversation/memory.py` - `get_user_name()` همیشه `None` برمی‌گرداند
- ✅ `backend/app/routers/ai_core.py` - `user_name=None`
- ✅ `backend/app/routers/health.py` - `user_name=None`
- ✅ `backend/app/routers/medical.py` - حذف `name` از response
- ✅ `backend/app/core/scheduler.py` - `user_name="my friend"`

---

### 7. تغییر Frontend

**فایل:** `frontend/lib/features/chat/chat_service.dart`

**قبل:**
```dart
Future<Map<String, dynamic>> setupOnboarding(
  String userName,
  String password,
  String language,
) async {
  final queryParams = <String, String>{
    'name': userName,
    'password': password,
    'language': language,
  };
  return {
    'name': body['name']?.toString() ?? userName,
    ...
  };
}
```

**بعد:**
```dart
Future<Map<String, dynamic>> setupOnboarding(
  String password,
  String language,
) async {
  final queryParams = <String, String>{
    'password': password,
    'language': language,
  };
  return {
    // No name in response
    ...
  };
}
```

**نتیجه:** ✅ `name` از API call حذف شد

**فایل:** `frontend/lib/features/onboarding/presentation/pages/onboarding_page.dart`

**تغییر:**
- ✅ `setupOnboarding` بدون `name` فراخوانی می‌شود
- ✅ `name` فقط در local storage ذخیره می‌شود (نه در backend)

---

## 📋 فایل‌های تغییر یافته

### Backend:
1. ✅ `backend/app/models.py` - حذف `name` از model
2. ✅ `backend/app/routers/interact.py` - حذف `name` از endpoints
3. ✅ `backend/app/core/conversation/brain.py` - حذف استفاده از `user.name`
4. ✅ `backend/app/core/conversation/memory.py` - `get_user_name()` همیشه `None`
5. ✅ `backend/app/routers/ai_core.py` - `user_name=None`
6. ✅ `backend/app/routers/health.py` - `user_name=None`
7. ✅ `backend/app/routers/medical.py` - حذف `name` از response
8. ✅ `backend/app/core/scheduler.py` - `user_name="my friend"`

### Frontend:
9. ✅ `frontend/lib/features/chat/chat_service.dart` - حذف `name` از API call
10. ✅ `frontend/lib/features/onboarding/presentation/pages/onboarding_page.dart` - `name` فقط local

---

## 🔄 Flow جدید

### Onboarding:
```
User Enters Name & Password
        ↓
Name Stored Locally Only ✅
        ↓
Backend API Call (password + language only)
        ↓
Backend Creates User (no name)
        ↓
Returns user_id + message
        ↓
Frontend Saves Profile Locally (with name)
        ↓
Navigate to ChatPage
```

### User Identification:
- ✅ Users identified by `user_id` (not name)
- ✅ Authentication by `secret_key` (password)
- ✅ Name stored locally in frontend only

---

## ⚠️ نکات مهم

### 1. Database Migration
اگر فیلد `name` در دیتابیس وجود دارد، باید migration انجام شود:
```sql
ALTER TABLE users DROP COLUMN IF EXISTS name;
```

### 2. Frontend Local Storage
- ✅ Name در `UserProfile` (local storage) ذخیره می‌شود
- ✅ Name برای نمایش در UI استفاده می‌شود
- ✅ Name به backend ارسال نمی‌شود

### 3. User Identification
- ✅ Users با `user_id` شناسایی می‌شوند
- ✅ Authentication با `secret_key` انجام می‌شود
- ✅ Name فقط برای نمایش در frontend استفاده می‌شود

---

## ✅ نتیجه

**فیلد `name` از دیتابیس backend حذف شد:**
- ✅ Model: `name` حذف شد
- ✅ Endpoints: `name` از تمام endpoints حذف شد
- ✅ Queries: تمام query های بر اساس `name` حذف شدند
- ✅ Frontend: `name` فقط در local storage ذخیره می‌شود

**نتیجه:** Name دیگر در backend ذخیره نمی‌شود و فقط در local storage frontend نگه‌داری می‌شود.

---

**وضعیت:** ✅ **تمام استفاده‌ها از `name` در backend حذف شد**

**نکته:** Backend باید restart شود و migration انجام شود (اگر فیلد در دیتابیس وجود دارد).

