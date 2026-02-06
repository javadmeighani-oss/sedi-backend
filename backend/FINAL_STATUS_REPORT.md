# گزارش وضعیت نهایی برنامه Sedi - Onboarding Flow

**تاریخ:** 2025-01-XX  
**نسخه:** 2.0.1  
**وضعیت:** ✅ آماده برای تست نهایی

---

## 📋 خلاصه اجرایی

برنامه Sedi یک دستیار سلامت هوشمند است که از Flutter (Frontend) و FastAPI (Backend) استفاده می‌کند. جریان Onboarding برای ثبت‌نام کاربران جدید طراحی شده است.

### وضعیت کلی
- ✅ **Frontend:** کامل و آماده
- ✅ **Backend:** کامل و آماده
- ⚠️ **Database Schema:** نیاز به بررسی (ممکن است mismatch وجود داشته باشد)

---

## 🏗️ معماری کلی

### Frontend (Flutter)
- **Framework:** Flutter/Dart
- **State Management:** StatefulWidget + Controllers
- **Local Storage:** SharedPreferences
- **HTTP Client:** `http` package
- **Navigation:** Navigator

### Backend (FastAPI)
- **Framework:** FastAPI (Python)
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy
- **API Style:** RESTful (Query Parameters)

---

## 📱 جریان Onboarding

