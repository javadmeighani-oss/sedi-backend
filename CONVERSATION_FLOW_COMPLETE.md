# مسیر کامل گفتگو - راهنمای فایل‌ها و جریان

## 📋 خلاصه

این سند مسیر کامل گفتگو را از Frontend تا Backend و بازگشت مشخص می‌کند و فایل‌های کلیدی را معرفی می‌کند.

---

## 🔄 مسیر کامل گفتگو (Step-by-Step)

### مرحله 1: شروع گفتگو (اولین بار)

```
Frontend: ChatController.initialize()
  ↓
ChatService.getGreeting()
  ↓
POST /interact/chat?message=__GREETING__&lang=fa
  ↓
Backend: interact.py → chat_with_sedi()
  ↓
ConversationBrain.get_greeting(user_id)
  ↓
prompts.py → _generate_greeting()
  ↓
GPT API → "سلام! من صدی هستم... میتونم اسمتون را بدونم؟"
  ↓
Frontend: نمایش greeting + ذخیره user_id
```

**فایل‌های استفاده شده:**
- `frontend/lib/features/chat/state/chat_controller.dart` (خط 63-138)
- `frontend/lib/features/chat/chat_service.dart` (خط 47-151)
- `backend/app/routers/interact.py` (خط 97-192)
- `backend/app/core/conversation/brain.py` (خط 133-227)
- `backend/app/core/conversation/prompts.py` (خط 169-227)

---

### مرحله 2: کاربر نامش را می‌گوید

```
User types: "جواد"
  ↓
ChatController.sendUserMessage("جواد")
  ↓
ChatService.sendMessage("جواد", userId=null, lang="fa")
  ↓
POST /interact/chat?message=جواد&lang=fa
  ↓
Backend: interact.py
  - user_id ندارد → ایجاد anonymous user (user_id=1)
  ↓
ConversationBrain.process_message(user_id=1, "جواد")
  ↓
stages.py → get_stage(user_id=1)
  - memory_count=0 → FIRST_CONTACT
  ↓
context.py → build()
  - recent_messages = [] (هیچ memory نیست)
  - memory_facts = {name: null}
  ↓
prompts.py → generate_response()
  - system_prompt: FIRST_CONTACT stage guidance
  - conversation_history = [] (خالی)
  - user_prompt = "جواد"
  - GPT API → "سلام جواد! خوشحالم که باهات آشنا شدم..."
  ↓
memory.py → save_conversation()
  - ذخیره: user_message="جواد", sedi_response="..."
  - memory_count = 1
  ↓
Response: {message: "...", user_id: 1}
  ↓
Frontend: ذخیره user_id=1 در _userProfile
```

**فایل‌های استفاده شده:**
- `frontend/lib/features/chat/state/chat_controller.dart` (خط 168-301)
- `frontend/lib/features/chat/chat_service.dart` (خط 217-395)
- `backend/app/routers/interact.py` (خط 97-192)
- `backend/app/core/conversation/brain.py` (خط 37-131)
- `backend/app/core/conversation/stages.py` (خط 27-58)
- `backend/app/core/conversation/context.py` (خط 39-150)
- `backend/app/core/conversation/prompts.py` (خط 36-122)
- `backend/app/core/conversation/memory.py` (خط 72-100)

---

### مرحله 3: کاربر می‌خواهد Sedi معرفی شود

```
User types: "معرفی کن خودتو"
  ↓
ChatController.sendUserMessage("معرفی کن خودتو")
  - _userProfile.userId = 1 ✅
  ↓
ChatService.sendMessage("معرفی کن خودتو", userId=1, lang="fa")
  ↓
POST /interact/chat?message=معرفی کن خودتو&user_id=1&lang=fa
  ↓
Backend: interact.py
  - user_id=1 دارد → پیدا کردن user ✅
  ↓
ConversationBrain.process_message(user_id=1, "معرفی کن خودتو")
  ↓
stages.py → get_stage(user_id=1)
  - memory_count=1 → INTRODUCTION
  ↓
context.py → build()
  - recent_messages = [Memory(user: "جواد", sedi: "...")]
  - memory_facts = {name: "جواد"}
  ↓
prompts.py → generate_response()
  - system_prompt: INTRODUCTION stage + introduction handling
  - conversation_history = [{user: "جواد", sedi: "..."}]
  - user_prompt = "معرفی کن خودتو" + intent hint
  - Intent detection: "معرفی کن" detected ✅
  - GPT API → باید معرفی کامل بدهد
  ↓
memory.py → save_conversation()
  - ذخیره: user_message="معرفی کن خودتو", sedi_response="..."
  - memory_count = 2
  ↓
Response: {message: "...", user_id: 1}
  ↓
Frontend: نمایش پاسخ
```

**فایل‌های استفاده شده:**
- همان فایل‌های مرحله 2
- **مهم:** `prompts.py` خط 575-602 (intent detection)

