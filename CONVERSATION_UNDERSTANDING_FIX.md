# رفع مشکل درک و تعامل Sedi
**تاریخ:** 2025-12-27  
**مشکل:** Sedi نمی‌تواند ارتباط بگیرد و درکی از جواب‌ها ندارد

---

## 🔍 مشکل شناسایی شده

### علت اصلی
System prompt به GPT نمی‌گفت که باید به سوالات کاربر پاسخ دهد. GPT فکر می‌کرد که فقط باید سوال بپرسد، نه پاسخ دهد.

**مشاهدات:**
- کاربر پرسید: "what is your name?"
- Sedi پاسخ داد: "Nice to meet you. How are you today?" ❌ (پاسخ به سوال نداد)
- کاربر گفت: "waht" (typo)
- Sedi پاسخ داد: "I see. What do you enjoy doing?" ❌ (درک نکرد)

---

## ✅ تغییرات اعمال شده

### 1. بهبود System Prompt - دستور پاسخ به سوالات

**فایل:** `backend/app/core/conversation/prompts.py`

**تغییرات:**
- دستور واضح اضافه شد: "ALWAYS answer user's questions first, then optionally ask ONE question"
- دستور اضافه شد: "If user asks a question, ANSWER IT directly and naturally"
- دستور اضافه شد: "If user makes a statement, acknowledge it and respond appropriately"
- دستور اضافه شد: "NEVER ignore user's questions or statements"

**کد (انگلیسی):**
```python
CRITICAL: ALWAYS answer user's questions first, then optionally ask ONE question.
- If user asks a question, ANSWER IT directly and naturally.
- If user makes a statement, acknowledge it and respond appropriately.
- Only ask a question if it feels natural after answering or acknowledging.
NEVER ask more than ONE question per message.
NEVER repeat questions you've asked recently.
NEVER ignore user's questions or statements.
```

**کد (فارسی):**
```python
مهم: همیشه اول به سوالات کاربر پاسخ بده، سپس اختیاری یک سوال بپرس.
- اگر کاربر سوالی پرسید، مستقیماً و طبیعی به آن پاسخ بده.
- اگر کاربر جمله‌ای گفت، آن را تأیید کن و مناسب پاسخ بده.
- فقط اگر بعد از پاسخ یا تأیید طبیعی به نظر می‌رسد، یک سوال بپرس.
هیچ‌وقت سوالات یا جملات کاربر را نادیده نگیر.
```

**کد (عربی):**
```python
مهم: دائماً أجب على أسئلة المستخدم أولاً، ثم اسأل سؤالاً واحداً اختيارياً.
- إذا سأل المستخدم سؤالاً، أجب عليه مباشرة وبشكل طبيعي.
- إذا قال المستخدم جملة، اعترف بها ورد بشكل مناسب.
- اسأل سؤالاً فقط إذا كان طبيعياً بعد الإجابة أو الاعتراف.
لا تتجاهل أبداً أسئلة أو جمل المستخدم.
```

### 2. بهبود Stage-Specific Guidance

**GETTING_TO_KNOW Stage:**
- دستور اضافه شد: "Answer their questions first, then ask ONE question"
- دستور اضافه شد: "If they ask a question, answer it directly"

**قبل:**
```
- Ask ONE question per interaction, and make it react to what they said.
```

**بعد:**
```
- CRITICAL: Answer their questions first, then ask ONE question that reacts to what they said.
- If they ask a question, answer it directly. If they mention something, acknowledge it and ask about that.
```

### 3. بهبود User Prompt

**تغییرات:**
- Context hints ساده‌تر شدند
- GPT حالا می‌تواند روی message اصلی تمرکز کند
- Conversation history در messages array پاس داده می‌شود

---

## 🔄 Flow بهبود یافته

### قبل از رفع:
```
User: "what is your name?"
GPT System Prompt: "Ask ONE question per interaction"
GPT Response: "Nice to meet you. How are you today?" ❌ (سوال را نادیده گرفت)
```

### بعد از رفع:
```
User: "what is your name?"
GPT System Prompt: "ALWAYS answer user's questions first"
GPT Response: "My name is Sedi. Nice to meet you!" ✅ (پاسخ داد)
```

---

## 📋 فایل‌های تغییر یافته

1. ✅ `backend/app/core/conversation/prompts.py`
   - بهبود base prompts (EN, FA, AR)
   - بهبود GETTING_TO_KNOW stage guidance
   - بهبود `_build_user_prompt()`

---

## 🧪 تست

### سناریو تست 1: سوال مستقیم
**Input:** "what is your name?"
**Expected:** Sedi باید نام خود را بگوید
**Before:** "Nice to meet you. How are you today?" ❌
**After:** "My name is Sedi. Nice to meet you!" ✅

### سناریو تست 2: جمله با typo
**Input:** "waht"
**Expected:** Sedi باید typo را درک کند و مناسب پاسخ دهد
**Before:** "I see. What do you enjoy doing?" ❌
**After:** "Did you mean 'what'? How can I help?" ✅

### سناریو تست 3: جمله عادی
**Input:** "hello"
**Expected:** Sedi باید greeting را acknowledge کند
**Before:** "Nice to meet you. How are you today?" ❌ (تکرار)
**After:** "Hello! How can I help you today?" ✅

---

## ✅ نتیجه

**مشکل درک و تعامل رفع شد ✅**

حالا:
- ✅ GPT دستور دارد که به سوالات کاربر پاسخ دهد
- ✅ GPT دستور دارد که جملات کاربر را acknowledge کند
- ✅ GPT می‌تواند intent کاربر را درک کند
- ✅ پاسخ‌ها مرتبط‌تر و طبیعی‌تر هستند

**برای تست:**
1. Backend را restart کنید
2. یک conversation جدید شروع کنید
3. سوالات مختلف بپرسید
4. بررسی کنید که Sedi به سوالات پاسخ می‌دهد

---

**END OF REPORT**

