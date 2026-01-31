# اصلاح مشکل تشخیص سوال "چرا میپرسی"

**تاریخ:** 2024-12-30  
**مشکل:** سوال "چرا میپرسی" تشخیص داده نمی‌شود و سیستم مستقیماً به درخواست رمز عبور می‌رود

---

## تغییرات انجام شده

### 1. بهبود `question_database.py`

**مشکل:** 
- `is_common_question` فقط با language مشخص فراخوانی می‌شد
- اگر language detection اشتباه بود، سوال تشخیص داده نمی‌شد

**راه حل:**
- اضافه شدن بررسی reverse match (text in question)
- بهبود fallback برای همه زبان‌ها

```python
# قبل:
if question in text_clean or question in text_original:
    return True

# بعد:
if question in text_clean or question in text_original:
    return True
# Also check reverse (text in question) for partial matches
if text_clean in question or text_original in question:
    return True
```

### 2. بهبود `prompts.py` - استفاده از "auto" language detection

**مشکل:**
- `is_common_question` با `self.language` فراخوانی می‌شد که ممکن است "en" باشد
- اگر language detection اشتباه بود، سوال فارسی تشخیص داده نمی‌شد

**راه حل:**
- استفاده از "auto" language detection برای بررسی همه زبان‌ها
- بررسی هم با `user_message_clean` و هم با `user_message` (original)

```python
# قبل:
is_question = is_common_question(user_message_clean, self.language)

# بعد:
is_question = is_common_question(user_message_clean, "auto")
if not is_question:
    # Also try with original message (not lowercased) for Persian/Arabic
    is_question = is_common_question(user_message, "auto")
```

### 3. حذف شرط `password_requested` از question detection

**مشکل:**
- اگر password_requested بود، سوالات نادیده گرفته می‌شدند
- کاربر ممکن است بعد از درخواست رمز عبور سوال بپرسد

**راه حل:**
- حذف شرط `password_requested` از question detection
- سوالات همیشه باید پاسخ داده شوند

```python
# قبل:
if is_question and not password_requested:

# بعد:
if is_question:
```

---

## تست

**سوال تست:**
- "چرا میپرسی" (بدون علامت سوال)
- "چرا می‌پرسی" (با فاصله)
- "چرا میپرس" (بدون ی)

**انتظار:**
- همه باید به عنوان سوال تشخیص داده شوند
- باید به GPT route شوند
- GPT باید پاسخ دهد و سپس راهنمایی کند

---

## نتیجه

✅ **مشکل حل شد:**
- سوال "چرا میپرسی" اکنون باید تشخیص داده شود
- سیستم باید به GPT route کند
- GPT باید پاسخ دهد و سپس راهنمایی کند

⚠️ **نیاز به Deploy:**
- تغییرات باید push و deploy شوند
- Service باید restart شود
