# گزارش آخرین تغییرات Backend - Sedi

**تاریخ:** 2026-02-02  
**آخرین Commit:** `ad8b018`  
**Branch:** `main`  
**Repository:** `javadmeighani-oss/sedi-backend`

---

## 📋 خلاصه تغییرات

این گزارش شامل تمام تغییرات انجام شده در فازهای اخیر پروژه Sedi Backend است که شامل سیستم نوتیفیکیشن، سیستم پزشکی، حافظه و سبک زندگی، و بهبودهای امنیتی می‌باشد.

---

## 🔄 آخرین تغییر (Commit: ad8b018)

### بهبود Workflow Deploy و امنیت SSH

**فایل تغییر یافته:**
- `.github/workflows/deploy-backend.yml`

**تغییرات:**
1. ✅ استفاده از نام کامل systemd unit: `sedi-backend.service` به جای `sedi-backend`
2. ✅ حذف `StrictHostKeyChecking=no` از دستورات SSH
3. ✅ بهبود امنیت SSH با استفاده از `known_hosts` که قبلاً با `ssh-keyscan` پر شده است
4. ✅ حفظ `BatchMode=yes` و `ConnectTimeout=10` برای اتصال غیرتعاملی

**قبل:**
```yaml
systemctl restart sedi-backend
systemctl status sedi-backend
ssh -o StrictHostKeyChecking=no -o BatchMode=yes ...
```

**بعد:**
```yaml
systemctl restart sedi-backend.service
systemctl status sedi-backend.service
ssh -o BatchMode=yes -o ConnectTimeout=10 ...
```

---

## 📦 فاز 9.4: Notification Triggers + Feedback

**Commit:** `0fa0d91`

### ویژگی‌های اضافه شده:

#### 1. Scheduler Triggers
- ✅ **Morning Notification (9AM)**: نوتیفیکیشن صبحگاهی در ساعت 9 صبح (قابل تنظیم برای هر کاربر)
- ✅ **Inactivity Notification (4h)**: نوتیفیکیشن عدم فعالیت بعد از 4 ساعت عدم چت
- ✅ **Deduplication & Cooldown**: جلوگیری از اسپم با محدودیت‌های زمانی

#### 2. Feedback Endpoint
- ✅ `POST /notifications/{notification_id}/feedback`
- ✅ ذخیره واکنش‌های like/dislike در `UserMemoryFact`
- ✅ تنظیم خودکار زمان نوتیفیکیشن صبحگاهی بر اساس بازخورد

#### 3. فایل‌های تغییر یافته:
- `app/core/scheduler.py` - اضافه شدن دو job جدید
- `app/routers/notifications.py` - اضافه شدن endpoint feedback
- `app/services/notification_engine/decision_engine.py` - یکپارچه‌سازی triggers

---

## 🧠 فاز 9.3: Lifestyle & Memory Foundation

**Commit:** `3bdfab1`

### مدل‌های جدید Database:

#### 1. DailyMemorySummary
```python
- id, user_id (FK)
- summary (text)
- mood (string, nullable)
- context (text, nullable)
- last_interaction (datetime, nullable)
- created_at (datetime)
```

#### 2. UserMemoryFact
```python
- id, user_id (FK)
- domain (string, indexed)
- key (string, indexed)
- value_json (text)  # JSON string
- confidence (float, default 0.7)
- source (string: chat|device|manual)
- last_seen_at (datetime, nullable)
- embedding_id (string, nullable)  # RAG-ready
- created_at, updated_at
```

### Router Updates:

#### 1. Memory Router (`app/routers/memory.py`)
- ✅ `POST /save` - ایجاد `DailyMemorySummary`
- ✅ `GET /latest` - خواندن آخرین `DailyMemorySummary`

#### 2. Lifestyle Router (`app/routers/lifestyle.py`)
- ✅ `POST /lifestyle/update` - آپدیت/ایجاد `UserMemoryFact`
- ✅ `GET /lifestyle/context?user_id=1` - دریافت `MemoryContext`

### Service Layer جدید:

#### 1. Memory Services
- `app/services/memory/memory_contract.py` - تعریف domains/keys
- `app/services/memory/memory_repository.py` - CRUD operations
- `app/services/memory/memory_context.py` - ساخت MemoryContext برای DecisionEngine

#### 2. DecisionEngine Integration
- ✅ استفاده از `MemoryContext` برای نوتیفیکیشن‌های شخصی‌سازی شده
- ✅ قوانین lifestyle: خواب کم، هیدراسیون کم، عدم فعالیت

---

## 💊 فاز 9.1.2: Medical Data Seed

**Commit:** `8d3245f`

### Script Seed Medical Data:

#### فایل‌های ایجاد شده:
- `scripts/seed_medical_data.json` - داده‌های اولیه
- `scripts/seed_medical_data.py` - اسکریپت seed

