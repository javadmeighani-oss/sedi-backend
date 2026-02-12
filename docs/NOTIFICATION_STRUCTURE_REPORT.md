# گزارش ساختار نوتیفیکیشن‌ها — Sedi

این سند دسته‌بندی نوتیف‌ها، کانال‌های پوش، و نقش هر نوع را در بک‌اند و فرانت خلاصه می‌کند.

---

## ۱. خلاصه: چند دسته نوتیف داریم؟

| سطح | تعداد | توضیح |
|-----|--------|--------|
| **نوع نوتیف (Type)** در قرارداد بک‌اند | **۴ نوع** | `morning_brief`, `connection_ping`, `health_alert`, `device_disconnected` |
| **کانال پوش (Channel)** برای ارسال FCM | **۳ کانال** | `morning`, `engagement`, `health_alert` |
| **نوع نمایش در فرانت (نمایش در Inbox)** | **۹ مقدار** | ۴ نوع قراردادی بالا + ۵ نوع کلی: `info`, `alert`, `reminder`, `checkIn`, `achievement` |

یعنی از نظر **منطق کسب‌وکار و ارسال پوش** چهار نوع نوتیف داریم که سه کانال پوش دارند؛ در **UI** فرانت برای سازگاری با قرارداد و نمایش قدیمی، چند نوع دیگر هم به عنوان برچسب نمایشی پشتیبانی می‌شوند.

---

## ۲. انواع نوتیف (Backend Contract — ۴ نوع)

همهٔ نوتیف‌های ایجادشده توسط موتور نوتیفیکیشن یکی از این چهار نوع را دارند. این‌ها در `NotificationPayload.type` و ستون `notifications.type` ذخیره می‌شوند.

| نوع (type) | کاربرد | اولویت معمول | ساعات آرام (quiet hours) |
|------------|--------|---------------|---------------------------|
| **morning_brief** | خلاصه صبح؛ یک بار در روز | کم | بله (کانال morning) |
| **connection_ping** | سلام و احوال‌پرسی؛ چک‌این ملایم | کم/عادی | بله (کانال engagement) |
| **health_alert** | هشدار سلامت، یادآور دارو/شرایط، مقدار غیرطبیعی | عادی/بالا | برای priority بالا نادیده گرفته می‌شود |
| **device_disconnected** | قطع اتصال دستگاه (دستگاه دیده نشده) | عادی | بله (در نقش engagement) |

- **dedupe_key** برای جلوگیری از ارسال تکراری به ازای هر نوع قالب مشخصی دارد (مثلاً `morning_brief:{user_id}:{date}` یا `health_alert:{user_id}:{alert_code}:{date}T{hour}`).

---

## ۳. کانال‌های پوش (۳ کانال)

کانال فقط برای **ارسال FCM** و قوانین **quiet hours / anti-spam** استفاده می‌شود. نگاشت نوع → کانال در بک‌اند:

| نوع نوتیف (type) | کانال پوش (channel) |
|-------------------|----------------------|
| morning_brief | **morning** |
| connection_ping | **engagement** |
| health_alert | **health_alert** |
| device_disconnected | *(بدون نگاشت — در کد `channel = None`؛ در لاگ از خود type استفاده می‌شود)* |

- **morning:** برای خلاصه صبح؛ تحت قوانین ساعات آرام.
- **engagement:** برای connection_ping و ناد (engagement nudge)؛ ساعات آرام + ضد اسپم (فاصله حداقلی بین ارسال‌ها).
- **health_alert:** برای هشدارهای سلامت؛ برای اولویت بالا می‌تواند در ساعات آرام هم ارسال شود.

اندپوینت ادمین **send_now** فقط این سه کانال را می‌پذیرد:  
`morning` \| `engagement` \| `health_alert`.

---

## ۴. اولویت (Priority)

در قرارداد و دیتابیس:

| مقدار | کاربرد |
|--------|--------|
| **low** | نوتیفهای ملایم (مثلاً بعضی engagement) |
| **normal** | پیش‌فرض |
| **high** | هشدارهای مهم‌تر؛ ممکن است در ساعات آرام هم ارسال شود |
| **critical** | بحرانی (در فرانت به صورت `urgent` نمایش داده می‌شود) |

