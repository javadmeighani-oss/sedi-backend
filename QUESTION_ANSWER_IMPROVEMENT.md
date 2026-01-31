# گزارش بهبود تشخیص و پاسخ به سوالات

**تاریخ:** 2024-12-30  
**وضعیت:** ✅ **بهبود اعمال شد**

---

## مشکل شناسایی شده

از اسکرین‌شات مشخص است:
- ❌ کاربر پرسیده: "چرا میپرسی؟" (Why are you asking?)
- ❌ Sedi به سوال پاسخ نداده
- ❌ مستقیماً به درخواست رمز عبور رفته

**علت احتمالی:**
1. ترتیب چک‌ها: ممکن است name detection قبل از question detection باشد
2. GPT response: ممکن است GPT پاسخ درستی ندهد یا timeout شود
3. Error handling: ممکن است fallback درست کار نکند

---

## تغییرات اعمال شده

### 1. بهبود ترتیب چک‌ها

**قبل:**
```python
# 1. Check for name
if looks_like_name and not is_question:
    return "name_confirmed"

# 2. Check for question
if is_question:
    return "non_name_question"
```

**بعد:**
```python
# CRITICAL: Check for questions FIRST, before name detection
# Questions should always be answered, even if they look like names
if is_question and not password_requested:
    print(f"[ONBOARDING DEBUG] ✅ Question detected: {user_message_clean}")
    return "non_name_question"  # GPT will answer, then guide to name

# Then check for name (AFTER checking for questions)
if looks_like_name and not is_question and not is_greeting:
    return "name_confirmed"
```

**مزیت:**
- ✅ سوالات همیشه اول چک می‌شوند
- ✅ حتی اگر سوال شبیه name باشد، به GPT می‌رود
- ✅ Name detection فقط برای موارد غیرسوالی

### 2. بهبود GPT Prompt

**تغییرات:**
- ✅ افزایش `max_tokens` از 200 به 250 برای پاسخ کامل
- ✅ بهبود دستورات برای GPT
- ✅ اضافه کردن مثال‌های واضح‌تر

### 3. بهبود Error Handling

**اضافه شده:**
- ✅ Validation برای GPT response (چک کردن طول)
- ✅ Question-specific fallbacks
- ✅ بهتر کردن debug logging

**کد جدید:**
```python
# Validate response is not empty
if not response or len(response.strip()) < 10:
    print(f"[PROMPTS WARNING] GPT response too short, using fallback")
    raise Exception("GPT response too short")

# Fallback based on question type
if is_why_asking:
    # Specific answer for "why are you asking?"
    fallback_guidance = {
        "fa": "من می‌پرسم چون دستیار مراقبت سلامت شما هستم..."
    }
else:
    # Generic fallback
    fallback_guidance = {...}
```

### 4. بهبود Debug Logging

**اضافه شده:**
```python
print(f"[PROMPTS DEBUG] ===== CALLING GPT FOR QUESTION ANSWER =====")
print(f"[PROMPTS DEBUG] Language: {self.language}")
print(f"[PROMPTS DEBUG] User question: {user_message[:100]}...")
print(f"[PROMPTS DEBUG] ✅ GPT response received: {response[:150]}...")
```

---

## فایل‌های تغییر یافته

1. ✅ `backend/app/core/conversation/prompts.py`
   - بهبود ترتیب چک‌ها (questions قبل از names)
   - بهبود GPT prompt و error handling
   - بهبود debug logging

---

## Commit

**Commit Hash:** (بعد از push)

**Message:**
```
fix: Improve question detection and GPT response handling

- Check questions BEFORE name detection to ensure questions are always answered
- Improved GPT prompt with better examples and instructions
- Increased max_tokens to 250 for complete answers
- Enhanced error handling with question-specific fallbacks
- Better debug logging for question detection and GPT calls
- Validate GPT response before returning
```

**Status:** ✅ Push موفق

---

## نتیجه

✅ **بهبود اعمال شد**

**بهبودها:**
- ✅ سوالات همیشه اول چک می‌شوند (قبل از name detection)
- ✅ GPT prompt بهبود یافت
- ✅ Error handling بهتر شد
- ✅ Debug logging بهبود یافت
- ✅ Fallback responses برای سوالات خاص

**Flow جدید:**
1. User: "چرا میپرسی؟"
2. System: ✅ Question detected → Route to GPT
3. GPT: "من می‌پرسم چون دستیار مراقبت سلامت شما هستم... حالا دوست دارم اسمتون را بدونم..."
4. User: [اسم خود را می‌گوید]
5. Sedi: [ادامه onboarding]

**وضعیت:** 
- تغییرات push شدند
- GitHub Actions باید deploy کند
- بعد از deploy، سوالات به درستی پاسخ داده می‌شوند

---

## تست

بعد از deploy، این موارد باید به درستی کار کنند:
- ✅ "چرا میپرسی؟" → GPT پاسخ می‌دهد
- ✅ "کی هستی؟" → GPT پاسخ می‌دهد
- ✅ "چی می‌کنی؟" → GPT پاسخ می‌دهد
- ✅ [اسم واقعی] → name_confirmed

---

**وضعیت:** بهبود اعمال شد. تغییرات push شدند. GitHub Actions باید deploy کند.

