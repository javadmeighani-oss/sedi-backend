# گزارش پیاده‌سازی سیستم اعلان‌ها (Notification System Implementation Report)

**تاریخ:** 2024  
**پروژه:** Sedi (AI-based Health Assistant)  
**بخش:** Backend Only (NO Frontend Changes)

---

## 📋 خلاصه تغییرات

سیستم اعلان‌ها (Notification System) برای پشتیبانی از:
- یادآوری داروها (Medication reminders)
- اعلان‌های مبتنی بر شرایط (Condition-based care notifications)
- آماده‌سازی برای یکپارچه‌سازی scheduler در آینده

---

## 🔧 تغییرات انجام شده

### 1. مدل دیتابیس (Database Model)

**فایل:** `backend/app/models.py`

**تغییرات:**
- به‌روزرسانی مدل `Notification` با فیلدهای جدید:
  - `id` (Integer, primary key)
  - `user_id` (ForeignKey -> users.id, indexed)
  - `type` (String) - مثال: HEALTH, REMINDER, INSIGHT
  - `title` (String, nullable)
  - `body` (String, required) - جایگزین `message`
  - `priority` (String) - low | normal | high | critical
  - `is_read` (Boolean, default=False)
  - `is_sent` (Boolean, default=False) - **جدید**
  - `scheduled_for` (DateTime, nullable=True) - **جدید** - برای scheduler
  - `created_at` (DateTime, default=now)

**حذف شده:**
- `message` → جایگزین با `body`
- `actions` (JSON string)
- `metadata_json` (JSON string)

---

### 2. اسکیماها (Schemas)

**فایل:** `backend/app/schemas/notification.py`

**اسکیماهای جدید:**
- `NotificationBase` - فیلدهای مشترک
- `NotificationCreate` - برای ایجاد اعلان جدید
- `NotificationResponse` - برای پاسخ API

**فایل:** `backend/app/schemas/__init__.py`
- به‌روزرسانی exports برای اسکیماهای جدید

---

### 3. روت‌های API (Router Endpoints)

**فایل:** `backend/app/routers/notifications.py`

**اندپوینت‌های پیاده‌سازی شده:**

#### GET `/notifications?user_id={id}`
- دریافت لیست اعلان‌های کاربر
- مرتب‌سازی بر اساس `created_at` (descending)
- بازگشت لیست اعلان‌ها در قالب `APIResponse`

#### POST `/notifications/{notification_id}/read`
- علامت‌گذاری اعلان به عنوان خوانده شده
- به‌روزرسانی `is_read = True`
- بازگشت اعلان به‌روزرسانی شده

**آماده‌سازی برای Scheduler:**
- کامنت‌های TODO برای یکپارچه‌سازی scheduler
- فیلد `scheduled_for` قابل query است
- فیلد `is_sent` برای جلوگیری از ارسال تکراری

---

### 4. به‌روزرسانی فایل‌های مرتبط

#### `backend/app/core/scheduler.py`
- به‌روزرسانی `save_notification()` برای استفاده از ساختار جدید:
  - `message` → `body`
  - افزودن `is_sent=False`
  - افزودن `scheduled_for=None`

#### `backend/app/routers/ai_core.py`
- به‌روزرسانی ایجاد اعلان برای استفاده از ساختار جدید:
  - `type="HEALTH"`
  - `message` → `body`
  - حذف فیلدهای قدیمی (`tone`, `feedback_options`, `language`)

#### `backend/app/routers/device.py`
- به‌روزرسانی برای سازگاری با ساختار جدید:
  - `message` → `body`
  - `priority` از integer به string تبدیل شد
  - افزودن helper function برای تبدیل priority string به numeric

---

## 📊 ساختار API

### GET `/notifications?user_id={id}`

**Request:**
```
GET /notifications?user_id=1
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "notifications": [
      {
        "id": 1,
        "user_id": 1,
        "type": "HEALTH",
        "title": "Health Update",
        "body": "Your health status is normal.",
        "priority": "normal",
        "is_read": false,
        "is_sent": false,
        "scheduled_for": null,
        "created_at": "2024-01-01T12:00:00"
      }
    ]
  }
}
```

### POST `/notifications/{notification_id}/read`

