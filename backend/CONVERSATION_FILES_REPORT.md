# گزارش کامل فایل‌های مرتبط با گفتگو و تعامل کاربر

## 📋 خلاصه
این گزارش فایل‌های کلیدی که مسئول گفتگو و تعامل با کاربر هستند را مشخص می‌کند. بر اساس اسکرین‌شات ارائه شده، Sedi پاسخ‌های تکراری می‌دهد که نشان‌دهنده نیاز به بازنویسی این فایل‌ها است.

---

## 🔴 BACKEND - فایل‌های اصلی گفتگو

### 1️⃣ `backend/app/routers/interact.py`
**نقش:** لایه API - نقطه ورود تمام درخواست‌های گفتگو

**مسئولیت‌ها:**
- دریافت درخواست‌های HTTP از frontend
- مدیریت `user_id` برای حفظ تداوم گفتگو
- ایجاد کاربر anonymous برای کاربران جدید
- فراخوانی `ConversationBrain` برای پردازش پیام
- بازگرداندن پاسخ به frontend

**توابع کلیدی:**
- `chat_with_sedi()`: پردازش پیام‌های کاربر
- `introduce_user()`: ثبت کاربر جدید
- `get_greeting()`: دریافت greeting اولیه

**مشکل احتمالی:**
- اگر `user_id` به درستی ارسال نشود، هر بار کاربر جدید ایجاد می‌شود
- این باعث می‌شود حافظه گفتگو از بین برود

---

### 2️⃣ `backend/app/core/conversation/brain.py`
**نقش:** موتور اصلی تصمیم‌گیری - COMMANDER

**مسئولیت‌ها:**
- هماهنگی تمام اجزای گفتگو
- تعیین stage فعلی گفتگو
- ساخت context برای GPT
- فراخوانی `ConversationPrompts` برای تولید پاسخ
- ذخیره گفتگو در memory
- بررسی transition بین stage‌ها

**توابع کلیدی:**
- `process_message()`: پردازش پیام کاربر و تولید پاسخ Sedi
- `get_greeting()`: تولید greeting اولیه
- `_determine_engagement_level()`: تعیین سطح تعامل کاربر

**جریان پردازش:**
```
1. دریافت user_id و user_message
2. تعیین stage فعلی (از stages.py)
3. ساخت context (از context.py)
4. تولید پاسخ (از prompts.py)
5. ذخیره در memory (از memory.py)
6. بررسی transition stage
7. بازگرداندن پاسخ + metadata
```

**مشکل احتمالی:**
- اگر ترتیب عملیات اشتباه باشد (مثلاً save بعد از transition)، stage اشتباه تشخیص داده می‌شود

---

### 3️⃣ `backend/app/core/conversation/prompts.py`
**نقش:** تولید کننده متن - صدای Sedi

**مسئولیت‌ها:**
- تولید تمام متن‌های Sedi (greeting، سوالات، پاسخ‌ها)
- ساخت system prompt برای GPT
- ساخت user prompt با context
- فراخوانی GPT API
- پردازش پاسخ GPT

**توابع کلیدی:**
- `generate_response()`: تولید پاسخ Sedi با استفاده از GPT
- `_build_system_prompt()`: ساخت system prompt بر اساس stage و engagement
- `_build_user_prompt()`: ساخت user prompt با context
- `_build_conversation_history()`: ساخت تاریخچه گفتگو برای GPT

**مشکل احتمالی:**
- اگر system prompt به درستی تنظیم نشود، GPT ممکن است:
  - سوالات کاربر را نادیده بگیرد
  - پاسخ‌های تکراری بدهد
  - context را درست درک نکند

**نکته مهم:**
این فایل **مهم‌ترین فایل** برای کیفیت گفتگو است. تمام متن‌های Sedi از اینجا تولید می‌شوند.

---

### 4️⃣ `backend/app/core/conversation/context.py`
**نقش:** سازنده Context - آماده‌سازی داده برای GPT

**مسئولیت‌ها:**
- ترکیب اطلاعات از memory
- ساخت context کامل برای GPT
- فراهم کردن اطلاعات stage، نام کاربر، تاریخچه گفتگو
- محاسبه conversation_count و time_since_last

**توابع کلیدی:**
- `build()`: ساخت context کامل

**خروجی:**
```python
{
    "user_id": int,
    "stage": str,
    "user_name": str,
    "memory_facts": dict,
    "recent_messages": list,
    "conversation_count": int,
    "time_since_last": str,
    "user_message": str
}
```

