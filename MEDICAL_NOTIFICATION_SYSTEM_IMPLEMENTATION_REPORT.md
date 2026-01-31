# گزارش پیاده‌سازی سیستم اعلان‌های پزشکی (Medical Notification System)

**فاز:** 9.1 – Medical Notification System (Plan B + RAG-Ready)  
**تاریخ:** 2024  
**وضعیت:** ✅ **پیاده‌سازی کامل**

---

## 📋 خلاصه

پیاده‌سازی معماری اعلان‌های پزشکی که:
- ✅ کاملاً عملکردی است بدون RAG
- ✅ طراحی شده برای پشتیبانی از RAG در آینده
- ✅ بدون تغییر در API contracts موجود
- ✅ بدون تغییر در frontend
- ✅ بدون وابستگی‌های سنگین

---

## 🏗️ معماری پیاده‌سازی شده

### Flow کلی:
```
Router → DecisionEngine → NotificationBuilder → Database
                ↓
         MedicalService (condition detection)
                ↓
         RAGService (interfaces only, optional)
```

**قانون:** هیچ router مستقیماً Notification ایجاد نمی‌کند. همه از DecisionEngine استفاده می‌کنند.

---

## 📦 فایل‌های ایجاد شده

### 1. Database Models (`app/models.py`)

**مدل‌های جدید:**

#### `MedicalCondition`
- `id` (Integer, primary key)
- `name` (String, unique) - نام بیماری
- `description` (String, nullable) - توضیحات
- `category` (String, nullable) - دسته‌بندی
- `embedding_id` (String, nullable) - **برای RAG**
- `created_at` (DateTime)

#### `Medication`
- `id` (Integer, primary key)
- `name` (String) - نام دارو
- `generic_name` (String, nullable) - نام ژنریک
- `dosage_form` (String, nullable) - فرم دارو
- `default_dosage` (String, nullable) - دوز پیش‌فرض
- `embedding_id` (String, nullable) - **برای RAG**
- `created_at` (DateTime)

#### `UserCondition`
- `id` (Integer, primary key)
- `user_id` (ForeignKey -> users.id, indexed)
- `condition_id` (ForeignKey -> medical_conditions.id)
- `diagnosed_date` (DateTime, nullable)
- `severity` (String, nullable) - mild, moderate, severe
- `notes` (String, nullable)
- `embedding_id` (String, nullable) - **برای RAG**
- `created_at` (DateTime)

---

### 2. Schemas (`app/schemas/medical.py`)

**اسکیماهای ایجاد شده:**
- `MedicalConditionBase`, `MedicalConditionCreate`, `MedicalConditionResponse`
- `MedicationBase`, `MedicationCreate`, `MedicationResponse`
- `UserConditionBase`, `UserConditionCreate`, `UserConditionResponse`

**Export در:** `app/schemas/__init__.py`

---

### 3. Service Layers

#### `app/services/__init__.py`
- Export تمام service classes

#### `app/services/medical.py` - MedicalService
**وظایف:**
- Condition lookup و search
- User condition management (assign, remove)
- Condition detection from health data (rule-based, Plan B)
- Medication lookup و search

**RAG-Ready:**
- `embedding_id` fields در همه مدل‌ها
- TODO comments برای RAG integration

#### `app/services/notification_engine.py` - DecisionEngine, NotificationBuilder, TimingRules
**وظایف:**

**TimingRules:**
- `should_send_immediately()` - تعیین فوری بودن بر اساس priority
- `calculate_scheduled_time()` - محاسبه زمان ارسال
- `get_reminder_interval()` - فاصله یادآوری برای انواع مختلف

**NotificationBuilder:**
- `build()` - ساخت Notification object
- `create_and_save()` - ساخت و ذخیره در دیتابیس

**DecisionEngine:**
- `evaluate_health_data()` - ارزیابی داده سلامت و ایجاد notification
- `create_condition_reminder()` - ایجاد یادآوری برای بیماری
- `create_medication_reminder()` - ایجاد یادآوری دارو
- `create_insight_notification()` - ایجاد notification برای insights

**RAG-Ready:**
- TODO comments در تمام methods برای RAG integration
- آماده برای افزودن context از RAG

#### `app/services/rag.py` - RAGService
**وظایف:**
- Interface-only (هیچ external call وجود ندارد)
- Stub methods که None/empty برمی‌گردانند
- `is_enabled()`, `enable()`, `disable()` برای کنترل RAG
- Methods: `generate_embedding()`, `semantic_search()`, `retrieve_condition_context()`, `retrieve_medication_context()`

**RAG Integration Points:**
- TODO comments در همه methods
- آماده برای افزودن vector DB و embedding model

---

### 4. Routers

#### `app/routers/conditions.py` (جدید)
**Endpoints:**
- `GET /conditions` - دریافت لیست تمام conditions
- `GET /conditions/user/{user_id}` - دریافت conditions کاربر
- `POST /conditions/assign` - اختصاص condition به کاربر
- `DELETE /conditions/user/{user_id}/condition/{condition_id}` - حذف condition از کاربر

**ثبت شده در:** `app/main.py` با prefix `/conditions`

---

## 🔄 تغییرات در Routers موجود

