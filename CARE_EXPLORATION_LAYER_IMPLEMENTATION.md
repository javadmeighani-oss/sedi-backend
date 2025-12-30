# Care Exploration Layer Implementation - Summary

## Overview

The Care Exploration Layer has been implemented in `app/core/conversation/prompts.py`. This layer provides soft guidance when the user doesn't choose a clear direction after the first real interaction, helping them start their health journey in a calm, structured, and caring manner.

---

## Implementation Details

### 1. Prompts Added

**Location:** `_init_onboarding_prompts()` method

**Three new prompt states:**

1. **user_delegates** - When user delegates control to Sedi
2. **unrelated_question** - When user asks unrelated or general questions
3. **early_medical_question** - When user asks medical question early (without context)

All prompts are available in three languages (EN/FA/AR).

---

### 2. Stage Mapping

**Trigger Conditions:**
- First Real Interaction or Unclear Response has been shown
- Conversation count: 5-10 (after first interaction)
- Stage: `INTRODUCTION` transitioning to `GETTING_TO_KNOW`

**Mapping:**
- **user_delegates** → When user explicitly delegates ("you decide", "you start")
- **unrelated_question** → When user asks non-health-related questions
- **early_medical_question** → When user asks medical question early (count 5-8, before context)

**Note:** No new stages were added. The prompts work within existing `INTRODUCTION` and `GETTING_TO_KNOW` stages.

---

### 3. Detection Logic

**Location:** `_get_onboarding_state()` method

**Detection Flow:**

#### Care Exploration Phase Detection:
```
Conditions:
- name_learned = true
- conversation_count >= 5 and <= 10
- password_requested = false
- Last Sedi message was first_real_interaction OR unclear_response
```

#### User Delegates:
```
Keywords by Language:
EN: "you decide", "you start", "you choose", "whatever you think", "up to you"
FA: "تو تصمیم بگیر", "تو شروع کن", "تو انتخاب کن", "هر چی فکر می‌کنی"
AR: "أنت تقرر", "أنت تبدأ", "أنت تختار", "مهما تعتقد"
```

#### Unrelated Question:
```
Conditions:
- Is a question (contains question words or ?)
- NOT health-related (no health keywords)
- Length > 5 characters
```

#### Early Medical Question:
```
Conditions:
- Contains medical keywords
- conversation_count <= 8 (early, before context established)
- After first interaction shown
```

---

## Prompt Content

### User Delegates Control

**English:**
```
That's completely fine.
I'll start gently.

I'm here to help you stay aware of your health,
understand your current condition,
and support you in taking better care of yourself.

To begin,
how would you describe your health today?
Would you say it feels good, normal, or a bit challenging?
```

**Persian:**
```
کاملاً مشکلی نیست،
من خیلی آروم شروع می‌کنم.

من اینجا هستم تا مراقب وضعیت سلامتت باشم،
کمک کنم از شرایط بدنت آگاه باشی
و راحت‌تر از خودت مراقبت کنی.

برای شروع،
امروز وضعیت سلامتت رو چطور توصیف می‌کنی؟
خوبه، معمولیه، یا کمی سخت؟
```

**Arabic:**
```
لا مشكلة في ذلك أبداً،
سأبدأ بهدوء.

أنا هنا لمتابعة وضعك الصحي،
ومساعدتك على أن تكون على دراية بحالتك
وتعتني بصحتك بشكل أفضل.

للبداية،
كيف تصف حالتك الصحية اليوم؟
هل هي جيدة، طبيعية، أم متعبة قليلاً؟
```

### Unrelated Question

**English:**
```
That's a good question.

My role is to support your health and well-being,
help you stay informed about your condition,
and assist you in taking better care of yourself.

If you're comfortable,
we can start with something simple about your health today.
```

**Persian:**
```
سؤال خوبیه.

نقش من اینه که مراقب وضعیت سلامتت باشم،
کمک کنم از شرایطت آگاه‌تر باشی
و راحت‌تر از خودت مراقبت کنی.

اگه موافقی،
می‌تونیم از یک موضوع ساده درباره سلامت امروزت شروع کنیم.
```

