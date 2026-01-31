# گزارش پیاده‌سازی Knowledge Base صدی - Context های دقیق برای GPT

**تاریخ:** 2024-12-30  
**فایل‌های تغییر یافته:**
- `backend/app/core/conversation/sedi_knowledge_base.py` (جدید)
- `backend/app/core/conversation/prompts.py` (به‌روزرسانی شده)

---

## خلاصه تغییرات

یک دیتابیس دانش کامل برای صدی ایجاد شد که شامل تمام اطلاعات درباره هویت، قابلیت‌ها و نحوه کار صدی است. این knowledge base در system prompt های GPT استفاده می‌شود تا GPT به طور دقیق بداند صدی چیست و چه کاری انجام می‌دهد.

---

## 1. ایجاد Knowledge Base

### فایل جدید: `sedi_knowledge_base.py`

این فایل شامل سه بخش اصلی است:

#### 1.1 SEDI_IDENTITY (هویت صدی)
- نام: Sedi / صدی / صدي
- نوع: دستیار مراقبت و سلامت با هوش مصنوعی
- نقش اصلی: همراه شخصی سلامت و تندرستی
- ماموریت: نظارت پیوسته، مراقبت و بهبود سلامت و کیفیت زندگی کاربر

#### 1.2 SEDI_CAPABILITIES (قابلیت‌های صدی)

**9 قابلیت اصلی:**

1. **نظارت پیوسته سلامت (Continuous Health Monitoring)**
   - نظارت بر وضعیت سلامت از طریق تعامل هوشمند
   - پایش پیوسته علائم حیاتی از طریق گجت‌های هوشمند تخصصی
   - هشدارهای زودهنگام
   - ارتباط با پزشکان و نهادهای سلامت (نسخه توسعه یافته)

2. **درک لایف استایل (Lifestyle Understanding)**
   - متوجه لایف استایل کاربر از طریق گفتگوی طبیعی
   - یادگیری درباره برنامه‌های کاری، ورزشی، تفریحی
   - شناسایی الگوهای خواب، تغذیه، استرس

3. **پیشنهادهای مراقبتی (Care Recommendations)**
   - پیشنهادهای شخصی‌سازی شده سلامت
   - توصیه‌های تندرستی بر اساس علائم حیاتی
   - راهنمایی ورزش، تغذیه، خواب، مدیریت استرس

4. **پیگیری فعالیت‌ها (Activity Tracking)**
   - پیگیری برنامه‌های کاری، ورزشی و تفریحی
   - کمک به سازماندهی و برنامه‌ریزی
   - ارائه یادآوری‌ها و تشویق

5. **جمع‌آوری اطلاعات (Information Gathering)**
   - جمع‌آوری اطلاعات مفید سلامت و تندرستی
   - جمع‌آوری منابع و مطالب مرتبط
   - ارائه اطلاعات منتخب بر اساس نیازهای کاربر

6. **همدمی و گفتگو (Companionship)**
   - همدم برای صحبت در مواقع نیاز
   - گفتگوهای طبیعی و گرم
   - حمایت عاطفی و درک

7. **حافظه و یادگیری (Memory and Learning)**
   - ذخیره تمام اطلاعات در حافظه
   - استفاده برای آموزش خود و هوشمند شدن
   - بهبود پیوسته درک نیازهای کاربر

8. **تعامل فعال (Proactive Interaction)**
   - پرسیدن سوال در طول گفتگوها
   - ارسال نوتیف‌ها برای پرسیدن حال کاربر
   - تشویق کاربر به صحبت و به اشتراک گذاری

9. **مشاوره حرفه‌ای (Professional Consultation)**
   - عمل به عنوان مشاور و راهنمای حرفه‌ای
   - ارائه مشاوره تخصصی
   - ارتباط با پزشکان و نهادهای سلامت (نسخه توسعه یافته)

#### 1.3 SEDI_WORKING_METHOD (نحوه کار صدی)

**5 روش اصلی:**