---

## 📁 فایل‌های کلیدی برای گفتگو

### Backend (6 فایل اصلی):

#### 1. `backend/app/routers/interact.py`
**مسئولیت:** Entry point - دریافت درخواست HTTP

**توابع کلیدی:**
- `chat_with_sedi()`: پردازش پیام کاربر
- `introduce_user()`: ثبت کاربر جدید
- `get_greeting()`: دریافت greeting

**جریان:**
```
HTTP Request
  → Resolve user (user_id → name+secret → new)
  → Call ConversationBrain
  → Return response
```

---

#### 2. `backend/app/core/conversation/brain.py`
**مسئولیت:** Central orchestrator - هماهنگی تمام اجزا

**توابع کلیدی:**
- `process_message()`: پردازش پیام و تولید پاسخ
- `get_greeting()`: تولید greeting اولیه

**جریان:**
```
process_message(user_id, user_message)
  → get_stage() (از stages.py)
  → build context (از context.py)
  → generate response (از prompts.py)
  → save conversation (از memory.py)
  → transition stage (از stages.py)
  → return response
```

---

#### 3. `backend/app/core/conversation/stages.py`
**مسئولیت:** Stage detection و transition

**توابع کلیدی:**
- `get_stage()`: تعیین stage فعلی بر اساس memory_count
- `transition_stage()`: بررسی transition

**Stage Logic:**
- FIRST_CONTACT: memory_count = 0
- INTRODUCTION: memory_count = 1-3
- GETTING_TO_KNOW: memory_count = 4-10
- DAILY_RELATION: memory_count = 11-30
- STABLE_RELATION: memory_count = 30+

---

#### 4. `backend/app/core/conversation/context.py`
**مسئولیت:** ساخت context برای GPT

**توابع کلیدی:**
- `build()`: ساخت context کامل

**Context شامل:**
- recent_messages (SHORT-TERM memory)
- memory_facts (MEDIUM-TERM patterns)
- health_data (از گجت‌ها)
- lifestyle_patterns

---

#### 5. `backend/app/core/conversation/memory.py`
**مسئولیت:** ذخیره و خواندن memory

**توابع کلیدی:**
- `save_conversation()`: ذخیره exchange
- `get_recent_messages()`: دریافت آخرین پیام‌ها
- `extract_memory_facts()`: استخراج facts

**Memory Types:**
- SHORT-TERM: last 10 exchanges
- MEDIUM-TERM: last 50 exchanges
- LONG-TERM: last 200 exchanges

---

#### 6. `backend/app/core/conversation/prompts.py` ⚠️ **مهم‌ترین**
**مسئولیت:** تولید تمام متن‌های Sedi

**توابع کلیدی:**
- `generate_response()`: تولید پاسخ با GPT
- `_build_system_prompt()`: ساخت system prompt
- `_build_user_prompt()`: ساخت user prompt با intent detection
- `_build_conversation_history()`: ساخت conversation history

**جریان:**
```
generate_response(context, user_message)
  → _build_system_prompt() (بر اساس stage)
  → _build_conversation_history() (از recent_messages)
  → _build_user_prompt() (با intent detection)
  → GPT API call
  → return response
```

---

### Frontend (2 فایل اصلی):

#### 1. `frontend/lib/features/chat/chat_service.dart`
**مسئولیت:** ارتباط با Backend

**توابع کلیدی:**
- `sendMessage()`: ارسال پیام به `/interact/chat`
- `getGreeting()`: دریافت greeting

**مهم:** باید `user_id` را ارسال کند!

---

#### 2. `frontend/lib/features/chat/state/chat_controller.dart`
**مسئولیت:** مدیریت UI state

**توابع کلیدی:**
- `sendUserMessage()`: ارسال پیام و نمایش پاسخ
- `initialize()`: مقداردهی اولیه

**مهم:** باید `user_id` را از response دریافت و ذخیره کند!

---

## 🔴 مشکلات شناسایی شده و راه‌حل‌ها

### مشکل 1: تکرار پیام در Frontend
**علت احتمالی:** Frontend پیام را چند بار اضافه می‌کند

**بررسی:**
- `chat_controller.dart` خط 182-188: پیام به UI اضافه می‌شود
- آیا `sendUserMessage()` چند بار فراخوانی می‌شود؟
- آیا response handler پیام را دوباره اضافه می‌کند؟

**راه‌حل:** بررسی frontend برای duplicate handling

---

### مشکل 2: GPT درک نمی‌کند که کاربر می‌خواهد Sedi معرفی شود
**علت:** Intent detection یا system prompt کافی نیست

**راه‌حل‌های اعمال شده:**
1. ✅ بهبود keywords: "معرفی کن خودتو", "معرفی کن خودت"
2. ✅ بهبود intent hints: دستورات واضح‌تر
3. ✅ بهبود system prompt: "DO NOT confuse introduce yourself with introduce the user"

