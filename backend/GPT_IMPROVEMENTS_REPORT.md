# گزارش بهبود آموزش GPT و جلوگیری از سوالات تکراری

**تاریخ:** 2024-12-30  
**وضعیت:** ✅ **تغییرات اعمال شد**

---

## مشکلات شناسایی شده

1. **تشخیص نام یا سوال:** سیستم نمی‌توانست به درستی تشخیص دهد که کاربر نام داده یا سوال پرسیده
2. **سوالات تکراری:** بعد از باز و بستن برنامه، GPT سوالات تکراری می‌پرسید
3. **آموزش ناکافی GPT:** GPT نیاز به آموزش بهتر برای عملکرد عالی داشت

---

## تغییرات اعمال شده

### 1. بهبود تشخیص نام یا سوال

**فایل:** `backend/app/core/conversation/prompts.py`

**تغییرات:**
- ✅ بهبود منطق `_get_onboarding_state` برای تشخیص بهتر نام
- ✅ اضافه کردن چک‌های بیشتر: طول، اعداد، علامت سوال
- ✅ بهبود keywords برای تشخیص سوالات (انگلیسی، فارسی، عربی)
- ✅ اضافه کردن keywords بیشتر مثل "what are", "what do", "what can"
- ✅ چک کردن همزمان name database و pattern matching

**کد جدید:**
```python
# Enhanced name detection
looks_like_name = (
    is_name or (
        2 <= len(user_message_clean) <= 30 and 
        not any(char.isdigit() for char in user_message_clean) and
        "?" not in user_message_clean and
        "؟" not in user_message_clean
    )
)

# Better question detection
question_indicators = {
    "en": ["what", "who", "where", "when", "why", "how", "can you", "do you", "are you", "is it", "tell me", "explain", "what are", "what do", "what can"],
    "fa": ["چی", "کی", "کجا", "چرا", "چطور", "می‌تونی", "می‌شه", "هست", "بگو", "توضیح", "چی هستی", "چی می‌کنی", "چی می‌تونی", "؟"],
    "ar": ["ماذا", "من", "أين", "متى", "لماذا", "كيف", "هل يمكنك", "هل أنت", "أخبرني", "اشرح", "ما أنت", "ماذا تفعل", "ماذا يمكنك", "؟"]
}
```

---

### 2. جلوگیری از سوالات تکراری

**تغییرات:**

#### A. بهبود System Prompt

**اضافه شده:**
- ✅ دستورات واضح برای جلوگیری از تکرار
- ✅ چک کردن تاریخچه گفتگو قبل از پرسیدن سوال
- ✅ دستور برای پرسیدن سوالات متفاوت

**مثال (انگلیسی):**
```
CRITICAL - AVOID REPETITION:
* Before asking ANY question, check conversation history to see if you've asked it before.
* If you asked a similar question in the last 5 messages, DO NOT ask it again.
* If user already answered a question, DO NOT ask it again - reference their answer instead.
* If you're about to ask "How are you?" and you asked it recently, ask something DIFFERENT.
* Vary your questions - don't ask the same type of question repeatedly.
```

**مثال (فارسی):**
```
مهم - جلوگیری از تکرار:
* قبل از پرسیدن هر سوالی، تاریخچه گفتگو را چک کن تا ببینی قبلاً پرسیده‌ای یا نه.
* اگر سوال مشابهی در 5 پیام اخیر پرسیدی، دوباره نپرس.
* اگر کاربر قبلاً به سوالی پاسخ داد، دوباره نپرس - به جوابشان اشاره کن.
* اگر می‌خواهی بپرسی "چطوری؟" و اخیراً پرسیدی، سوال متفاوتی بپرس.
* سوالاتت را متنوع کن - یک نوع سوال را مکرر نپرس.
```

#### B. بهبود User Prompt

**اضافه شده:**
- ✅ Context-aware hints برای جلوگیری از تکرار
- ✅ چک کردن سوالات اخیر در conversation history
- ✅ اضافه کردن hint به GPT برای پرسیدن سوالات متفاوت