### Routers به‌روزرسانی شده:

1. **`app/routers/health.py`**
   - استفاده از `DecisionEngine.evaluate_health_data()`
   - Backward compatibility: اگر DecisionEngine notification ایجاد نکند، یک notification ساده ایجاد می‌شود

2. **`app/routers/data.py`**
   - `create_auto_notification()` از `DecisionEngine.create_insight_notification()` استفاده می‌کند

3. **`app/routers/medical.py`**
   - استفاده از `DecisionEngine.create_insight_notification()`

4. **`app/routers/device.py`**
   - استفاده از `DecisionEngine.create_insight_notification()`

5. **`app/routers/ai_core.py`**
   - استفاده از `DecisionEngine.create_insight_notification()`

6. **`app/core/scheduler.py`**
   - `save_notification()` از `DecisionEngine` استفاده می‌کند

---

## ✅ بررسی‌های انجام شده

### Static Checks:
- ✅ هیچ خطای linting وجود ندارد
- ✅ همه imports صحیح هستند
- ✅ هیچ استفاده مستقیم از `Notification()` در routers وجود ندارد
- ✅ هیچ استفاده از فیلدهای قدیمی (`message`, `priority` int, `sound_id`) در Notification model وجود ندارد

### Backward Compatibility:
- ✅ API contracts تغییر نکرده‌اند
- ✅ Response structures یکسان هستند
- ✅ Existing notification flow همچنان کار می‌کند
- ✅ Routers موجود با DecisionEngine سازگار شده‌اند

---

## 🔮 آماده‌سازی برای RAG

### Embedding Fields:
- ✅ `MedicalCondition.embedding_id` (nullable)
- ✅ `Medication.embedding_id` (nullable)
- ✅ `UserCondition.embedding_id` (nullable)

### RAG Integration Points:
1. **MedicalService:**
   - `detect_conditions_from_health_data()` - TODO برای semantic search
   - `search_medications()` - TODO برای semantic search

2. **DecisionEngine:**
   - `evaluate_health_data()` - TODO برای condition-specific care guidelines
   - `create_condition_reminder()` - TODO برای condition-specific care guidelines
   - `create_medication_reminder()` - TODO برای medication-specific information

3. **RAGService:**
   - همه methods آماده برای implementation

---

## 📊 خلاصه فایل‌ها

### فایل‌های ایجاد شده:
1. `app/models.py` - مدل‌های جدید اضافه شد
2. `app/schemas/medical.py` - **جدید**
3. `app/services/__init__.py` - **جدید**
4. `app/services/medical.py` - **جدید**
5. `app/services/notification_engine.py` - **جدید**
6. `app/services/rag.py` - **جدید**
7. `app/routers/conditions.py` - **جدید**

### فایل‌های به‌روزرسانی شده:
1. `app/schemas/__init__.py` - export medical schemas
2. `app/routers/health.py` - استفاده از DecisionEngine
3. `app/routers/data.py` - استفاده از DecisionEngine
4. `app/routers/medical.py` - استفاده از DecisionEngine
5. `app/routers/device.py` - استفاده از DecisionEngine
6. `app/routers/ai_core.py` - استفاده از DecisionEngine
7. `app/core/scheduler.py` - استفاده از DecisionEngine
8. `app/main.py` - ثبت conditions router

---

## 🎯 ویژگی‌های کلیدی

### 1. Separation of Concerns
- Routers فقط API handling
- Business logic در services
- Decision making در DecisionEngine

### 2. RAG-Ready Architecture
- Embedding fields در همه مدل‌ها
- RAGService interface-only
- TODO comments برای integration points

### 3. Backward Compatibility
- API contracts تغییر نکرده
- Existing flows کار می‌کنند
- Response structures یکسان

### 4. No Heavy Dependencies
- هیچ vector DB dependency
- هیچ LLM call اضافی
- RAG optional و non-blocking

---

## 📝 TODO برای RAG Integration (آینده)

### در `MedicalService`:
- [ ] Semantic search در `detect_conditions_from_health_data()`
- [ ] Semantic search در `search_medications()`

### در `DecisionEngine`:
- [ ] افزودن condition-specific care guidelines از RAG
- [ ] افزودن medication-specific information از RAG

### در `RAGService`:
- [ ] Initialize vector database connection
- [ ] Load embedding model
- [ ] Implement `generate_embedding()`
- [ ] Implement `semantic_search()`
- [ ] Implement `retrieve_condition_context()`
- [ ] Implement `retrieve_medication_context()`

---

## ✅ نتیجه

**وضعیت:** ✅ **پیاده‌سازی کامل و آماده استفاده**

- ✅ همه مدل‌ها ایجاد شدند
- ✅ همه schemas ایجاد شدند
- ✅ همه service layers ایجاد شدند
- ✅ همه routers به‌روزرسانی شدند
- ✅ Conditions router ایجاد شد
- ✅ Backward compatibility حفظ شد
- ✅ RAG-ready architecture پیاده‌سازی شد
- ✅ هیچ خطای linting وجود ندارد

**سیستم آماده برای استفاده و آماده برای RAG integration در آینده است.**

---

**پایان گزارش**