**مشکل احتمالی:**
- اگر context ناقص باشد، GPT نمی‌تواند پاسخ مناسب بدهد

---

### 5️⃣ `backend/app/core/conversation/memory.py`
**نقش:** مدیریت حافظه - خواندن/نوشتن در دیتابیس

**مسئولیت‌ها:**
- ذخیره گفتگو در دیتابیس
- خواندن تاریخچه گفتگو
- استخراج facts از memory
- محاسبه conversation_count
- محاسبه time_since_last

**توابع کلیدی:**
- `save_conversation()`: ذخیره یک exchange گفتگو
- `get_recent_messages()`: دریافت آخرین پیام‌ها
- `extract_memory_facts()`: استخراج facts از memory
- `get_conversation_count()`: شمارش تعداد exchanges

**مشکل احتمالی:**
- اگر `user_id` اشتباه باشد، memory درست ذخیره/خوانده نمی‌شود

---

### 6️⃣ `backend/app/core/conversation/stages.py`
**نقش:** مدیریت Stage - State Machine

**مسئولیت‌ها:**
- تعریف stage‌های گفتگو
- تعیین stage فعلی بر اساس memory_count
- مدیریت transition بین stage‌ها

**Stage‌ها:**
- `FIRST_CONTACT`: 0 memory
- `INTRODUCTION`: 1-3 memory
- `GETTING_TO_KNOW`: 4-10 memory
- `DAILY_RELATION`: 11-30 memory
- `STABLE_RELATION`: 30+ memory

**توابع کلیدی:**
- `get_stage()`: تعیین stage فعلی
- `transition_stage()`: بررسی و انجام transition

**مشکل احتمالی:**
- اگر memory_count اشتباه باشد، stage اشتباه تشخیص داده می‌شود

---

## 🟢 FRONTEND - فایل‌های اصلی گفتگو

### 1️⃣ `frontend/lib/features/chat/chat_service.dart`
**نقش:** سرویس ارتباط با Backend

**مسئولیت‌ها:**
- ارسال پیام به backend
- دریافت greeting از backend
- مدیریت user_id برای حفظ تداوم گفتگو
- پردازش پاسخ‌های backend
- مدیریت خطاها

**توابع کلیدی:**
- `sendMessage()`: ارسال پیام به `/interact/chat`
- `getGreeting()`: دریافت greeting از backend
- `registerUser()`: ثبت کاربر جدید

**مشکل احتمالی:**
- اگر `user_id` به درستی ارسال نشود، backend نمی‌تواند گفتگو را ادامه دهد

---

### 2️⃣ `frontend/lib/features/chat/state/chat_controller.dart`
**نقش:** کنترلر UI - مدیریت state و نمایش

**مسئولیت‌ها:**
- مدیریت state UI (messages، isThinking، ...)
- فراخوانی `ChatService` برای ارسال پیام
- نمایش پاسخ‌های backend
- مدیریت user profile
- تشخیص زبان

**توابع کلیدی:**
- `sendUserMessage()`: ارسال پیام کاربر و نمایش پاسخ
- `initialize()`: مقداردهی اولیه و دریافت greeting
- `_getGreetingFromBackend()`: دریافت greeting از backend

**مشکل احتمالی:**
- اگر `user_id` از backend دریافت شود اما ذخیره نشود، در درخواست بعدی ارسال نمی‌شود

---

### 3️⃣ `frontend/lib/features/chat/presentation/pages/chat_page.dart`
**نقش:** صفحه اصلی UI

**مسئولیت‌ها:**
- نمایش UI گفتگو
- اتصال UI به ChatController
- مدیریت ورودی کاربر

---

### 4️⃣ `frontend/lib/features/chat/presentation/widgets/message_bubble.dart`
**نقش:** ویجت نمایش پیام

**مسئولیت‌ها:**
- نمایش bubble پیام‌های کاربر و Sedi
- استایل‌دهی پیام‌ها

---

## 🔄 جریان کامل گفتگو

### 1. شروع گفتگو (Frontend)
```
ChatController.initialize()
  → ChatService.getGreeting()
    → POST /interact/chat?message=__GREETING__
      → Backend: interact.py
        → ConversationBrain.get_greeting()
          → ConversationPrompts.generate_response()
            → GPT API
              → Response به Frontend
                → ChatController نمایش greeting
```

