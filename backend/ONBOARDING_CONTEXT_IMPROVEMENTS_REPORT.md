# گزارش بهبود Context های Onboarding - تشخیص زبان و راهنمایی کاربر

**تاریخ:** 2024-12-30  
**فایل:** `backend/app/core/conversation/prompts.py`

---

## خلاصه تغییرات

بهبود سیستم onboarding برای تشخیص خودکار زبان کاربر و راهنمایی بهتر کاربر در مراحل اولیه.

---

## تغییرات اعمال شده

### 1. اضافه شدن Prompt های جدید

#### 1.1 Prompt های فارسی (`fa`)

**`name_pending_polite`** (اولین درخواست مودبانه):
```
"سلام، من صدی هستم. خیلی خوشحالم از آشنایی با شما. لطفا قبل از شروع مکالمه ممنون میشوم اسم شما را بدانم؟"
```

**`name_pending_insistent`** (درخواست قوی‌تر):
```
"کاربر عزیز من قراره به عنوان دستیار مراقبت و سلامت شما همراهیتان کنم. ممنون میشوم قبل از شروع تعامل و گفتگو اطلاعات لازم، شامل نام و سپس تعیین رمز را در ادامه گفتگویمان برای من مشخص کنید تا من بتوانم شما را به عنوان یک کاربر با هویت مشخص ثبت نمایم. زیرا من قراره به عنوان دستیار شخصی شما فعالیت کنم و از حریم شخصی شما محافظت کنم. اسم شما چیه؟"
```

#### 1.2 Prompt های عربی (`ar`)

**`name_pending_polite`**:
```
"مرحباً، أنا صدي. سعيد جداً بلقائك. من فضلك قبل بدء المحادثة، أود أن أعرف اسمك؟"
```

**`name_pending_insistent`**:
```
"عزيزي المستخدم، أنا سأكون مساعدك للعناية بالصحة. من فضلك قبل بدء التفاعل والمحادثة، يرجى تحديد المعلومات اللازمة، بما في ذلك الاسم ثم تعيين كلمة المرور في محادثتنا القادمة، حتى أتمكن من تسجيلك كمستخدم بهوية محددة. لأنني سأعمل كمساعدك الشخصي وأحمي خصوصيتك. ما اسمك؟"
```

#### 1.3 Prompt های انگلیسی (`en`) - برای سازگاری

**`name_pending_polite`**:
```
"Hello, I'm Sedi. I'm really glad to meet you. Please, before we start our conversation, I would appreciate it if you could tell me your name?"
```

**`name_pending_insistent`**:
```
"Dear user, I'm going to be your health and care assistant. Please, before we start our interaction and conversation, I need you to provide the necessary information, including your name and then setting a password in our upcoming conversation, so I can register you as a user with a specific identity. Because I'm going to work as your personal assistant and protect your privacy. What's your name?"
```

---

### 2. بهبود منطق تشخیص زبان و نام

#### 2.1 تشخیص خودکار زبان

**قبل:**
- زبان فقط از تنظیمات اولیه استفاده می‌شد
- تغییر زبان فقط در صورت تشخیص انجام می‌شد

**بعد:**
- اگر کاربر به فارسی/عربی تایپ کرد و **اسمش را گفت**، زبان فوراً تغییر می‌کند
- اگر کاربر به فارسی/عربی متنی غیر از نام تایپ کرد، زبان تغییر می‌کند و prompt مناسب نمایش داده می‌شود

**کد:**
```python
# Detect user language from message
user_lang = detect_language(user_message)
# Update prompts language if user is using different language
# CRITICAL: If user types in Persian/Arabic and provides their name, switch language immediately
if user_lang != self.language and user_lang in ["en", "fa", "ar"]:
    self.language = user_lang
    print(f"[ONBOARDING DEBUG] Language switched to: {user_lang}")
```

#### 2.2 منطق انتخاب Prompt بر اساس تعداد تلاش

**قبل:**
- فقط `name_pending` استفاده می‌شد

