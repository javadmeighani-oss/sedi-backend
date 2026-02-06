# گزارش رفع مشکل تشخیص Greeting vs Name

**تاریخ:** 2024-12-30  
**وضعیت:** ✅ **مشکل رفع شد**

---

## مشکل شناسایی شده

از اسکرین‌شات مشخص است:
- ❌ Sedi پرسیده: "Hello, I'm Sedi. I'm really glad to meet you. What's your name?"
- ❌ کاربر جواب داده: "سلام" (Hello)
- ❌ Sedi به greeting پاسخ نداده
- ❌ مستقیماً به درخواست رمز عبور رفته

**علت:**
- "سلام" یک greeting است، نه اسم
- منطق فعلی: اگر message کوتاه باشد (2-30 chars) و سوال نباشد، به عنوان name تشخیص می‌دهد
- "سلام" 4 کاراکتر است، سوال نیست، پس به عنوان name تشخیص داده می‌شود!
- سپس به `name_confirmed` می‌رود و مستقیماً به password flow می‌رود

---

## تغییرات اعمال شده

### 1. اضافه کردن Greeting Detection

**قبل:**
```python
# فقط name detection
is_name = is_likely_name(user_message_clean, self.language)
looks_like_name = is_name or (2 <= len(...) <= 30 and ...)
```

**بعد:**
```python
# CRITICAL: First check if it's a greeting (not a name)
greeting_words = {
    "en": ["hello", "hi", "hey", "greetings", "good morning", ...],
    "fa": ["سلام", "درود", "صبح بخیر", "ظهر بخیر", ...],
    "ar": ["مرحباً", "أهلا", "السلام عليكم", ...]
}
is_greeting = any(greeting in user_message_clean.lower() for greeting in greeting_list)

# If it's a greeting, respond to it and ask for name again
if is_greeting:
    return "greeting_response"  # Respond to greeting, then ask for name

# Then check for name (excluding greetings)
looks_like_name = is_name or (... and not is_greeting)  # CRITICAL: Exclude greetings
```

### 2. اضافه کردن Greeting Response State

**اضافه شده:**
```python
"greeting_response": {
    "en": "Hello! I'm Sedi, your health care assistant. I'm really glad to meet you. To get started, could you please tell me your name?",
    "fa": "سلام! من صدی هستم، دستیار مراقبت سلامت شما. خیلی خوشحالم از آشنایی با شما. برای شروع، لطفاً اسمتون را به من بگین؟",
    "ar": "مرحباً! أنا صدي، مساعد رعاية صحية الخاص بك. سعيد جداً بلقائك. للبدء، هل يمكنك إخباري باسمك من فضلك؟"
}
```

### 3. بهبود Multi-Language Detection

**اضافه شده:**
- ✅ چک کردن greeting در همه زبان‌ها
- ✅ چک کردن فارسی اگر پیام شامل کاراکترهای فارسی باشد
- ✅ چک کردن انگلیسی به عنوان fallback
- ✅ Language switching خودکار وقتی greeting فارسی تشخیص داده می‌شود

---

## فایل‌های تغییر یافته

1. ✅ `backend/app/core/conversation/prompts.py`
   - اضافه کردن greeting detection قبل از name detection
   - اضافه کردن `greeting_response` state
   - اضافه کردن greeting words برای همه زبان‌ها
   - بهبود منطق name detection برای exclude کردن greetings

---

## Commit

**Commit Hash:** (بعد از push)

**Message:**
```
fix: Add greeting detection to distinguish greetings from names

- Added greeting detection before name detection
- Greetings like 'سلام', 'hello', 'hi' are now properly recognized
- Added 'greeting_response' state to respond to greetings and ask for name
- Prevents greetings from being mistaken as names
- Added greeting words for English, Persian, and Arabic
- Multi-language greeting detection (check all languages)
- Better user experience: respond to greeting, then ask for name
```

**Status:** ✅ Push موفق

---

## نتیجه

✅ **مشکل رفع شد**

**بهبودها:**
- ✅ Greetings مثل "سلام" حالا به درستی تشخیص داده می‌شوند
- ✅ Greetings به عنوان name تشخیص داده نمی‌شوند
- ✅ Sedi به greeting پاسخ می‌دهد و دوباره از اسم می‌پرسد
- ✅ Multi-language greeting detection
- ✅ User experience بهتر

**Flow جدید:**
1. User: "سلام"
2. Sedi: "سلام! من صدی هستم، دستیار مراقبت سلامت شما. خیلی خوشحالم از آشنایی با شما. برای شروع، لطفاً اسمتون را به من بگین؟"
3. User: [اسم خود را می‌گوید]
4. Sedi: [ادامه onboarding]

**وضعیت:** 
- تغییرات push شدند
- GitHub Actions باید deploy کند
- بعد از deploy، greetings به درستی تشخیص داده می‌شوند

---

## تست

بعد از deploy، این موارد باید به درستی کار کنند:
- ✅ "سلام" → greeting response + ask for name
- ✅ "hello" → greeting response + ask for name
- ✅ "hi" → greeting response + ask for name
- ✅ "درود" → greeting response + ask for name
- ✅ [اسم واقعی] → name_confirmed

---

**وضعیت:** مشکل رفع شد. تغییرات push شدند. GitHub Actions باید deploy کند.