---

### مشکل 3: Conversation History استفاده نمی‌شود
**علت احتمالی:** History به GPT ارسال نمی‌شود یا GPT آن را نادیده می‌گیرد

**راه‌حل‌های اعمال شده:**
1. ✅ Debug logging برای conversation history
2. ✅ تاکید در system prompt برای خواندن history
3. ✅ بررسی که history به GPT ارسال می‌شود

---

## ✅ تغییرات اعمال شده

### 1. بهبود Intent Detection
- افزودن keywords بیشتر: "معرفی کن خودتو", "معرفی کن خودت", "خودتو معرفی کن"
- بهبود pattern matching برای فارسی

### 2. بهبود Intent Hints
- دستورات واضح: "You must introduce yourself, NOT ask the user"
- جلوگیری از confusion

### 3. بهبود System Prompt
- دستورات واضح برای معرفی
- تاکید: "DO NOT confuse introduce yourself with introduce the user"

### 4. Debug Logging
- Log conversation history
- Log user prompt with intent hints
- Log messages array

---

## 🎯 مسیر گفتگو برای اولین تماس (بهبود یافته)

### مرحله 1: Greeting
```
Sedi: "سلام! من صدی هستم، دستیار مراقبت سلامت شما با هوش مصنوعی. 
من از طریق پیشنهادهای شخصی‌سازی شده سلامت، بهبود سبک زندگی 
و پایش پیوسته داده‌های سلامت روزمره‌تان از طریق گجت‌های هوشمند، 
به بهبود کیفیت زندگی‌تان کمک می‌کنم. میتونم اسمتون را بدونم؟"
```

### مرحله 2: User sends name
```
User: "جواد"
Sedi: "سلام جواد! خوشحالم که باهات آشنا شدم. چطور می‌تونم کمکت کنم؟"
```

### مرحله 3: User asks for introduction
```
User: "معرفی کن خودتو"
Sedi: "سلام جواد! من صدی هستم، دستیار مراقبت سلامت شما با هوش مصنوعی. 
من از طریق پیشنهادهای شخصی‌سازی شده سلامت، بهبود سبک زندگی 
و پایش پیوسته داده‌های سلامت روزمره‌تان از طریق گجت‌های هوشمند، 
به بهبود کیفیت زندگی‌تان کمک می‌کنم. از طریق گفتگوی طبیعی 
درباره سبک زندگی‌تان یاد می‌گیرم و از گجت‌های هوشمند برای ثبت 
علائم حیاتی استفاده می‌کنم."
```

---

## 📝 چک‌لیست برای گفتگوی موفق

### Backend:
- ✅ `user_id` به درستی resolve می‌شود
- ✅ Memory به درستی ذخیره می‌شود
- ✅ Stage به درستی تشخیص داده می‌شود
- ✅ Context به درستی ساخته می‌شود
- ✅ Conversation history به GPT ارسال می‌شود
- ✅ Intent detection کار می‌کند
- ✅ System prompt واضح است
- ✅ GPT پاسخ مناسب می‌دهد

### Frontend:
- ✅ `user_id` از response دریافت می‌شود
- ✅ `user_id` در درخواست بعدی ارسال می‌شود
- ✅ پیام‌ها duplicate نمی‌شوند
- ✅ Response به درستی نمایش داده می‌شود

---

## 🔍 Debug Checklist

اگر گفتگو کار نمی‌کند، بررسی کنید:

1. **Backend Logs:**
   - `[ROUTER DEBUG]` - user resolution
   - `[BRAIN DEBUG]` - message processing
   - `[STAGE DEBUG]` - stage detection
   - `[MEMORY DEBUG]` - memory save/load
   - `[PROMPTS DEBUG]` - GPT context and response

2. **Frontend Logs:**
   - `[ChatController]` - message sending
   - `[ChatService]` - API calls
   - `user_id` در request

3. **Database:**
   - آیا memory ذخیره می‌شود؟
   - آیا `user_id` یکسان است؟

---

## 🎯 نتیجه

**فایل‌های کلیدی برای گفتگو:**
1. `backend/app/core/conversation/prompts.py` - مهم‌ترین (تولید پاسخ)
2. `backend/app/core/conversation/brain.py` - هماهنگی
3. `backend/app/core/conversation/context.py` - ساخت context
4. `backend/app/core/conversation/memory.py` - ذخیره memory
5. `backend/app/core/conversation/stages.py` - stage detection
6. `backend/app/routers/interact.py` - entry point
7. `frontend/lib/features/chat/chat_service.dart` - ارتباط با backend
8. `frontend/lib/features/chat/state/chat_controller.dart` - UI state

**مسیر گفتگو:**
Frontend → Backend Router → Brain → Stages/Context/Memory → Prompts → GPT → Memory → Response → Frontend