**بعد:**
- **اولین تلاش** (`conversation_count == 1`): `name_pending_polite` (مودبانه)
- **تلاش‌های بعدی** (`conversation_count >= 2`): `name_pending_insistent` (قوی‌تر)
- **سوال درباره صدی**: استفاده از GPT برای پاسخ + راهنمایی

**کد:**
```python
if not password_requested:
    # Use polite prompt for first attempt (conversation_count == 1)
    if conversation_count == 1:
        return "name_pending_polite"
    # Use insistent prompt for subsequent attempts (conversation_count >= 2)
    elif conversation_count >= 2:
        return "name_pending_insistent"
    else:
        return "name_pending"
```

---

### 3. پاسخ هوشمند به سوالات کاربر درباره صدی

#### 3.1 متد جدید: `_answer_sedi_question_with_guidance`

این متد:
1. از GPT استفاده می‌کند تا به سوالات کاربر درباره صدی پاسخ دهد
2. سپس کاربر را راهنمایی می‌کند که نامش را بگوید

**ویژگی‌ها:**
- پاسخ به سوالات درباره: "تو چی هستی؟"، "چی می‌کنی؟"، "چطور کار می‌کنی؟"
- توضیح کامل هویت صدی
- راهنمایی خودکار برای دریافت نام
- پشتیبانی از سه زبان (en, fa, ar)

**مثال استفاده:**
```python
if onboarding_state == "non_name_question":
    # Use GPT to answer user's question about Sedi
    gpt_response = self._answer_sedi_question_with_guidance(user_message, context, stage)
    return gpt_response
```

#### 3.2 System Prompt برای پاسخ به سوالات

**انگلیسی:**
- توضیح کامل هویت صدی
- هدف و نحوه کار
- راهنمایی برای دریافت نام

**فارسی:**
- توضیح کامل به فارسی
- راهنمایی مودبانه

**عربی:**
- توضیح کامل به عربی
- راهنمایی مناسب

---

### 4. بهبود تشخیص سوالات درباره صدی

#### 4.1 کلمات کلیدی برای تشخیص

**انگلیسی:**
```python
["what are you", "who are you", "what do you", "what can you", 
 "tell me about", "explain", "what is", "how do you"]
```

**فارسی:**
```python
["چی هستی", "کی هستی", "چی می‌کنی", "چی می‌تونی", 
 "بگو درباره", "توضیح بده", "چیه", "چطور کار می‌کنی"]
```

**عربی:**
```python
["ما أنت", "من أنت", "ماذا تفعل", "ماذا يمكنك", 
 "أخبرني عن", "اشرح", "ما هو", "كيف تعمل"]
```

#### 4.2 منطق تشخیص

```python
# Check if question is about Sedi, the app, or what Sedi does
sedi_question_keywords = {...}
is_sedi_question = any(keyword in user_message_clean.lower() for keyword in sedi_keywords)

if is_sedi_question:
    # This will be handled by GPT in generate_response
    return "non_name_question"  # GPT will answer, then guide to name
```

---

## سناریوهای پشتیبانی شده

### سناریو 1: کاربر فارسی‌زبان - نام را می‌دهد

1. **شروع:** "Hello, I'm Sedi. I'm really glad to meet you. What's your name?" (انگلیسی)
2. **کاربر:** "محمد" (فارسی)
3. **سیستم:** زبان به فارسی تغییر می‌کند
4. **صدی:** "از این به بعد من به عنوان دستیار مراقبت و سلامت همراهت هستم..." (فارسی)

### سناریو 2: کاربر فارسی‌زبان - سوال می‌پرسد

1. **شروع:** "Hello, I'm Sedi. I'm really glad to meet you. What's your name?" (انگلیسی)
2. **کاربر:** "تو چی هستی؟" (فارسی)
3. **سیستم:** زبان به فارسی تغییر می‌کند
4. **GPT:** پاسخ به سوال + راهنمایی برای نام
5. **صدی:** "من صدی هستم، دستیار مراقبت سلامت... حالا دوست دارم اسمتون را بدونم. اسم شما چیه؟"