**Arabic:**
```
سؤال جيد.

دوري هو متابعة حالتك الصحية،
ومساعدتك على فهم وضعك بشكل أفضل
والاعتناء بصحتك بطريقة واعية.

إذا أحببت،
يمكننا أن نبدأ بسؤال بسيط عن صحتك اليوم.
```

### Early Medical Question

**English:**
```
I can help you understand health topics
and support you in monitoring your condition,
but medical diagnosis or treatment decisions
should always be made with a qualified doctor.

If you'd like,
we can first talk a bit about your symptoms or concerns.
```

**Persian:**
```
می‌تونم بهت کمک کنم موضوعات مربوط به سلامت رو بهتر بفهمی
و مراقب وضعیتت باشی،
اما تشخیص یا تصمیم درمانی قطعی
حتماً باید توسط پزشک انجام بشه.

اگه دوست داری،
می‌تونیم اول کمی درباره علائم یا نگرانی‌هات صحبت کنیم.
```

**Arabic:**
```
يمكنني مساعدتك في فهم الأمور الصحية
ومتابعة حالتك،
لكن التشخيص أو القرارات العلاجية
يجب أن تتم دائماً مع طبيب مختص.

إذا أحببت،
يمكننا أولاً التحدث قليلاً عن الأعراض أو ما يقلقك.
```

---

## Example Flows

### User Delegates Control

```
Sedi: "Dear Javad, how can I support you today?"
User: "You decide"
Sedi: "That's completely fine.
      I'll start gently.
      
      I'm here to help you stay aware of your health,
      understand your current condition,
      and support you in taking better care of yourself.
      
      To begin,
      how would you describe your health today?
      Would you say it feels good, normal, or a bit challenging?"
State: user_delegates
```

### User Asks Unrelated Question

```
Sedi: "Dear Javad, how can I support you today?"
User: "What's the weather like?"
Sedi: "That's a good question.
      
      My role is to support your health and well-being,
      help you stay informed about your condition,
      and assist you in taking better care of yourself.
      
      If you're comfortable,
      we can start with something simple about your health today."
State: unrelated_question
```

### User Asks Early Medical Question

```
Sedi: "Dear Javad, how can I support you today?"
User: "Can you diagnose my symptoms?"
Sedi: "I can help you understand health topics
      and support you in monitoring your condition,
      but medical diagnosis or treatment decisions
      should always be made with a qualified doctor.
      
      If you'd like,
      we can first talk a bit about your symptoms or concerns."
State: early_medical_question
```

---

## Key Features

### 1. Gentle Guidance
- Takes control when user delegates
- Structured but friendly language
- Health-awareness oriented
- No pressure or forced flows

### 2. Focus on Health
- Redirects unrelated questions to health
- Maintains health awareness focus
- Professional but caring tone

### 3. Safety First
- Early medical questions handled safely
- Redirects to doctor for diagnosis
- Encourages symptom discussion first

### 4. Language Support
- Full support for EN/FA/AR
- Delegation keywords in all languages
- Health/unrelated question detection per language

---

## Detection Logic Details

### Care Exploration Phase

**Triggers when:**
- First Real Interaction or Unclear Response was shown
- User hasn't chosen a clear health path yet
- Conversation count 5-10 (early interaction phase)

**Prevents:**
- Triggering during onboarding
- Triggering after context is established (count > 10)
- Triggering before first interaction shown

### User Delegation Detection

**Keywords by Language:**
- **EN:** "you decide", "you start", "you choose", "whatever you think", "up to you", "your choice", "you know", "you pick"
- **FA:** "تو تصمیم بگیر", "تو شروع کن", "تو انتخاب کن", "هر چی فکر می‌کنی", "به تو بستگی داره", "هر چی تو بگی", "تو می‌دونی"
- **AR:** "أنت تقرر", "أنت تبدأ", "أنت تختار", "مهما تعتقد", "يعود لك", "اختيارك", "أنت تعرف"

**Behavior:**
- Detects explicit delegation phrases
- Takes gentle control
- Starts with health awareness question

### Unrelated Question Detection

**Health Keywords (to exclude):**
- **EN:** health, symptom, pain, feel, body, doctor, medical, illness, disease, treatment, care, wellness
- **FA:** سلامت، علائم، درد، احساس، بدن، پزشک، بیماری، درمان، مراقبت، تندرستی
- **AR:** صحة، أعراض، ألم، شعور، جسم، طبيب، مرض، علاج، رعاية، صحة