ستون `notifications.priority` در دیتابیس همین مقادیر را ذخیره می‌کند.

---

## ۵. اکشن‌های فیدبک (Feedback Actions)

بعد از نمایش نوتیف، کاربر می‌تواند یکی از این اکشن‌ها را بفرستد (مثلاً از طریق دکمه‌های Like/Dislike یا باز کردن چت):

| اکشن | معنی |
|------|--------|
| **like** | مثبت |
| **dislike** | منفی |
| **open_chat** | باز کردن چت از نوتیف |
| **dismissed** | بستن/رد کردن |

این‌ها در `POST /notifications/{id}/feedback` با فیلد `action` ارسال می‌شوند و در تحلیل فیدبک (مثلاً positive/negative) استفاده می‌شوند.

---

## ۶. فرانت‌اند: انواع نمایش (Inbox و قرارداد)

در فرانت مدل `NotificationType` (مثلاً در `lib/data/models/notification.dart`) برای **نمایش در Inbox** و تطبیق با API این مقادیر را دارد:

| مقدار enum فرانت | رشتهٔ قرارداد (از بک‌اند) | توضیح |
|-------------------|----------------------------|--------|
| morningBrief | morning_brief | خلاصه صبح |
| connectionPing | connection_ping | سلام/چک‌این |
| healthAlert | health_alert | هشدار سلامت |
| deviceDisconnected | device_disconnected | قطع دستگاه |
| info | info | نوتیف عمومی (پیش‌فرض برای نوع نامشخص) |
| alert | alert | هشدار کلی |
| reminder | reminder | یادآور |
| checkIn | check_in | چک‌این (کلی) |
| achievement | achievement | دستاورد |

چهار نوع اول همان **۴ نوع قراردادی بک‌اند** هستند؛ بقیه برای سازگاری با پاسخ API و نمایش برچسب در UI نگه داشته شده‌اند. اگر بک‌اند `type` دیگری بفرستد، فرانت آن را به `info` نگاشت می‌کند.

**عنوان پیش‌فرض در UI** (وقتی `title` خالی است) در `notification_ui_mapping.dart` برای هر نوع تعریف شده است (مثلاً "Morning Brief", "Health Alert", "Device Disconnected").

---

## ۷. جریان کلی

1. **ایجاد:** موتور نوتیفیکیشن (مثلاً `notification_engine`) با یکی از متدهای `create_morning_brief`, `create_connection_ping`, `create_health_alert`, `create_device_disconnected` یا قوانین lifestyle/health/condition/medication نوتیف می‌سازد.
2. **نوع و کانال:** برای هر نوتیف `type` (یکی از ۴ نوع) و در صورت وجود نگاشت، `channel` (morning / engagement / health_alert) ست می‌شود.
3. **ارسال پوش:** سرویس تحویل با FCM به توکن‌های کاربر ارسال می‌کند؛ قوانین quiet hours و anti-spam بر اساس کانال اعمال می‌شوند.
4. **فرانت:** نوتیف در Inbox با همان `type` و در صورت نیاز با عنوان پیش‌فرض نمایش داده می‌شود؛ کاربر می‌تواند like/dislike/open_chat/dismissed بفرستد.

---

## ۸. جمع‌بندی عددی

| مورد | تعداد |
|------|--------|
| انواع نوتیف (قرارداد بک‌اند) | **۴** (morning_brief, connection_ping, health_alert, device_disconnected) |
| کانال‌های پوش | **۳** (morning, engagement, health_alert) |
| انواع نمایش در فرانت (enum) | **۹** (۴ قراردادی + ۵ کلی) |
| اولویت‌ها | **۴** (low, normal, high, critical/urgent) |
| اکشن‌های فیدبک | **۴** (like, dislike, open_chat, dismissed) |

اگر سؤال بعدی روی یک نوع خاص (مثلاً فقط health_alert یا فقط کانال engagement) باشد، می‌توان همان بخش را با جزئیات بیشتر (مثلاً قوانین ساعات آرام یا dedupe_key) باز کرد.
