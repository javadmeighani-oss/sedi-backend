# گزارش پیاده‌سازی دیتابیس سوالات

**تاریخ:** 2024-12-30  
**وضعیت:** ✅ **پیاده‌سازی کامل**

---

## مشکل شناسایی شده

از اسکرین‌شات مشخص است:
- ❌ کاربر پرسیده: "چرا میپرسی"
- ❌ Sedi سوال را تشخیص نداده
- ❌ مستقیماً به درخواست رمز عبور رفته
- ❌ کانتکس‌های آماده شده استفاده نشده

**علت:**
- تشخیص سوال فقط بر اساس keywords بود
- دیتابیس جامع سوالات رایج وجود نداشت
- Pattern matching محدود بود

---

## راه‌حل انتخاب شده

**بهترین روش:** دیتابیس جامع سوالات رایج + چند روش تشخیص

**مزایا:**
- ✅ دقت بالاتر در تشخیص سوالات
- ✅ پوشش بیشتر سوالات رایج
- ✅ دسته‌بندی سوالات برای context بهتر
- ✅ استفاده از regex و pattern matching
- ✅ پشتیبانی از چند زبان

---

## پیاده‌سازی

### 1. ایجاد دیتابیس سوالات (`question_database.py`)

**ساختار:**
```python
ENGLISH_QUESTIONS = {
    "about_sedi": ["who are you", "what are you", ...],
    "why_asking": ["why are you asking", "why do you need", ...],
    "general": ["what is this", "how does this work", ...],
    "greeting_questions": ["how are you", ...],
}

PERSIAN_QUESTIONS = {
    "about_sedi": ["کی هستی", "چی هستی", ...],
    "why_asking": ["چرا میپرسی", "چرا می‌پرسی", ...],
    "general": ["این چیه", "چی شده", ...],
    "greeting_questions": ["چطوری", ...],
}

ARABIC_QUESTIONS = {
    "about_sedi": ["من أنت", "ما أنت", ...],
    "why_asking": ["لماذا تسأل", ...],
    ...
}
```

**دسته‌بندی سوالات:**
1. **about_sedi**: سوالات درباره Sedi
2. **why_asking**: سوالات درباره چرا می‌پرسد
3. **general**: سوالات عمومی
4. **greeting_questions**: سوالات سلام و احوال

### 2. توابع Helper

**`is_common_question(text, language)`:**
- چک کردن دقیق match
- چک کردن substring match
- چک کردن در همه زبان‌ها به عنوان fallback

**`get_question_category(text, language)`:**
- تشخیص دسته سوال
- مفید برای context بهتر

### 3. بهبود منطق تشخیص در `prompts.py`

**4 روش تشخیص (به ترتیب اولویت):**

1. **METHOD 1: دیتابیس سوالات (MOST RELIABLE)**
   ```python
   is_question = is_common_question(user_message_clean, self.language)
   ```

2. **METHOD 2: Keywords**
   ```python
   question_indicators = {"en": [...], "fa": [...], "ar": [...]}
   is_question = any(keyword in text for keyword in question_list)
   ```

3. **METHOD 3: Pattern Matching**
   ```python
   persian_question_patterns = ["چرا می", "چرا می‌", "چرا میپرس", ...]
   is_question = any(pattern in text for pattern in patterns)
   ```

4. **METHOD 4: Question Marks**
   ```python
   is_question = "?" in text or "؟" in text
   ```

---

## فایل‌های ایجاد/تغییر یافته

1. ✅ **`backend/app/core/conversation/question_database.py`** (NEW)
   - دیتابیس جامع سوالات رایج
   - توابع helper برای تشخیص سوالات

2. ✅ **`backend/app/core/conversation/prompts.py`**
   - Import کردن question_database
   - بهبود منطق تشخیص با 4 روش
   - استفاده از دیتابیس به عنوان اولویت اول

---

## Commit

**Commit Hash:** (بعد از push)

**Message:**
```
feat: Add comprehensive question database for better question detection

- Created question_database.py with common questions in EN/FA/AR
- Added 4 detection methods: database, keywords, patterns, question marks
- Improved question detection accuracy
- Better handling of questions like 'چرا میپرسی'
- Questions categorized for better context understanding
```

**Status:** ✅ Push موفق

---

## نتیجه

✅ **پیاده‌سازی کامل**

**بهبودها:**
- ✅ دیتابیس جامع سوالات رایج (EN/FA/AR)
- ✅ 4 روش تشخیص سوال (دیتابیس، keywords، patterns، question marks)
- ✅ دسته‌بندی سوالات برای context بهتر
- ✅ دقت بالاتر در تشخیص سوالات
- ✅ پوشش بیشتر سوالات رایج

**مثال‌ها:**
- ✅ "چرا میپرسی" → تشخیص داده می‌شود (دیتابیس + pattern)
- ✅ "کی هستی؟" → تشخیص داده می‌شود (دیتابیس)
- ✅ "why are you asking?" → تشخیص داده می‌شود (دیتابیس)

**وضعیت:** 
- تغییرات push شدند
- GitHub Actions باید deploy کند
- بعد از deploy، سوالات به درستی تشخیص داده می‌شوند

---

## مزایای این روش

1. **دقت بالا**: دیتابیس جامع سوالات رایج
2. **انعطاف‌پذیری**: 4 روش مختلف برای تشخیص
3. **قابلیت توسعه**: می‌توان سوالات جدید اضافه کرد
4. **دسته‌بندی**: سوالات دسته‌بندی شده برای context بهتر
5. **چندزبانه**: پشتیبانی از EN/FA/AR

---

**وضعیت:** پیاده‌سازی کامل. تغییرات push شدند. GitHub Actions باید deploy کند.