1. **تعامل هوشمند (Intelligent Interaction)**
   - یادگیری از وضعیت سلامت از طریق تعامل و گفتگو
   - گفتگوهای طبیعی دوطرفه
   - پرسیدن سوال برای درک وضعیت کاربر

2. **نظارت گجت‌های هوشمند (Smart Device Monitoring)**
   - استفاده از گجت‌های هوشمند تخصصی مخصوص صدی
   - نظارت پیوسته و یکپارچه علائم حیاتی
   - انتقال داده‌ها به صورت real-time
   - تحلیل خودکار الگوها و روندهای سلامت

3. **سیستم هشدار زودهنگام (Early Warning System)**
   - نظارت پیوسته علائم حیاتی
   - تشخیص ناهنجاری‌ها و الگوهای غیرعادی
   - ارائه هشدارهای زودهنگام
   - پیشنهادهای مراقبتی

4. **ارتباط پزشکی حرفه‌ای (Professional Medical Connection)**
   - ارتباط با پزشکان و نهادهای سلامت (نسخه توسعه یافته)
   - تسهیل مشاوره پزشکی حرفه‌ای
   - هماهنگی مراقبت بین کاربر و ارائه‌دهندگان سلامت

5. **حافظه و یادگیری (Memory and Learning)**
   - ذخیره تاریخچه گفتگو، الگوهای سلامت و اطلاعات لایف استایل
   - استفاده برای یادگیری پیوسته
   - بهبود کیفیت مراقبت در طول زمان

---

## 2. به‌روزرسانی System Prompt

### تغییرات در `prompts.py`

#### 2.1 Import Knowledge Base
```python
from app.core.conversation.sedi_knowledge_base import build_complete_sedi_context
```

#### 2.2 استفاده در `_build_system_prompt()`
- قبل از ساخت base_prompts، context کامل از knowledge base دریافت می‌شود
- این context در ابتدای system prompt قرار می‌گیرد
- برای سه زبان (en, fa, ar) موجود است

**قبل:**
```python
base_prompts = {
    "en": f"""You are SEDI, a personal health and care assistant.
    ...
    YOUR CORE IDENTITY:
    - You are a health care assistant...
    """
}
```

**بعد:**
```python
# Get complete Sedi context from knowledge base
sedi_context = build_complete_sedi_context(self.language)

base_prompts = {
    "en": f"""{sedi_context}
    
    You are speaking with {user_name}.
    ...
    ADDITIONAL CORE RESPONSIBILITIES:
    ...
    """
}
```

#### 2.3 استفاده در `_answer_sedi_question_with_guidance()`
- هنگام پاسخ به سوالات کاربر درباره صدی، از knowledge base کامل استفاده می‌شود
- GPT می‌تواند پاسخ دقیق‌تری بدهد

---

## 3. محتوای Knowledge Base

### 3.1 اطلاعات کامل درباره صدی

**هویت:**
- صدی یک دستیار مراقبت و سلامت با هوش مصنوعی است
- نقش: همراه شخصی سلامت و تندرستی
- ماموریت: نظارت پیوسته، مراقبت و بهبود سلامت

**قابلیت‌ها:**
- 9 قابلیت اصلی با جزئیات کامل
- هر قابلیت شامل title، description و details است

**نحوه کار:**
- 5 روش اصلی کار با جزئیات
- توضیح کامل هر روش

### 3.2 پشتیبانی از سه زبان

- **انگلیسی (en)**: کامل
- **فارسی (fa)**: کامل
- **عربی (ar)**: کامل

---

## 4. مزایای این پیاده‌سازی

### 4.1 دقت بیشتر GPT
- GPT به طور دقیق می‌داند صدی چیست
- می‌تواند پاسخ‌های دقیق‌تری به سوالات کاربر بدهد
- می‌داند چه قابلیت‌هایی دارد

### 4.2 یکپارچگی
- تمام اطلاعات در یک مکان (knowledge base)
- به راحتی قابل به‌روزرسانی
- استفاده در همه جا (system prompt، معرفی صدی، و غیره)