### سناریو 3: کاربر فارسی‌زبان - از نام بردن امتناع می‌کند

1. **شروع:** "Hello, I'm Sedi. I'm really glad to meet you. What's your name?" (انگلیسی)
2. **کاربر:** "سلام" (فارسی - بدون نام)
3. **سیستم:** زبان به فارسی تغییر می‌کند
4. **صدی:** "سلام، من صدی هستم. خیلی خوشحالم از آشنایی با شما. لطفا قبل از شروع مکالمه ممنون میشوم اسم شما را بدانم؟" (مودبانه)
5. **کاربر:** "خوبم" (باز هم بدون نام)
6. **صدی:** "کاربر عزیز من قراره به عنوان دستیار مراقبت و سلامت شما همراهیتان کنم..." (قوی‌تر)

### سناریو 4: کاربر عربی‌زبان

1. **شروع:** "Hello, I'm Sedi. I'm really glad to meet you. What's your name?" (انگلیسی)
2. **کاربر:** "أحمد" یا "ما أنت؟" (عربی)
3. **سیستم:** زبان به عربی تغییر می‌کند
4. **صدی:** پاسخ به زبان عربی

---

## فلوچارت منطق

```
شروع (conversation_count = 0)
  ↓
first_launch (انگلیسی)
  ↓
کاربر پاسخ می‌دهد
  ↓
تشخیص زبان کاربر
  ↓
آیا نام است؟
  ├─ بله → name_confirmed (به زبان کاربر)
  └─ خیر
      ↓
  آیا سوال درباره صدی است؟
      ├─ بله → non_name_question → GPT پاسخ می‌دهد + راهنمایی
      └─ خیر
          ↓
      conversation_count == 1?
          ├─ بله → name_pending_polite (مودبانه)
          └─ خیر → name_pending_insistent (قوی‌تر)
```

---

## تست و بررسی

### موارد تست شده:

1. ✅ تشخیص خودکار زبان فارسی
2. ✅ تشخیص خودکار زبان عربی
3. ✅ تغییر prompt بر اساس تعداد تلاش
4. ✅ پاسخ GPT به سوالات درباره صدی
5. ✅ راهنمایی خودکار برای دریافت نام

### موارد نیاز به تست:

- [ ] تست کامل با کاربر واقعی فارسی‌زبان
- [ ] تست کامل با کاربر واقعی عربی‌زبان
- [ ] تست سناریوهای مختلف امتناع از نام
- [ ] تست سوالات مختلف درباره صدی

---

## نکات مهم

1. **تشخیص زبان:** سیستم به صورت خودکار زبان کاربر را از اولین پیام تشخیص می‌دهد
2. **تدریجی بودن:** درخواست‌ها از مودبانه به قوی‌تر تغییر می‌کنند
3. **هوشمند بودن:** اگر کاربر سوالی درباره صدی بپرسد، GPT پاسخ می‌دهد و سپس راهنمایی می‌کند
4. **سازگاری:** همه prompt ها برای سه زبان (en, fa, ar) موجود هستند

---

## فایل‌های تغییر یافته

1. `backend/app/core/conversation/prompts.py`
   - اضافه شدن prompt های جدید
   - بهبود منطق `_get_onboarding_state`
   - اضافه شدن متد `_answer_sedi_question_with_guidance`
   - بهبود منطق `generate_response`

---

## نتیجه‌گیری

سیستم onboarding اکنون:
- ✅ به صورت خودکار زبان کاربر را تشخیص می‌دهد
- ✅ prompt های مناسب را بر اساس تعداد تلاش نمایش می‌دهد
- ✅ به سوالات کاربر درباره صدی پاسخ می‌دهد
- ✅ کاربر را به صورت هوشمند راهنمایی می‌کند

همه تغییرات با موفقیت اعمال شدند و آماده استفاده هستند.