**کد جدید:**
```python
def _build_user_prompt(
    self,
    user_message: str,
    stage: ConversationStage,
    context: Dict[str, any],
    conversation_history: list = None  # NEW: Added conversation history
) -> str:
    # ... existing code ...
    
    # Add context-aware hints to prevent repetitive questions
    if conversation_history:
        # Check if we've asked similar questions recently
        recent_questions = []
        for msg in conversation_history[-3:]:  # Last 3 exchanges
            sedi_msg = msg.get("sedi", "")
            if "?" in sedi_msg or "؟" in sedi_msg:
                recent_questions.append(sedi_msg)
        
        # Add hint to avoid repetition
        if recent_questions:
            repetition_hint = {
                "en": "\n\n[IMPORTANT: Check conversation history above. You've asked questions recently. Make sure your response doesn't repeat the same questions. If you need to ask something, ask something DIFFERENT from what you asked before.]",
                "fa": "\n\n[مهم: تاریخچه گفتگو را چک کن. اخیراً سوالاتی پرسیده‌ای. مطمئن شو که پاسخ تو همان سوالات را تکرار نمی‌کند. اگر نیاز به پرسیدن چیزی داری، سوال متفاوتی از آنچه قبلاً پرسیدی بپرس.]",
                "ar": "\n\n[مهم: تحقق من تاريخ المحادثة أعلاه. لقد طرحت أسئلة مؤخراً. تأكد من أن ردك لا يكرر نفس الأسئلة. إذا كنت بحاجة إلى طرح شيء ما، اسأل شيئاً مختلفاً عما سألته من قبل.]"
            }
            return user_message + repetition_hint.get(self.language, repetition_hint["en"])
```

#### C. بهبود Memory Usage Instructions

**اضافه شده:**
- ✅ دستورات واضح برای استفاده از conversation history
- ✅ جلوگیری از پرسیدن سوالات مشابه در 3-5 پیام اخیر
- ✅ اشاره به پاسخ‌های قبلی کاربر به جای پرسیدن دوباره

---

### 3. بهبود آموزش GPT

**تغییرات:**

#### A. System Prompt قوی‌تر

- ✅ دستورات واضح‌تر برای پاسخ به سوالات کاربر
- ✅ دستورات واضح برای جلوگیری از تکرار
- ✅ دستورات برای استفاده بهتر از conversation history
- ✅ دستورات برای متنوع کردن سوالات

#### B. Context-Aware Hints

- ✅ اضافه کردن hints به user prompt بر اساس conversation history
- ✅ چک کردن سوالات اخیر قبل از پرسیدن سوال جدید
- ✅ راهنمایی GPT برای پرسیدن سوالات متفاوت

#### C. Better Memory Instructions

- ✅ دستورات واضح برای استفاده از SHORT-TERM, MEDIUM-TERM, LONG-TERM memory
- ✅ دستورات برای جلوگیری از تکرار سوالات
- ✅ دستورات برای اشاره به اطلاعات قبلی به جای پرسیدن دوباره

---

## فایل‌های تغییر یافته

1. ✅ `backend/app/core/conversation/prompts.py`
   - بهبود `_get_onboarding_state` برای تشخیص بهتر نام
   - بهبود `_build_user_prompt` برای استفاده از conversation history
   - بهبود system prompts با دستورات ضد تکرار
   - بهبود question detection keywords

---

## Commit

**Commit Hash:** (بعد از push)

**Message:**
```
feat: Improve GPT training and prevent repetitive questions

- Enhanced name vs question detection with better logic
- Added conversation history awareness to prevent repetitive questions
- Improved system prompts with explicit anti-repetition instructions
- Enhanced user prompt building with context-aware hints
- Better question detection keywords for all languages
- Added checks to avoid asking same questions in last 3-5 messages
- Improved memory usage instructions for GPT
```

**Status:** ✅ Push موفق

---

## نتیجه

✅ **بهبودهای اعمال شد**

**بهبودها:**
- ✅ تشخیص بهتر نام یا سوال
- ✅ جلوگیری از سوالات تکراری
- ✅ آموزش بهتر GPT با دستورات واضح‌تر
- ✅ استفاده بهتر از conversation history
- ✅ متنوع کردن سوالات

**وضعیت:** 
- تغییرات push شدند
- نیاز به restart backend service روی سرور
- بعد از restart، GPT باید بهتر عمل کند

---

## مراحل بعدی

1. ✅ **Restart Backend Service:**
   ```bash
   cd /var/www/sedi/backend
   git pull origin main
   systemctl restart sedi-backend
   ```

2. ✅ **تست:**
   - تست تشخیص نام
   - تست تشخیص سوال
   - تست جلوگیری از سوالات تکراری
   - تست عملکرد GPT بعد از باز و بستن برنامه

---

**وضعیت:** تغییرات اعمال شد و push شدند. نیاز به restart backend.