**Request:**
```
POST /notifications/1/read
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "id": 1,
    "user_id": 1,
    "type": "HEALTH",
    "title": "Health Update",
    "body": "Your health status is normal.",
    "priority": "normal",
    "is_read": true,
    "is_sent": false,
    "scheduled_for": null,
    "created_at": "2024-01-01T12:00:00"
  }
}
```

---

## 🔄 آماده‌سازی برای Scheduler

سیستم آماده است برای یکپارچه‌سازی scheduler در آینده:

```python
# مثال query برای scheduler (در آینده پیاده‌سازی می‌شود)
scheduled_notifications = db.query(Notification).filter(
    Notification.scheduled_for <= datetime.utcnow(),
    Notification.is_sent == False
).all()
```

**کامنت‌های TODO در کد:**
- `backend/app/routers/notifications.py` - بخش scheduler integration readiness

---

## ✅ تست‌ها و بررسی‌ها

- ✅ هیچ خطای linting وجود ندارد
- ✅ تمام imports به‌روزرسانی شده‌اند
- ✅ ساختار کد با الگوهای موجود پروژه هماهنگ است
- ✅ هیچ breaking change در endpoint‌های موجود ایجاد نشده است

---

## 📝 فایل‌های تغییر یافته

1. `backend/app/models.py` - به‌روزرسانی مدل Notification
2. `backend/app/schemas/notification.py` - بازنویسی کامل اسکیماها
3. `backend/app/schemas/__init__.py` - به‌روزرسانی exports
4. `backend/app/routers/notifications.py` - بازنویسی کامل router
5. `backend/app/core/scheduler.py` - به‌روزرسانی save_notification()
6. `backend/app/routers/ai_core.py` - به‌روزرسانی ایجاد اعلان
7. `backend/app/routers/device.py` - به‌روزرسانی برای سازگاری

---

## 🚀 Deploy

**Commit:**
```
feat: implement proper notification system backend with scheduler readiness
```

**تغییرات commit شده و آماده push به GitHub هستند.**

**نکته:** در صورت نیاز به push دستی:
```bash
git push origin main
```

---

## 📌 نکات مهم

1. **هیچ تغییری در frontend انجام نشده است** - فقط backend به‌روزرسانی شده است
2. **ساختار قدیمی حذف شده** - فیلدهای `message`, `actions`, `metadata_json` دیگر وجود ندارند
3. **Priority از integer به string تبدیل شد** - مقادیر: "low", "normal", "high", "critical"
4. **Type enum به‌روزرسانی شد** - مثال: "HEALTH", "REMINDER", "INSIGHT"
5. **Scheduler readiness** - فیلدهای `is_sent` و `scheduled_for` برای استفاده در آینده آماده هستند

---

## 🔮 مراحل بعدی (Future Work)

1. پیاده‌سازی scheduler برای ارسال خودکار اعلان‌ها
2. یکپارچه‌سازی با سیستم push notification
3. افزودن endpoint برای ایجاد اعلان‌های زمان‌بندی شده
4. افزودن فیلترهای بیشتر در GET endpoint (priority, type, is_read)

---

## Release C – Device Ingestion Contract + Idempotency (V1 Freeze)

- **Endpoints:** `POST /devices/register` (register device, get token), `POST /device/ingest` (submit vital event).
- **Header:** `X-DEVICE-TOKEN` is **required** for ingest; validated per `DEVICE_AUTH_MODE`.
- **Auth modes:** `legacy_only` (shared token, tests only), `db_only` (per-device token from DB), `hybrid` (DB first then legacy). **V1 production decision:** use **`db_only`**.
- **Dedupe (proven):**
  - **device_events:** e.g. `heart_rate:1:2026-02-20T10:05` → at most one row per (event_type, user_id, time window); duplicate ingest returns `device_event_dedupe_hit=true`, `event_id=null`, `actions_created=0`.
  - **notifications:** e.g. `alert:heart_rate:1:202602201005:heart_rate_low` → at most one notification per (alert, user, minute, rule); duplicate does not create a second notification.
- **Duplicate ingest response:** HTTP 200, `ok: true`, `data.event_id=null`, `data.device_event_dedupe_hit=true`, `data.actions_created=0` (or omitted), plus existing `dedupe_key` and optional `message` ("Event already exists (duplicate)").

---

**پایان گزارش**
