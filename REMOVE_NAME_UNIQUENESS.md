# حذف محدودیت Unique بودن نام کاربر

**تاریخ:** 2024-12-30  
**هدف:** حذف محدودیت unique بودن name در دیتابیس و اجازه دادن به نام‌های تکراری

---

## 🔍 تغییرات انجام شده

### 1. حذف Unique Constraint از Model

**فایل:** `backend/app/models.py`

**قبل:**
```python
name = Column(String, unique=True, nullable=False)              # نام کاربر
```

**بعد:**
```python
name = Column(String, nullable=False)              # نام کاربر (no unique constraint - allow duplicate names)
```

**نتیجه:** ✅ محدودیت unique از model حذف شد

---

### 2. حذف چک Duplicate Name از Endpoint `/onboarding`

**فایل:** `backend/app/routers/interact.py`

**قبل:**
```python
# Check if name already exists
existing_user = db.query(User).filter(User.name == name).first()
if existing_user:
    raise HTTPException(status_code=400, detail="User name already exists")

# Create new user
```

**بعد:**
```python
# Create new user (no name uniqueness check - allow duplicate names)
```

**نتیجه:** ✅ چک duplicate name حذف شد

---

### 3. حذف چک Duplicate Name از Endpoint `/introduce`

**فایل:** `backend/app/routers/interact.py`

**قبل:**
```python
# Check if new name is already taken
name_taken = db.query(User).filter(
    User.name == name,
    User.id != user_id
).first()
if name_taken:
    raise HTTPException(status_code=400, detail="User name already exists")
```

**بعد:**
```python
# Upgrade anonymous user to registered user (no name uniqueness check)
```

**قبل:**
```python
# Check if name already exists
existing_user = db.query(User).filter(User.name == name).first()
if existing_user:
    raise HTTPException(status_code=400, detail="User already exists")
```

**بعد:**
```python
# Create new user (no name uniqueness check - allow duplicate names)
```

**نتیجه:** ✅ چک duplicate name از `/introduce` هم حذف شد

---

### 4. حذف چک Duplicate Name از ConversationBrain

**فایل:** `backend/app/core/conversation/brain.py`

**قبل:**
```python
# Check if name is already taken by another user
existing_user = self.db.query(User).filter(
    User.name == name,
    User.id != user_id
).first()

if not existing_user:
    # Save name to user
    user.name = name
    self.db.commit()
    self.db.refresh(user)
```

**بعد:**
```python
# Save name to user (no uniqueness check - allow duplicate names)
user.name = name
self.db.commit()
self.db.refresh(user)
```

**نتیجه:** ✅ چک duplicate name از ConversationBrain هم حذف شد

---

## 📋 فایل‌های تغییر یافته

1. ✅ `backend/app/models.py` - حذف `unique=True` از `name`
2. ✅ `backend/app/routers/interact.py` - حذف چک duplicate name از `/onboarding` و `/introduce`
3. ✅ `backend/app/core/conversation/brain.py` - حذف چک duplicate name از `_save_user_name_if_provided`

---

## ⚠️ نکات مهم

### 1. Database Migration
اگر unique constraint در دیتابیس وجود دارد، باید migration انجام شود:
```sql
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_name_key;
```

### 2. رفتار جدید
- ✅ نام‌های تکراری مجاز هستند
- ✅ هر کاربر می‌تواند هر نامی را انتخاب کند
- ✅ هیچ چک duplicate انجام نمی‌شود

### 3. شناسایی کاربر
- کاربران با `user_id` شناسایی می‌شوند (نه با name)
- `name` فقط برای نمایش استفاده می‌شود

---

## 🔄 Flow جدید

```
User Submits Onboarding
        ↓
Validate Password (>= 6 characters) ✅
        ↓
Create User (no name check) ✅
        ↓
Save to Database ✅
        ↓
Return user_id ✅
```

---

## ✅ نتیجه

**محدودیت unique بودن name حذف شد:**
- ✅ Model: `unique=True` حذف شد
- ✅ `/onboarding`: چک duplicate حذف شد
- ✅ `/introduce`: چک duplicate حذف شد
- ✅ ConversationBrain: چک duplicate حذف شد

**نتیجه:** حالا کاربران می‌توانند نام‌های تکراری استفاده کنند و خطای "User name already exists" دیگر نمایش داده نمی‌شود.

---

**وضعیت:** ✅ **تمام محدودیت‌های unique بودن name حذف شد**