### 2. ارسال پیام کاربر (Frontend → Backend)
```
User types message
  → ChatController.sendUserMessage()
    → ChatService.sendMessage(userMessage, userId)
      → POST /interact/chat?message=...&user_id=...
        → Backend: interact.py
          → ConversationBrain.process_message()
            → stages.py: get_stage()
            → context.py: build()
            → prompts.py: generate_response()
              → GPT API
            → memory.py: save_conversation()
            → stages.py: transition_stage()
              → Response به Frontend
                → ChatController نمایش پاسخ
```

---

## 🐛 مشکلات احتمالی بر اساس اسکرین‌شات

### مشکل 1: پاسخ‌های تکراری
**علت احتمالی:**
- GPT context را درست نمی‌خواند
- System prompt به درستی تنظیم نشده
- Conversation history به GPT ارسال نمی‌شود

**فایل‌های مرتبط:**
- `backend/app/core/conversation/prompts.py` (مهم‌ترین)
- `backend/app/core/conversation/context.py`
- `backend/app/core/conversation/memory.py`

### مشکل 2: عدم درک سوالات کاربر
**علت احتمالی:**
- System prompt دستورات واضح برای پاسخ به سوالات ندارد
- User prompt context کافی ندارد

**فایل‌های مرتبط:**
- `backend/app/core/conversation/prompts.py` (مهم‌ترین)

### مشکل 3: عدم پیشرفت در stage
**علت احتمالی:**
- `user_id` به درستی ارسال نمی‌شود
- Memory ذخیره نمی‌شود
- Stage transition درست کار نمی‌کند

**فایل‌های مرتبط:**
- `backend/app/routers/interact.py`
- `frontend/lib/features/chat/chat_service.dart`
- `frontend/lib/features/chat/state/chat_controller.dart`
- `backend/app/core/conversation/memory.py`
- `backend/app/core/conversation/stages.py`

---

## ✅ فایل‌های نیازمند بازنویسی (اولویت‌بندی شده)

### اولویت 1: فایل‌های حیاتی
1. **`backend/app/core/conversation/prompts.py`**
   - بهبود system prompt برای پاسخ به سوالات
   - بهبود user prompt برای درک بهتر context
   - بهبود conversation history برای جلوگیری از تکرار

2. **`backend/app/core/conversation/brain.py`**
   - بررسی ترتیب عملیات (save قبل از transition)
   - بهبود error handling

### اولویت 2: فایل‌های مهم
3. **`backend/app/core/conversation/context.py`**
   - بهبود ساخت context
   - افزودن اطلاعات بیشتر برای GPT

4. **`backend/app/core/conversation/memory.py`**
   - بهبود استخراج facts
   - بهبود خواندن recent messages

### اولویت 3: فایل‌های پشتیبانی
5. **`backend/app/routers/interact.py`**
   - بهبود مدیریت user_id
   - بهبود error handling

6. **`frontend/lib/features/chat/chat_service.dart`**
   - اطمینان از ارسال user_id
   - بهبود error handling

7. **`frontend/lib/features/chat/state/chat_controller.dart`**
   - اطمینان از ذخیره user_id
   - بهبود نمایش پاسخ‌ها

---

## 📝 نکات مهم برای بازنویسی

1. **GPT Context:**
   - اطمینان از ارسال conversation history به GPT
   - اطمینان از ارسال user_message به GPT
   - اطمینان از ارسال stage و context به GPT

2. **System Prompt:**
   - دستورات واضح برای پاسخ به سوالات
   - دستورات واضح برای عدم تکرار
   - دستورات واضح برای درک context

3. **User ID Lifecycle:**
   - اطمینان از ارسال user_id در هر درخواست
   - اطمینان از ذخیره user_id در frontend
   - اطمینان از استفاده صحیح user_id در backend

4. **Memory Management:**
   - اطمینان از ذخیره هر exchange
   - اطمینان از خواندن recent messages
   - اطمینان از محاسبه صحیح conversation_count

---

## 🎯 نتیجه‌گیری

بر اساس اسکرین‌شات و بررسی کد، مشکل اصلی در:
1. **`prompts.py`**: System prompt و user prompt نیاز به بهبود دارند
2. **`context.py`**: Context ممکن است ناقص باشد
3. **`memory.py`**: ممکن است recent messages به درستی خوانده نشوند

**اولویت بازنویسی:**
1. `backend/app/core/conversation/prompts.py` (فوری)
2. `backend/app/core/conversation/context.py`
3. `backend/app/core/conversation/memory.py`
4. `backend/app/core/conversation/brain.py` (بررسی ترتیب عملیات)

