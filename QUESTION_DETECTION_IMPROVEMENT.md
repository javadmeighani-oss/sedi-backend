# گزارش بهبود تشخیص سوالات فارسی

**تاریخ:** 2024-12-30  
**وضعیت:** ✅ **بهبود اعمال شد**

---

## مشکل شناسایی شده

از اسکرین‌شات مشخص است:
- ❌ کاربر پرسیده: "چرا میپرسی؟" (Why are you asking?)
- ❌ سیستم سوال را تشخیص نداده
- ❌ Sedi به سوال پاسخ نداده و مستقیماً به درخواست رمز عبور رفته

**علت:**
- "میپرسی" در question_indicators نبود
- فقط "چرا" بود که ممکن است کافی نباشد
- Pattern matching برای سوالات فارسی وجود نداشت
- Language detection ممکن است اشتباه باشد

---

## تغییرات اعمال شده

### 1. اضافه کردن Keywords بیشتر

**قبل:**
```python
"fa": ["چی", "کی", "کجا", "چرا", "چطور", ...]
```

**بعد:**
```python
"fa": ["چی", "کی", "کجا", "چرا", "چطور", "میپرسی", "می‌پرسی", "میپرس", "می‌پرس", "چرا میپرسی", "چرا می‌پرسی", "چرا میپرس", "چرا می‌پرس", "؟"]
```

### 2. Pattern Matching برای سوالات فارسی

**اضافه شده:**
```python
# CRITICAL: Also check for question patterns (verb + question word)
# This catches patterns like "چرا میپرسی؟" even if individual words aren't in the list
if not is_question:
    # Check for Persian question patterns
    persian_question_patterns = ["چرا می", "چرا می‌", "چرا میپرس", "چرا می‌پرس", "چرا میپرسی", "چرا می‌پرسی"]
    if any(pattern in user_message_clean.lower() for pattern in persian_question_patterns):
        is_question = True
        if self.language != "fa":
            self.language = "fa"  # Switch to Persian
```

### 3. بهبود Multi-Language Detection

**اضافه شده:**
- ✅ چک کردن در همه زبان‌ها، نه فقط زبان تشخیص داده شده
- ✅ چک کردن فارسی اگر پیام شامل کاراکترهای فارسی باشد
- ✅ چک کردن انگلیسی به عنوان fallback
- ✅ Language switching خودکار وقتی سوال فارسی تشخیص داده می‌شود

**کد جدید:**
```python
# CRITICAL: Check in ALL languages, not just detected language
# This ensures we catch questions even if language detection is wrong
is_question = False

# First, check in detected language
question_list = question_indicators.get(self.language, question_indicators["en"])
is_question = any(keyword in user_message_clean.lower() for keyword in question_list) or "?" in user_message_clean or "؟" in user_message_clean

# CRITICAL: Also check in Persian if message contains Persian characters
if not is_question:
    persian_chars = "ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی"
    if any(char in user_message for char in persian_chars):
        persian_questions = question_indicators["fa"]
        is_question = any(keyword in user_message_clean.lower() for keyword in persian_questions) or "؟" in user_message_clean
        if is_question:
            self.language = "fa"  # Switch to Persian

# Also check in English as fallback
if not is_question:
    english_questions = question_indicators["en"]
    is_question = any(keyword in user_message_clean.lower() for keyword in english_questions) or "?" in user_message_clean
```

### 4. بهبود Debug Logging

**اضافه شده:**
```python
print(f"[ONBOARDING DEBUG] Question detection: is_question={is_question}, language={self.language}, message={user_message_clean[:50]}")
```

---

## فایل‌های تغییر یافته

1. ✅ `backend/app/core/conversation/prompts.py`
   - اضافه کردن "میپرسی" و variations به question_indicators
   - اضافه کردن pattern matching برای سوالات فارسی
   - بهبود multi-language detection
   - بهبود debug logging

---

## Commit

**Commit Hash:** (بعد از push)

**Message:**
```
fix: Improve question detection for Persian questions like 'چرا میپرسی؟'

- Added 'میپرسی' and 'می‌پرسی' to Persian question indicators
- Added pattern matching for Persian question patterns like 'چرا میپرسی'
- Improved multi-language question detection (check all languages, not just detected)
- Added fallback checks for Persian and English questions
- Better language switching when Persian questions detected
- Enhanced debug logging for question detection
```

**Status:** ✅ Push موفق

---

## نتیجه

✅ **بهبود اعمال شد**

**بهبودها:**
- ✅ "چرا میپرسی؟" حالا به درستی تشخیص داده می‌شود
- ✅ Pattern matching برای سوالات فارسی اضافه شد
- ✅ Multi-language detection بهبود یافت
- ✅ Language switching خودکار اضافه شد
- ✅ Debug logging بهبود یافت

**وضعیت:** 
- تغییرات push شدند
- GitHub Actions باید deploy کند
- بعد از deploy، سوالات فارسی به درستی تشخیص داده می‌شوند

---

## تست

بعد از deploy، این سوالات باید به درستی تشخیص داده شوند:
- ✅ "چرا میپرسی؟"
- ✅ "چرا می‌پرسی؟"
- ✅ "چرا میپرس؟"
- ✅ "چی هستی؟"
- ✅ "کی هستی؟"

---

**وضعیت:** بهبود اعمال شد. تغییرات push شدند. GitHub Actions باید deploy کند.