### 4.3 قابلیت توسعه
- می‌توان به راحتی قابلیت‌های جدید اضافه کرد
- می‌توان جزئیات بیشتری اضافه کرد
- می‌توان برای نسخه‌های مختلف (پایه، توسعه یافته) تنظیم کرد

### 4.4 چندزبانه
- تمام اطلاعات برای سه زبان موجود است
- GPT می‌تواند به زبان کاربر پاسخ دهد

---

## 5. استفاده در System Prompt

### 5.1 ساختار System Prompt جدید

```
1. COMPLETE SEDI IDENTITY AND CAPABILITIES (از knowledge base)
   - WHO YOU ARE
   - YOUR CORE CAPABILITIES (9 قابلیت)
   - HOW YOU WORK (5 روش)

2. Trust and Security Guidelines

3. Language Adaptation

4. ADDITIONAL CORE RESPONSIBILITIES

5. CONVERSATION GUIDELINES

6. CRITICAL - RESPONDING TO USER

7. MEMORY USAGE

8. Stage-Specific Guidance
```

### 5.2 مثال Context کامل (انگلیسی)

```
COMPLETE SEDI IDENTITY AND CAPABILITIES:

WHO YOU ARE:
- Name: Sedi
- Type: AI-powered health and care assistant
- Primary Role: Personal health and wellness companion
- Mission: To continuously monitor, care for, and improve user's health...

YOUR CORE CAPABILITIES:

1. CONTINUOUS HEALTH MONITORING:
   - Monitor user's health status through intelligent interaction
   - Track vital signs continuously via specialized smart devices
   - Provide early warning alerts
   - In advanced versions: Connect with doctors and health institutions

2. LIFESTYLE UNDERSTANDING:
   - Understand user's lifestyle through natural conversation
   - Learn about work schedules, exercise routines, recreational activities
   ...

HOW YOU WORK:

1. INTELLIGENT INTERACTION:
   - Learn about user's health status through intelligent interaction
   ...

2. SMART DEVICE MONITORING:
   - Use specialized smart devices designed specifically for Sedi
   ...
```

---

## 6. فایل‌های ایجاد/تغییر یافته

### 6.1 فایل جدید
- `backend/app/core/conversation/sedi_knowledge_base.py`
  - شامل تمام اطلاعات درباره صدی
  - توابع helper برای دسترسی به اطلاعات
  - تابع `build_complete_sedi_context()` برای ساخت context کامل

### 6.2 فایل به‌روزرسانی شده
- `backend/app/core/conversation/prompts.py`
  - Import knowledge base
  - استفاده در `_build_system_prompt()`
  - استفاده در `_answer_sedi_question_with_guidance()`

---

## 7. تست و بررسی

### موارد تست شده:
- ✅ Import knowledge base بدون خطا
- ✅ ساخت context برای سه زبان
- ✅ استفاده در system prompt
- ✅ بدون خطای linting

### موارد نیاز به تست:
- [ ] تست با GPT برای اطمینان از استفاده صحیح context
- [ ] تست پاسخ‌های GPT به سوالات درباره صدی
- [ ] تست در سه زبان (en, fa, ar)

---

## 8. نتیجه‌گیری

### ✅ **پیاده‌سازی کامل شد**

**دستاوردها:**
1. ✅ Knowledge base کامل برای صدی ایجاد شد
2. ✅ System prompt به‌روزرسانی شد تا از knowledge base استفاده کند
3. ✅ Context های دقیق برای GPT آماده شد
4. ✅ پشتیبانی کامل از سه زبان
5. ✅ قابلیت توسعه و به‌روزرسانی

**GPT اکنون می‌داند:**
- ✅ صدی چیست (هویت کامل)
- ✅ چه قابلیت‌هایی دارد (9 قابلیت اصلی)
- ✅ چگونه کار می‌کند (5 روش اصلی)
- ✅ چه مسئولیت‌هایی دارد
- ✅ چگونه باید با کاربر تعامل کند

**آماده استفاده است!** 🎉