#### داده‌های Seed شده:

**13 Medical Condition:**
1. ALS (Amyotrophic Lateral Sclerosis) - severity: high, chronic: true
2. MS (Multiple Sclerosis) - severity: high, chronic: true
3. DIABETES_T2
4. HYPERTENSION
5. ARRHYTHMIA
6. HEART_FAILURE
7. ASTHMA_COPD
8. CHRONIC_BACK_PAIN
9. KNEE_OSTEOARTHRITIS
10. MIGRAINE
11. INSOMNIA
12. ANXIETY
13. DEPRESSION_MILD

**8 Medication:**
1. Riluzole → ALS
2. Interferon_beta → MS
3. Metformin → DIABETES_T2
4. Insulin_Generic → DIABETES_T2
5. Amlodipine → HYPERTENSION
6. Losartan → HYPERTENSION
7. Atorvastatin → CARDIO_GENERAL
8. Sertraline → ANXIETY / DEPRESSION_MILD

**ویژگی‌های Script:**
- ✅ Idempotent (امن برای اجرای چندباره)
- ✅ بررسی وجود قبل از insert
- ✅ خروجی واضح: inserted/skipped counts

---

## 🏥 فاز 9.1: Medical Notification System

**Commit:** `7c49d59`

### مدل‌های Database جدید:

#### 1. MedicalCondition
```python
- id, code (unique, uppercase)
- name, chronic (boolean)
- severity_level ("low" | "medium" | "high")
- keywords (JSON array)
- embedding_id (nullable)  # RAG-ready
- created_at, updated_at
```

#### 2. Medication
```python
- id, name, generic_name (nullable)
- condition_id (FK MedicalCondition)
- dosage_info (text, nullable)
- keywords (JSON array)
- embedding_id (nullable)  # RAG-ready
- created_at, updated_at
```

#### 3. UserCondition
```python
- id, user_id (FK users)
- condition_id (FK MedicalCondition)
- diagnosed_at (datetime, nullable)
- severity_notes (text, nullable)
- embedding_id (nullable)  # RAG-ready
- created_at, updated_at
```

### Service Layer جدید:

#### 1. Medical Service (`app/services/medical/`)
- `medical_service.py` - تشخیص و جستجوی شرایط پزشکی
- `condition_detector.py` - تشخیص شرایط از متن

#### 2. Notification Engine (`app/services/notification_engine/`)
- `decision_engine.py` - موتور تصمیم‌گیری برای نوتیفیکیشن‌ها
- `notification_builder.py` - ساختاردهی نوتیفیکیشن‌ها
- `timing_rules.py` - قوانین زمان‌بندی

#### 3. RAG Service (`app/services/rag/`)
- `rag_interface.py` - رابط RAG (بدون پیاده‌سازی کامل)
- آماده برای یکپارچه‌سازی در آینده

### Router Updates:

#### 1. Medical Router (`app/routers/medical.py`)
- ✅ لیست شرایط پزشکی
- ✅ اختصاص شرایط به کاربر

#### 2. Router Refactoring
- ✅ تمام routers از `DecisionEngine` و `NotificationBuilder` استفاده می‌کنند
- ✅ هیچ router مستقیماً notification ایجاد نمی‌کند

**Routers به‌روز شده:**
- `app/routers/health.py`
- `app/routers/data.py`
- `app/routers/medical.py`
- `app/routers/device.py`
- `app/routers/ai_core.py`

---

## 🔔 فاز اولیه: Notification System

**Commit:** `fbe6815`

### مدل Database:

#### Notification Model
```python
- id (Integer, primary key)
- user_id (ForeignKey -> users.id, indexed)
- type (String)  # e.g. HEALTH, REMINDER, INSIGHT, morning_summary, inactive_ping
- title (String)
- body (String)
- priority (String)  # low | normal | high | critical
- is_read (Boolean, default False)
- is_sent (Boolean, default False)
- scheduled_for (DateTime, nullable=True)
- created_at (DateTime, default now)
```

### Schemas:

#### فایل: `app/schemas/notification.py`
- `NotificationBase`
- `NotificationCreate`
- `NotificationResponse`

### Router:

#### `app/routers/notifications.py`
- ✅ `GET /notifications?user_id={id}` - لیست نوتیفیکیشن‌ها
- ✅ `POST /notifications/{notification_id}/read` - علامت‌گذاری به عنوان خوانده شده
- ✅ `POST /notifications/{notification_id}/feedback` - بازخورد like/dislike

---

## 📁 ساختار فایل‌های ایجاد/تغییر یافته

### فایل‌های جدید:

```
backend/
├── app/
│   ├── models.py (updated)
│   ├── routers/
│   │   ├── notifications.py (updated)
│   │   ├── medical.py (updated)
│   │   ├── memory.py (updated)
│   │   └── lifestyle.py (new)
│   ├── schemas/
│   │   └── notification.py (new)
│   ├── services/
│   │   ├── medical/
│   │   │   ├── medical_service.py (new)
│   │   │   └── condition_detector.py (new)
│   │   ├── notification_engine/
│   │   │   ├── decision_engine.py (new)
│   │   │   ├── notification_builder.py (new)
│   │   │   └── timing_rules.py (new)
│   │   ├── memory/
│   │   │   ├── memory_contract.py (new)
│   │   │   ├── memory_repository.py (new)
│   │   │   └── memory_context.py (new)
│   │   └── rag/
│   │       └── rag_interface.py (new)
│   └── core/
│       └── scheduler.py (updated)
├── scripts/
│   ├── seed_medical_data.py (new)
│   └── seed_medical_data.json (new)
└── .github/
    └── workflows/
        └── deploy-backend.yml (updated)
```

---

## 🔒 بهبودهای امنیتی

1. ✅ **SSH Security**: حذف `StrictHostKeyChecking=no` و استفاده از `known_hosts`
2. ✅ **Systemd Unit Naming**: استفاده از نام کامل unit برای جلوگیری از خطا
3. ✅ **Input Validation**: اعتبارسنجی ورودی‌ها در تمام endpoints
4. ✅ **Idempotent Scripts**: اسکریپت‌های seed قابل اجرای چندباره بدون خطا

---

## 🧪 تست‌ها و Verification

### دستورات تست:

#### 1. تست Seed Medical Data:
```bash
cd backend
python scripts/seed_medical_data.py
```

#### 2. تست Notification Endpoints:
```bash
# لیست نوتیفیکیشن‌ها
curl http://localhost:8000/notifications?user_id=1

# علامت‌گذاری به عنوان خوانده شده
curl -X POST http://localhost:8000/notifications/1/read

# ارسال بازخورد
curl -X POST http://localhost:8000/notifications/1/feedback \
  -H "Content-Type: application/json" \
  -d '{"reaction": "like"}'
```

#### 3. تست Lifestyle Endpoints:
```bash
# آپدیت lifestyle
curl -X POST http://localhost:8000/lifestyle/update \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "entries": [
      {"domain": "lifestyle", "key": "sleep_duration_hours", "value": 6.5, "confidence": 0.8, "source": "manual"}
    ]
  }'

# دریافت context
curl http://localhost:8000/lifestyle/context?user_id=1
```

#### 4. بررسی وضعیت Service:
```bash
systemctl status sedi-backend.service
systemctl restart sedi-backend.service
```

---

## 🚀 Deploy Status

### آخرین Deploy:
- **Commit:** `ad8b018`
- **Status:** ✅ Pushed to GitHub
- **Workflow:** ✅ Triggered automatically
- **Server:** 91.107.168.130

### بررسی Deploy:
- GitHub Actions: https://github.com/javadmeighani-oss/sedi-backend/actions
- API Endpoint: http://91.107.168.130:8000/

---

## 📝 نکات مهم

1. ✅ **Backward Compatibility**: تمام تغییرات با کد موجود سازگار هستند
2. ✅ **RAG-Ready**: فیلدهای `embedding_id` برای آماده‌سازی RAG اضافه شده‌اند اما فعلاً NULL هستند
3. ✅ **No Breaking Changes**: هیچ تغییری در API contracts موجود ایجاد نشده است
4. ✅ **Idempotent**: تمام اسکریپت‌های seed قابل اجرای چندباره هستند
5. ✅ **Production Ready**: تمام کدها آماده production هستند

---

## 🔮 آماده برای آینده

### RAG Integration Points:
- `MedicalCondition.embedding_id`
- `Medication.embedding_id`
- `UserCondition.embedding_id`
- `UserMemoryFact.embedding_id`
- `app/services/rag/rag_interface.py` - رابط آماده

### Scheduler Jobs:
- ✅ Morning notifications (9AM default)
- ✅ Inactivity notifications (4h threshold)
- 🔄 آماده برای jobs بیشتر

---

## 📊 آمار تغییرات

- **Total Commits:** 10+ commits
- **Files Created:** ~15 فایل جدید
- **Files Modified:** ~10 فایل
- **Database Models Added:** 5 مدل جدید
- **API Endpoints Added:** 5+ endpoint جدید
- **Service Layers:** 4 لایه service جدید

---

## ✅ Checklist نهایی

- [x] تمام تغییرات در GitHub push شده‌اند
- [x] Workflow deploy به‌روزرسانی شده است
- [x] امنیت SSH بهبود یافته است
- [x] Systemd unit naming اصلاح شده است
- [x] تمام endpoints تست شده‌اند
- [x] Backward compatibility حفظ شده است
- [x] Documentation کامل است

---

**تهیه شده در:** 2026-02-02  
**آخرین بروزرسانی:** Commit `ad8b018`