**Question Indicators:**
- **EN:** what, who, where, when, why, how, can you, do you, are you, is it, ?
- **FA:** چی، کی، کجا، چرا، چطور، می‌تونی، می‌شه، هست، ؟
- **AR:** ماذا، من، أين، متى، لماذا، كيف، هل يمكنك، هل أنت، ؟

**Behavior:**
- Detects questions that are NOT health-related
- Acknowledges question politely
- Redirects to health focus

### Early Medical Question Detection

**Medical Keywords:**
- **EN:** diagnose, diagnosis, treatment, prescribe, medicine, symptom, disease, illness, sick, pain, cure, heal, what's wrong, what is wrong
- **FA:** تشخیص، درمان، دارو، علائم، بیماری، مریض، درد، درمان کن، تشخیص بده، چی شده، مشکل چیه
- **AR:** تشخيص، علاج، دواء، أعراض، مرض، مريض، ألم، عالج، شخص، ما الخطأ، ما المشكلة

**Behavior:**
- Detects medical questions early (count 5-8)
- Provides safe response
- Redirects to symptom discussion first
- Different from general `medical_question` (which is for later, after context)

---

## Integration Points

### With Existing System

1. **First Real Interaction:**
   - Triggers after first_real_interaction or unclear_response
   - Seamless transition from invitation to guidance
   - Maintains trust-building tone

2. **Stage System:**
   - Works within `INTRODUCTION` and `GETTING_TO_KNOW` stages
   - Natural progression as conversation develops
   - No stage changes required

3. **Context System:**
   - Uses `conversation_count` to detect timing
   - Uses last Sedi message to detect phase
   - Reads from structured memory domains

4. **Response Generation:**
   - Hardcoded prompts for consistency
   - Maintains structured, professional tone
   - Health-awareness focused

---

## Language & Style Rules

### Implemented Rules

✅ **Friendly but structured:**
- Professional phrasing
- Clear structure
- No vague emotional phrases

✅ **Health-awareness oriented:**
- Focus on health awareness
- Self-care emphasis
- Condition monitoring

✅ **No passive language:**
- Active guidance
- Clear direction
- Professional confidence

✅ **Consistent tone:**
- Same tone across EN/FA/AR
- Respectful grammar
- Professional phrasing

---

## Limitations & Future Enhancements

### Current Limitations

1. **Delegation Detection:**
   - Keyword-based (simplified)
   - Could be enhanced with intent detection
   - May miss nuanced delegation phrases

2. **Unrelated Question Detection:**
   - Relies on keyword exclusion
   - May misclassify health-related questions
   - Could be enhanced with NLP

3. **Early Medical Detection:**
   - Uses conversation_count for timing
   - Could be enhanced with context analysis
   - May not catch all early medical questions

### Future Enhancements

1. Add intent detection for better delegation recognition
2. Enhance unrelated question detection with NLP
3. Improve early medical question detection with context analysis
4. Add more nuanced responses for different delegation styles

---

## Testing Recommendations

### Test Cases

1. **User Delegates:**
   - Test with "you decide", "you start", "تو تصمیم بگیر", "أنت تقرر"
   - Verify gentle control is taken
   - Test in all three languages

2. **Unrelated Question:**
   - Test with "What's the weather?", "چی خبر؟", "ما الأخبار؟"
   - Verify health redirect
   - Test in all three languages

3. **Early Medical Question:**
   - Test with "Can you diagnose?", "تشخیص بده", "شخص"
   - Verify safe response
   - Test in all three languages

4. **Flow Continuity:**
   - Verify smooth transition from first interaction
   - Verify GPT takes over after guidance
   - Verify no prompt conflicts

---

## Conclusion

The Care Exploration Layer has been successfully implemented with:
- ✅ Gentle guidance when user delegates control
- ✅ Polite redirection for unrelated questions
- ✅ Safe handling of early medical questions
- ✅ Full language support (EN/FA/AR)
- ✅ Structured, professional, health-aware language
- ✅ Integration with existing stage system
- ✅ No database or schema changes
- ✅ Context-based state detection

The system now provides soft guidance to help users start their health journey when they don't choose a clear direction, maintaining a calm, professional, and caring tone throughout.