### 1. Intro Page → Onboarding Page
- کاربر برنامه را باز می‌کند
- Intro Page نمایش داده می‌شود (Sedi's birth page)
- اگر کاربر جدید است → Onboarding Page
- اگر کاربر قبلاً ثبت‌نام کرده → Chat Page

### 2. Onboarding Page
**فایل:** `frontend/lib/features/onboarding/presentation/pages/onboarding_page.dart`

**ویژگی‌ها:**
- ✅ دو فیلد ورودی:
  - **Name:** بدون محدودیت (فقط نباید خالی باشد)
  - **Security Password:** حداقل 6 کاراکتر (هر نوع کاراکتری)
- ✅ Validation real-time
- ✅ نمایش loading state هنگام submit
- ✅ Error handling کامل

**Validation:**
```dart
// Name: فقط نباید خالی باشد
final nameValid = nameText.isNotEmpty;

// Password: حداقل 6 کاراکتر
final isValid = password.length >= 6;
```

### 3. Submit Flow

#### Frontend (`_submitForm`)
1. Validation فرم
2. فراخوانی `ChatService.setupOnboarding(password, language)`
3. دریافت response از backend
4. بررسی `user_id` در response
5. ذخیره Profile در local storage
6. Navigation به ChatPage

#### Backend (`/interact/onboarding`)
1. Validation password (حداقل 6 کاراکتر)
2. بررسی/ایجاد جدول users
3. ایجاد User object با:
   - `secret_key = password`
   - `preferred_language = language`
   - `created_at = datetime.utcnow()`
4. Validation همه فیلدها
5. Add to session → Flush → Commit
6. Generate greeting message (GPT یا fallback)
7. Return response با `user_id`, `message`, `language`

### 4. Local Storage
**فایل:** `frontend/lib/core/utils/user_profile_manager.dart`

**ذخیره می‌شود:**
- `name`: نام کاربر (local only)
- `securityPassword`: رمز امنیتی
- `userId`: شناسه کاربر از backend
- `preferredLanguage`: زبان انتخابی
- `hasSecurityPassword`: true
- `isVerified`: true
- `securityPasswordSetAt`: زمان ثبت

**Storage:** SharedPreferences (key: `user_profile`)

---

## 🔧 فایل‌های کلیدی

### Frontend

#### 1. Onboarding Page
**مسیر:** `frontend/lib/features/onboarding/presentation/pages/onboarding_page.dart`
- مدیریت UI و فرم
- Validation
- Navigation

#### 2. Chat Service
**مسیر:** `frontend/lib/features/chat/chat_service.dart`
- متد: `setupOnboarding(password, language)`
- ارسال request به `/interact/onboarding`
- Parsing response
- Error handling

#### 3. User Profile Manager
**مسیر:** `frontend/lib/core/utils/user_profile_manager.dart`
- `saveProfile(profile)`: ذخیره profile
- `loadProfile()`: بارگذاری profile

#### 4. User Profile Model
**مسیر:** `frontend/lib/data/models/user_profile.dart`
- مدل داده برای UserProfile
- JSON serialization

### Backend

#### 1. Onboarding Endpoint
**مسیر:** `backend/app/routers/interact.py`
- متد: `setup_onboarding(password, language)`
- ایجاد User در database
- Generate greeting
- Return response

#### 2. User Model
**مسیر:** `backend/app/models.py`
```python
class User(Base):
    id: Integer (PK)
    secret_key: String (NOT NULL, NOT UNIQUE)
    preferred_language: String (NOT NULL, DEFAULT 'en')
    created_at: DateTime (NOT NULL, DEFAULT now)
```

#### 3. Database Config
**مسیر:** `backend/app/database.py`
- PostgreSQL connection
- Connection pooling
- Session management

---

## 🔍 Validation Rules

### Frontend
- **Name:** 
  - ✅ نباید خالی باشد
  - ✅ هیچ محدودیت دیگری ندارد
- **Password:**
  - ✅ حداقل 6 کاراکتر
  - ✅ هر نوع کاراکتری مجاز است

### Backend
- **Password:**
  - ✅ حداقل 6 کاراکتر (HTTP 400 اگر کمتر باشد)
- **Language:**
  - ✅ Default: "fa"
  - ✅ اگر خالی باشد → "en"

---

## 🗄️ Database Schema

### Users Table
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    secret_key VARCHAR NOT NULL,
    preferred_language VARCHAR NOT NULL DEFAULT 'en',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### Schema Check
**Script:** `backend/check_schema.py`
```bash
cd backend
python check_schema.py
```

### Schema Fix (اگر نیاز باشد)
**Script:** `backend/fix_schema.py`
```bash
cd backend
python fix_schema.py
```
⚠️ **هشدار:** همه users موجود را حذف می‌کند!

---

## 🚨 مشکلات احتمالی و راه‌حل‌ها

### 1. خطای "Required field is missing"
**علت:** Schema mismatch در database

**راه‌حل:**
```bash
# 1. بررسی schema
cd backend
python check_schema.py

# 2. Fix schema
python fix_schema.py

# 3. Restart backend
sudo systemctl restart sedi-backend
```

**یا Manual Fix:**
```sql
ALTER TABLE users 
  ALTER COLUMN preferred_language SET NOT NULL,
  ALTER COLUMN preferred_language SET DEFAULT 'en',
  ALTER COLUMN created_at SET NOT NULL;
```

### 2. پنجره Onboarding بسته نمی‌شود
**علت:** 
- Backend خطا برمی‌گرداند
- `user_id` در response null است
- Navigation fail می‌کند

**راه‌حل:**
1. بررسی logs backend:
```bash
sudo journalctl -u sedi-backend -f | grep -i "ONBOARDING"
```

2. بررسی logs frontend (Flutter console)

3. بررسی response از backend:
   - باید `user_id` داشته باشد
   - باید `status_code = 200` باشد

### 3. خطای Network
**علت:** Backend در دسترس نیست

**راه‌حل:**
1. بررسی status backend:
```bash
sudo systemctl status sedi-backend
```

2. بررسی connection:
```bash
curl http://localhost:8000/
```

3. بررسی firewall/network

---

## 📊 Logging

### Frontend Logs
**Location:** Flutter Console
**Format:**
```
[ChatService] ========== SETUP ONBOARDING START ==========
[ChatService] Password length: X
[ChatService] Language: fa
[ChatService] Request URL: ...
[ChatService] Response body: ...
```

### Backend Logs
**Location:** Systemd Journal (server) یا Console (local)
**Format:**
```
[ONBOARDING] ========== USER CREATION START ==========
[ONBOARDING] Step 1: Input validation
[ONBOARDING] Step 2: Creating User object...
[ONBOARDING] ✅ User object created
[ONBOARDING] Step 3: Adding to session...
[ONBOARDING] Step 4: Flushing...
[ONBOARDING] Step 5: Committing transaction...
[ONBOARDING] Step 6: Refreshing user to get ID...
[ONBOARDING] ✅ SUCCESS - Returning response with user_id: X
```

**دستورات:**
```bash
# Real-time logs
sudo journalctl -u sedi-backend -f | grep -i "ONBOARDING"

# Last 100 lines
sudo journalctl -u sedi-backend -n 100 | grep -i "ONBOARDING"
```

---

## ✅ Checklist تست

### قبل از تست
- [ ] Backend running است
- [ ] Database connection OK است
- [ ] Schema match است (`python check_schema.py`)
- [ ] Frontend build شده است

### تست Onboarding
- [ ] Intro Page نمایش داده می‌شود
- [ ] Onboarding Page باز می‌شود (برای کاربر جدید)
- [ ] Name field کار می‌کند (بدون محدودیت)
- [ ] Password field کار می‌کند (حداقل 6 کاراکتر)
- [ ] Submit button فعال می‌شود (وقتی فرم valid است)
- [ ] Loading state نمایش داده می‌شود
- [ ] Request به backend ارسال می‌شود
- [ ] Response از backend دریافت می‌شود
- [ ] Profile در local ذخیره می‌شود
- [ ] پنجره Onboarding بسته می‌شود
- [ ] Navigation به ChatPage انجام می‌شود
- [ ] Initial message نمایش داده می‌شود

### تست بعد از Onboarding
- [ ] اگر دوباره برنامه را باز کنیم، Onboarding نمایش داده نمی‌شود
- [ ] مستقیماً به ChatPage می‌رود
- [ ] Profile از local load می‌شود

---

## 🔄 جریان کامل (Flow Diagram)

```
User Opens App
    ↓
Intro Page (Sedi's birth page)
    ↓
Check: Has completed onboarding?
    ├─ YES → Chat Page
    └─ NO → Onboarding Page
            ↓
        User enters:
        - Name (no restrictions)
        - Password (min 6 chars)
            ↓
        User taps Submit
            ↓
        Frontend: setupOnboarding(password, language)
            ↓
        Backend: /interact/onboarding
            ├─ Validate password
            ├─ Create User in DB
            ├─ Generate greeting
            └─ Return {user_id, message, language}
            ↓
        Frontend: Receive response
            ├─ Check user_id exists
            ├─ Save profile locally
            └─ Navigate to ChatPage
            ↓
        Chat Page (with initial message)
```

---

## 📝 نکات مهم

### 1. Name در Backend ذخیره نمی‌شود
- Name فقط در local storage (SharedPreferences) ذخیره می‌شود
- Backend فقط `password` و `language` را دریافت می‌کند
- این طراحی عمدی است (privacy)

### 2. Error Messages
- همه error messages به **انگلیسی** هستند
- چون زبان اصلی Sedi انگلیسی است

### 3. Schema Mismatch
- اگر خطای "Required field is missing" دریافت می‌کنید
- حتماً schema را check و fix کنید
- از `check_schema.py` و `fix_schema.py` استفاده کنید

### 4. GPT Fallback
- اگر GPT service fail کند
- Backend از fallback message استفاده می‌کند
- User creation همچنان موفق می‌شود

---

## 🛠️ دستورات مفید

### Backend
```bash
# Check schema
cd backend
python check_schema.py

# Fix schema (⚠️ deletes all users)
python fix_schema.py

# Restart backend (server)
sudo systemctl restart sedi-backend

# Check logs
sudo journalctl -u sedi-backend -f | grep -i "ONBOARDING"

# Check status
sudo systemctl status sedi-backend
```

### Frontend
```bash
# Build
cd frontend
flutter build apk

# Run
flutter run

# Check logs
flutter logs
```

---

## 📚 مستندات اضافی

- `backend/HOW_TO_FIX_SCHEMA.md` - راهنمای fix schema
- `backend/HOW_TO_CHECK_LOGS.md` - راهنمای بررسی logs
- `backend/fix_schema.py` - Script برای fix schema
- `backend/check_schema.py` - Script برای check schema

---

## ✅ وضعیت نهایی

### Frontend
- ✅ Onboarding Page کامل است
- ✅ Validation درست است
- ✅ Error handling کامل است
- ✅ Navigation درست است
- ✅ Local storage درست است

### Backend
- ✅ Onboarding endpoint کامل است
- ✅ User creation درست است
- ✅ Error handling کامل است
- ✅ Logging کامل است
- ⚠️ Schema ممکن است نیاز به fix داشته باشد

### Database
- ⚠️ نیاز به بررسی schema
- ✅ Model definition درست است

---

## 🎯 اقدامات بعدی

1. **بررسی Schema:**
   ```bash
   cd backend
   python check_schema.py
   ```

2. **Fix Schema (اگر نیاز باشد):**
   ```bash
   python fix_schema.py
   ```

3. **Restart Backend:**
   ```bash
   sudo systemctl restart sedi-backend
   ```

4. **تست کامل:**
   - تست Onboarding flow
   - بررسی logs
   - تست navigation
   - تست local storage

---

**پایان گزارش**

